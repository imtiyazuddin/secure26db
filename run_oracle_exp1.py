import os
import re
import json
import time
import oracledb
import matplotlib.pyplot as plt

# 1. Load Configuration
with open('index_config.json', 'r') as f:
    PK_MAP = json.load(f)

conn_admin = oracledb.connect(user="system", password="secure26DBOracle", dsn="localhost:1521/FREEPDB1")
cursor_admin = conn_admin.cursor()
cursor_admin.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD'")

try: cursor_admin.execute("CREATE USER tpch_tester IDENTIFIED BY password")
except: pass
cursor_admin.execute("GRANT CONNECT, SELECT ANY TABLE TO tpch_tester")

conn_tester = oracledb.connect(user="tpch_tester", password="password", dsn="localhost:1521/FREEPDB1")
cursor_tester = conn_tester.cursor()
cursor_tester.execute("ALTER SESSION SET CURRENT_SCHEMA = SYSTEM")
cursor_tester.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD'")

# Force the tester session to utilize Multi-Threading for heavy TPC-H queries
cursor_tester.execute("ALTER SESSION FORCE PARALLEL QUERY PARALLEL 2")

print("\n[SYSTEM] Purging artifacts, building Shadow Tables, and engaging Multi-Threading...")
for table, pk_col in PK_MAP.items():
    try: cursor_admin.execute(f"BEGIN DBMS_RLS.DROP_POLICY(object_schema => 'SYSTEM', object_name => '{table.upper()}', policy_name => 'VPD_NATIVE_POL'); EXCEPTION WHEN OTHERS THEN NULL; END;")
    except: pass
    try: cursor_admin.execute(f"BEGIN EXECUTE IMMEDIATE 'DROP FUNCTION VPD_FUNC_NATIVE'; EXCEPTION WHEN OTHERS THEN NULL; END;")
    except: pass
    
    # Base Indexes
    try: cursor_admin.execute(f"CREATE INDEX idx_{table}_pk ON SYSTEM.{table.upper()} ({pk_col})")
    except Exception as e: 
        if "ORA-01408" not in str(e) and "ORA-00955" not in str(e): print(f"  -> Index Warning on {table}: {e}")

    try: cursor_admin.execute(f"DROP TABLE {table}_shadow CASCADE CONSTRAINTS")
    except: pass
    cursor_admin.execute(f"CREATE TABLE {table}_shadow AS SELECT * FROM {table}")
    
    try: cursor_admin.execute(f"CREATE INDEX idx_{table}_shad_pk ON {table}_shadow ({pk_col})")
    except: pass

    # --- THE SPEED FIX: Instantly analyze the new shadow tables and enable parallelism ---
    cursor_admin.execute(f"ALTER TABLE {table}_shadow PARALLEL 2")
    cursor_admin.execute(f"ALTER TABLE {table} PARALLEL 2")
    cursor_admin.execute(f"BEGIN DBMS_STATS.GATHER_TABLE_STATS('SYSTEM', '{table}'); END;")
    cursor_admin.execute(f"BEGIN DBMS_STATS.GATHER_TABLE_STATS('SYSTEM', '{table}_shadow'); END;")
    # -----------------------------------------------------------------------------------

# 3. Parse Baseline Queries
queries_dict = {}
with open('queries/all_queries.sql', 'r') as f:
    sql_text = f.read()
if sql_text.count(';') < 20: raw_queries = re.split(r';|\n\s*\n', sql_text)
else:
    temp_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)
    raw_queries = re.sub(r'--.*', '', temp_text).split(';')

for i, q in enumerate([q.strip() for q in raw_queries if len(q.strip()) > 10]): 
    queries_dict[i + 1] = q

