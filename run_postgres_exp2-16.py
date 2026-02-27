import os
import re
import time
import psycopg2
import psycopg2.errors
import matplotlib.pyplot as plt
import numpy as np

# --- CONFIGURATION ---
HOST_IP = "172.17.0.3"
DB_NAME = "postgres" 
# ---------------------

# 1. Hardcoded TPC-H Primary Key Map
PK_MAP = {
    'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
    'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
    'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
}

# Connect as Superuser for schema changes
conn_admin = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="postgres", password="secure26DBPostgreSQL")
conn_admin.autocommit = True
cursor_admin = conn_admin.cursor()

# THE FIX: Forcefully reset the password every time to avoid stale credentials
cursor_admin.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tpch_tester') THEN CREATE ROLE tpch_tester LOGIN; END IF; END $$;")
cursor_admin.execute("ALTER ROLE tpch_tester WITH PASSWORD 'password';")
cursor_admin.execute("GRANT USAGE ON SCHEMA public TO tpch_tester;")
cursor_admin.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tpch_tester;")

# Connect as standard user for execution
conn_tester = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="tpch_tester", password="password")
conn_tester.autocommit = True
cursor_tester = conn_tester.cursor()

# 2. Parse Baseline Queries
queries_dict = {}
with open('queries/all_queries.sql', 'r') as f:
    sql_text = f.read()
if sql_text.count(';') < 20: raw_queries = re.split(r';|\n\s*\n', sql_text)
else:
    temp_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)
    raw_queries = re.sub(r'--.*', '', temp_text).split(';')

for i, q in enumerate([q.strip() for q in raw_queries if len(q.strip()) > 10]): 
    queries_dict[i + 1] = q

# 3. Parse Policies into Memory
available_policies = {}
target_tables = ['lineitem', 'customer', 'orders'] 

for p_file in os.listdir('policies'):
    if not p_file.endswith('.sql'): continue
    with open(os.path.join('policies', p_file), 'r') as f: clean_sql = f.read()
    
    clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
    clean_sql = re.sub(r'--.*', '', clean_sql).strip()
    match = re.search(r'\b(SELECT|WITH)\b.*', clean_sql, re.IGNORECASE | re.DOTALL)
    if match: clean_sql = match.group(0)
    clean_sql = clean_sql.replace(';', '')
    
    match = re.search(r'\bFROM\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
    if match:
        table_name = match.group(1).lower()
        if table_name in target_tables and table_name in PK_MAP:
            if table_name not in available_policies:
                available_policies[table_name] = clean_sql

print(f"[SYSTEM] Loaded {len(available_policies)} unique policies for {list(available_policies.keys())}.")

def get_tables_in_query(sql_query):
    words = re.findall(r'\b[a-zA-Z_]+\b', sql_query.lower())
    return list(set(words).intersection(set(PK_MAP.keys())))

def rewrite_query_for_views(sql, tables_with_views):
    modified_sql = sql
    for t in tables_with_views:
        modified_sql = re.sub(rf'(?i)\bFROM\s+{t}\b', f'FROM {t}_view', modified_sql)
        modified_sql = re.sub(rf'(?i)\bJOIN\s+{t}\b', f'JOIN {t}_view', modified_sql)
        modified_sql = re.sub(rf'(?i)(,\s*){t}\b', rf'\g<1>{t}_view', modified_sql)
    return modified_sql

def run_query_safe(query, timeout_ms=0):
    if timeout_ms > 0: cursor_tester.execute(f"SET statement_timeout = {int(timeout_ms)}")
    else: cursor_tester.execute("SET statement_timeout = 0")
    
    # --- THE CPU & MEMORY UNLOCK ---
    cursor_tester.execute("SET max_parallel_workers_per_gather = 16;")
    cursor_tester.execute("SET parallel_setup_cost = 10;") 
    cursor_tester.execute("SET parallel_tuple_cost = 0.001;") 
    
    # Give the workers enough RAM to prevent disk spilling
    cursor_tester.execute("SET work_mem = '512MB';") 
    
    # Force the Optimizer to use Hash Joins instead of Row-by-Row loops
    cursor_tester.execute("SET enable_nestloop = off;")
    # ----------------------    
    times = []
    # ... rest of the function remains the same
    try:
        for _ in range(3):
            start = time.perf_counter()
            cursor_tester.execute(query)
            cursor_tester.fetchall()
            times.append(time.perf_counter() - start)
        return sum(times) / len(times)
    except psycopg2.errors.QueryCanceled:
        return float('inf')
    except Exception as e:
        print(f"      [!] Query Error Unmasked: {e}".strip())
        return None

# --- DATABASE STATE MANAGERS ---

def reset_database():
    for table in PK_MAP.keys():
        cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
        cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
        cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")
        cursor_admin.execute(f"DROP INDEX IF EXISTS idx_{table}_policy_cov;")

def apply_rls():
    for table, policy_sql in available_policies.items():
        pk_col = PK_MAP[table]
        pk_left = f"({pk_col})" if "," in pk_col else pk_col
        
        bypass_view = f"rls_bypass_view_{table}"
        cursor_admin.execute(f"CREATE OR REPLACE VIEW {bypass_view} AS {policy_sql};")
        cursor_admin.execute(f"GRANT SELECT ON {bypass_view} TO tpch_tester;")
        
        predicate = f"{pk_left} IN (SELECT {pk_col} FROM {bypass_view})"
        
        cursor_admin.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"CREATE POLICY tpch_rls_pol ON {table} FOR SELECT USING ({predicate});")

