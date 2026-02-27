import os
import re
import json
import time
import psycopg2
import matplotlib.pyplot as plt

# 1. Load Configuration
with open('index_config.json', 'r') as f:
    PK_MAP = json.load(f)

conn = psycopg2.connect(dbname="postgres", user="postgres", password="secure26DBPostgreSQL", host="172.17.0.3", port="5432")
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("SET work_mem = '256MB';") 
cursor.execute("SET max_parallel_workers_per_gather = 0;") 

# 2. Database Cleanup & Index Initialization
print("\n[SYSTEM] Terminating orphaned background queries...")
try:
    cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid() AND datname = 'postgres';")
except: pass

print("[SYSTEM] Purging old artifacts and applying Primary Key Indexes...")
for table, pk_col in PK_MAP.items():
    try:
        cursor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        cursor.execute(f"DROP POLICY IF EXISTS rls_native_pol ON {table};")
        
        # Apply Indexes from Config File
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_pk ON {table} ({pk_col});")
        cursor.execute(f"ANALYZE {table};")
    except Exception as e: 
        print(f"  -> Cleanup/Index Warning on {table}: {e}")

# 3. Parse Baseline Queries
queries_dict = {}
with open('queries/all_queries.sql', 'r') as f:
    sql_text = f.read()
if sql_text.count(';') < 20: raw_queries = re.split(r';|\n\s*\n', sql_text)
else:
    temp_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)
    raw_queries = re.sub(r'--.*', '', temp_text).split(';')

for i, q in enumerate([q.strip() for q in raw_queries if len(q.strip()) > 10]): 
    queries_dict[i + 1] = q + ";"

# 4. Parse Policies into Memory
available_policies = {}
for p_file in os.listdir('policies'):
    if not p_file.endswith('.sql'): continue
    with open(os.path.join('policies', p_file), 'r') as f: clean_sql = f.read()
    
    clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
    clean_sql = re.sub(r'--.*', '', clean_sql).strip()
    match = re.search(r'\b(SELECT|WITH)\b.*', clean_sql, re.IGNORECASE | re.DOTALL)
    if match: clean_sql = match.group(0)
    
    clean_sql = re.sub(r'DATEADD\s*\(\s*DAY\s*,\s*(-?\d+)\s*,\s*CAST\s*\(\s*GETDATE\s*\(\s*\)\s*AS\s*DATE\s*\)\s*\)', r"CURRENT_DATE + INTERVAL '\1 days'", clean_sql, flags=re.IGNORECASE)
    clean_sql = re.sub(r'CAST\s*\(\s*GETDATE\s*\(\s*\)\s*AS\s*DATE\s*\)', 'CURRENT_DATE', clean_sql, flags=re.IGNORECASE)
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

print(f"[SYSTEM] Loaded {len(available_policies)} unique RLS policies into memory.")

def get_tables_in_query(sql_query):
    words = re.findall(r'\b[a-zA-Z_]+\b', sql_query.lower())
    return list(set(words).intersection(set(PK_MAP.keys())))

def run_query_loop(cursor, query, timeout_ms=0):
    cursor.execute(f"SET statement_timeout = {int(timeout_ms)};")
    times = []
    for _ in range(4):
        start = time.perf_counter()
        try: 
            cursor.execute(query)
            cursor.fetchall()
        except psycopg2.errors.QueryCanceled: return float('inf')
        except Exception as e: 
            print(f"      [!] DB Error: {e}")
            return None
        times.append(time.perf_counter() - start)
    return sum(times[1:]) / 3.0

results = {}
print("\n--- Starting Native RLS Benchmark (Experiment 1) ---")

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
    
    # --- THE FIX: Wrap the raw policy in an exact column matcher ---
    setup_script = f"""
        CREATE POLICY rls_native_pol ON {matched_table} FOR SELECT USING ( ({pk_col}) IN (SELECT {pk_col} FROM ({policy_sql}) AS rls_subq) );
        ALTER TABLE {matched_table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {matched_table} FORCE ROW LEVEL SECURITY; 
    """
    # ---------------------------------------------------------------
    
    teardown_script = f"""
        DROP POLICY IF EXISTS rls_native_pol ON {matched_table};
        ALTER TABLE {matched_table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {matched_table} DISABLE ROW LEVEL SECURITY;
    """

    baseline_avg = run_query_loop(cursor, q_sql, timeout_ms=120000)
    if baseline_avg == float('inf'):
        print("  -> Baseline timeout (> 120s). Skipping.")
        continue
    if baseline_avg is None: continue
    print(f"  -> Baseline Avg: {baseline_avg:.4f} sec")
    
    try: cursor.execute(setup_script)
    except Exception as e: 
        print(f"  -> Native Setup Error: {e}")
        cursor.execute(teardown_script)
        continue
        
    timeout_ms = (baseline_avg * 10.0) * 1000
    modified_avg = run_query_loop(cursor, q_sql, timeout_ms=timeout_ms)
    
    if modified_avg == float('inf'): 
        print("  -> Execution capped at > 10.0x penalty!")
        results[f"Q{q_id}"] = 10.0
    elif modified_avg is not None: 
        print(f"  -> Native Policy Avg: {modified_avg:.4f} sec")
        results[f"Q{q_id}"] = modified_avg / baseline_avg
    else: results[f"Q{q_id}"] = 0
    
    cursor.execute(teardown_script)

cursor.close()
conn.close()

if results:
    plt.figure(figsize=(24, 8))
    queries = list(results.keys())
    ratios = list(results.values())
    colors = ['crimson' if r >= 10.0 else 'steelblue' for r in ratios]
    bars = plt.bar(queries, ratios, color=colors, edgecolor='black')
    plt.axhline(y=1, color='green', linestyle='--', linewidth=2, label='Baseline (1.0x)')
    plt.ylabel('Execution Slowdown Factor', fontsize=12)
    plt.xlabel('TPC-H Queries', fontsize=12)
    plt.title('PostgreSQL Pure Native RLS Penalty (Experiment 1)', fontsize=16, fontweight='bold')
    plt.xticks(rotation=45, ha='right', fontsize=10)
    for bar in bars:
        yval = bar.get_height()
        label = ">10x" if yval >= 10.0 else f"{yval:.2f}x"
        plt.text(bar.get_x() + bar.get_width()/2, yval + 0.1, label, ha='center', va='bottom', fontsize=9, rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig('postgres_native_rls.png', dpi=300)
    print("\nSaved as postgres_native_rls.png")