# 4. Parse Policies into Memory
available_policies = {}
for p_file in os.listdir('policies'):
    if not p_file.endswith('.sql'): continue
    with open(os.path.join('policies', p_file), 'r') as f: clean_sql = f.read()
    
    clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
    clean_sql = re.sub(r'--.*', '', clean_sql).strip()
    match = re.search(r'\b(SELECT|WITH)\b.*', clean_sql, re.IGNORECASE | re.DOTALL)
    if match: clean_sql = match.group(0)
    
    clean_sql = re.sub(r'DATEADD\s*\(\s*DAY\s*,\s*(-?\d+)\s*,\s*CAST\s*\(\s*GETDATE\s*\(\s*\)\s*AS\s*DATE\s*\)\s*\)', r"TRUNC(SYSDATE) + (\1)", clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r'CAST\s*\(\s*GETDATE\s*\(\s*\)\s*AS\s*DATE\s*\)', 'TRUNC(SYSDATE)', clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r'\bDATEDIFF\s*\(\s*DAY\s*,\s*([a-zA-Z0-9_.]+)\s*,\s*([a-zA-Z0-9_.]+)\s*\)', r'(\2 - \1)', clean_sql, flags=re.IGNORECASE)
    clean_sql = clean_sql.replace('[', '').replace(']', '')
    clean_sql = re.sub(r'"?dbo"?\.', '', clean_sql, flags=re.IGNORECASE) 
    
    clean_sql = re.sub(r'\bCROSS\s+APPLY\b', 'CROSS JOIN LATERAL', clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r'\bOUTER\s+APPLY\b', 'LEFT JOIN LATERAL', clean_sql, flags=re.IGNORECASE)
    
    clean_sql = re.sub(r'\b(FROM|JOIN)\s+([a-zA-Z0-9_".]+)\s+AS\s+([a-zA-Z0-9_"]+)\b', r'\1 \2 \3', clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r',\s*([a-zA-Z0-9_".]+)\s+AS\s+([a-zA-Z0-9_"]+)\b', r', \1 \2', clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r'\)\s*AS\s+([a-zA-Z0-9_"]+)\b', r') \1', clean_sql, flags=re.IGNORECASE)
    clean_sql = clean_sql.replace(';', '')
    
    match = re.search(r'\bFROM\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
    if match:
        target_table = match.group(1).lower()
        if target_table in PK_MAP:
            available_policies[target_table] = clean_sql

print(f"[SYSTEM] Loaded {len(available_policies)} unique VPD policies into memory.")

def get_tables_in_query(sql_query):
    words = re.findall(r'\b[a-zA-Z_]+\b', sql_query.lower())
    return list(set(words).intersection(set(PK_MAP.keys())))

def run_query_loop(conn, cursor, query, timeout_ms=0):
    conn.call_timeout = int(timeout_ms)
    times = []
    try:
        for _ in range(4):
            start = time.perf_counter()
            cursor.execute(query)
            cursor.fetchall()
            times.append(time.perf_counter() - start)
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        if "timeout" in error_obj.message.lower() or "DPY-4024" in error_obj.message: 
            return float('inf')
        print(f"      [!] DB Error: {e}")
        return None
    finally:
        conn.call_timeout = 0 
        
    return sum(times[1:]) / 3.0

results = {}
print("\n--- Starting Native VPD Benchmark (Experiment 1) ---")

for q_id, q_sql in queries_dict.items():
    query_tables = get_tables_in_query(q_sql)
    
    matched_table = None
    for tbl in query_tables:
        if tbl in available_policies:
            matched_table = tbl
            break
            
    if not matched_table:
        continue
        
    print(f"\n[Executing Q{q_id}] Applying {matched_table.upper()} policy...")
    
    policy_sql = available_policies[matched_table]
    pk_col = PK_MAP[matched_table]
    pk_left = f"({pk_col})" if "," in pk_col else pk_col
    
    anti_recurse_policy = policy_sql
    for t in PK_MAP.keys():
        anti_recurse_policy = re.sub(rf'\b{t}\b', f'{t}_shadow', anti_recurse_policy, flags=re.IGNORECASE)
    
    pure_condition = f"{pk_left} IN (SELECT {pk_col} FROM ({anti_recurse_policy}))"
    
    try:
        cursor_tester.execute(f"SELECT 1 FROM {matched_table} WHERE {pure_condition} AND ROWNUM = 1")
    except Exception as e:
        print(f"      [!] Syntax Error Unmasked: {e}")
        continue 

    safe_condition = pure_condition.replace("'", "''")

    setup_func = f"""
        CREATE OR REPLACE FUNCTION VPD_FUNC_NATIVE(schema_p IN VARCHAR2, table_p IN VARCHAR2) RETURN VARCHAR2 AS 
        BEGIN 
            RETURN '{safe_condition}'; 
        END;
    """
    
    setup_policy = f"""
        BEGIN 
            DBMS_RLS.ADD_POLICY(
                object_schema => 'SYSTEM', 
                object_name => '{matched_table.upper()}', 
                policy_name => 'VPD_NATIVE_POL', 
                function_schema => 'SYSTEM', 
                policy_function => 'VPD_FUNC_NATIVE', 
                statement_types => 'SELECT'
            ); 
        END;
    """
    
    teardown_script = f"""
        BEGIN
            BEGIN DBMS_RLS.DROP_POLICY(object_schema => 'SYSTEM', object_name => '{matched_table.upper()}', policy_name => 'VPD_NATIVE_POL'); EXCEPTION WHEN OTHERS THEN NULL; END;
            BEGIN EXECUTE IMMEDIATE 'DROP FUNCTION VPD_FUNC_NATIVE'; EXCEPTION WHEN OTHERS THEN NULL; END;
        END;
    """

    baseline_avg = run_query_loop(conn_tester, cursor_tester, q_sql, timeout_ms=120000)
    if baseline_avg == float('inf'):
        print("  -> Baseline timeout (> 120s). Skipping.")
        continue
    if baseline_avg is None: continue
    print(f"  -> Baseline Avg: {baseline_avg:.4f} sec")
    
    try: 
        cursor_admin.execute(setup_func)
        cursor_admin.execute(setup_policy)
    except Exception as e: 
        print(f"  -> Native Setup Error: {e}")
        cursor_admin.execute(teardown_script)
        continue
        
    timeout_ms = (baseline_avg * 10.0) * 1000
    modified_avg = run_query_loop(conn_tester, cursor_tester, q_sql, timeout_ms=timeout_ms)
    
    if modified_avg == float('inf'): 
        print("  -> Execution capped at > 10.0x penalty!")
        results[f"Q{q_id}"] = 10.0
    elif modified_avg is not None: 
        print(f"  -> Native Policy Avg: {modified_avg:.4f} sec")
        results[f"Q{q_id}"] = modified_avg / baseline_avg
    else: results[f"Q{q_id}"] = 0
    
    cursor_admin.execute(teardown_script)

cursor_tester.close()
conn_tester.close()
cursor_admin.close()
conn_admin.close()

if results:
    plt.figure(figsize=(24, 8))
    queries = list(results.keys())
    ratios = list(results.values())
    colors = ['crimson' if r >= 10.0 else 'darkorange' for r in ratios]
    bars = plt.bar(queries, ratios, color=colors, edgecolor='black')
    plt.axhline(y=1, color='black', linestyle='--', linewidth=2, label='Baseline (1.0x)')
    plt.ylabel('Execution Slowdown Factor', fontsize=12)
    plt.xlabel('TPC-H Queries', fontsize=12)
    plt.title('Oracle Native VPD Penalty (Experiment 1)', fontsize=16, fontweight='bold')
    plt.xticks(rotation=45, ha='right', fontsize=10)
    for bar in bars:
        yval = bar.get_height()
        label = ">10x" if yval >= 10.0 else f"{yval:.2f}x"
        plt.text(bar.get_x() + bar.get_width()/2, yval + 0.1, label, ha='center', va='bottom', fontsize=9, rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig('oracle_native_vpd.png', dpi=300)
    print("\nSaved as oracle_native_vpd.png")