def build_policy_indexes():
    prefix_map = {
        'customer': 'c_', 'orders': 'o_', 'lineitem': 'l_', 
        'part': 'p_', 'supplier': 's_', 'partsupp': 'ps_', 
        'nation': 'n_', 'region': 'r_'
    }
    
    for table, policy_sql in available_policies.items():
        all_cols = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', policy_sql.lower()))
        table_prefix = prefix_map.get(table, '')
        valid_cols = [col for col in all_cols if col.startswith(table_prefix)]
        
        if valid_cols:
            col_str = ", ".join(valid_cols)
            print(f"  -> Building covering index on {table} for columns: {col_str}")
            cursor_admin.execute(f"CREATE INDEX idx_{table}_policy_cov ON {table} ({col_str});")

def create_secure_views():
    for table, policy_sql in available_policies.items():
        cursor_admin.execute(f"CREATE OR REPLACE VIEW {table}_view AS {policy_sql};")
        cursor_admin.execute(f"GRANT SELECT ON {table}_view TO tpch_tester;")

# --- BENCHMARK EXECUTION ---

baseline_times = {}
exp1_times = {}
exp2_times = {}

print("\n--- PHASE 1: Running Baseline (Indexed RLS) ---")
reset_database()
build_policy_indexes()
apply_rls()
for q_id, q_sql in queries_dict.items():
    if not set(get_tables_in_query(q_sql)).intersection(available_policies.keys()): continue
    avg_time = run_query_safe(q_sql, timeout_ms=250000)
    
    if avg_time == float('inf'):
        print(f"  [Q{q_id}] Indexed RLS Baseline: TIMEOUT (> 250s)")
    elif avg_time is not None:
        baseline_times[q_id] = avg_time
        print(f"  [Q{q_id}] Indexed RLS Baseline: {avg_time:.4f}s")

print("\n--- PHASE 2: Running Exp 1 (Pure Native RLS) ---")
reset_database()
apply_rls()
for q_id, q_sql in queries_dict.items():
    if q_id not in baseline_times: continue
    avg_time = run_query_safe(q_sql, timeout_ms=baseline_times[q_id] * 10 * 1000)
    exp1_times[q_id] = avg_time
    print(f"  [Q{q_id}] Pure RLS Avg: {'TIMEOUT' if avg_time == float('inf') else f'{avg_time:.4f}s'}")

print("\n--- PHASE 3: Running Exp 2 (Secure Views) ---")
reset_database()
create_secure_views()
for q_id, q_sql in queries_dict.items():
    if q_id not in baseline_times: continue
    view_sql = rewrite_query_for_views(q_sql, available_policies.keys())
    avg_time = run_query_safe(view_sql, timeout_ms=baseline_times[q_id] * 10 * 1000)
    exp2_times[q_id] = avg_time
    print(f"  [Q{q_id}] Secure Views Avg: {'TIMEOUT' if avg_time == float('inf') else f'{avg_time:.4f}s'}")

cursor_tester.close()
conn_tester.close()
cursor_admin.close()
conn_admin.close()

# --- VISUALIZATION ---
if baseline_times:
    queries = [f"Q{q}" for q in baseline_times.keys()]
    
    exp1_ratios = [min(10.0, exp1_times[q]/baseline_times[q]) if exp1_times[q] else 0 for q in baseline_times.keys()]
    exp2_ratios = [min(10.0, exp2_times[q]/baseline_times[q]) if exp2_times[q] else 0 for q in baseline_times.keys()]

    x = np.arange(len(queries))
    width = 0.35

    fig, ax = plt.subplots(figsize=(20, 8))
    rects1 = ax.bar(x - width/2, exp1_ratios, width, label='Exp 1 (Pure RLS)', color='crimson', edgecolor='black')
    rects2 = ax.bar(x + width/2, exp2_ratios, width, label='Exp 2 (Secure Views)', color='royalblue', edgecolor='black')

    ax.axhline(1, color='black', linestyle='--', linewidth=2, label='Baseline (Indexed RLS = 1.0x)')
    ax.set_ylabel('Execution Slowdown Factor')
    ax.set_title('PostgreSQL Architecture Penalty: Pure RLS vs Secure Views', fontsize=16, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(queries, rotation=45, ha='right')
    ax.legend()

    plt.tight_layout()
    plt.savefig('postgres_exp2_views.png', dpi=300)
    print("\nSaved as postgres_exp2_views.png")
else:
    print("\n[!] No valid baselines recorded. Check policy compatibility.")
