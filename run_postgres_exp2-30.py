import json
import re
import time
import psycopg2
import psycopg2.errors
import matplotlib.pyplot as plt
import numpy as np

# --- CONFIGURATION ---
HOST_IP = "localhost" 
DB_NAME = "postgres" 
MAPPING_FILE = "experiment_mapping.json"
# ---------------------

print(f"[SYSTEM] Loading execution plan from {MAPPING_FILE}...", flush=True)
with open(MAPPING_FILE, 'r') as f:
    plan = json.load(f)

global_policies = plan["policies"]
queries_dict = plan["queries"]

conn_admin = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="postgres", password="secure26DBPostgreSQL", port=5432)
conn_admin.autocommit = True
cursor_admin = conn_admin.cursor()
cursor_admin.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tpch_tester') THEN CREATE ROLE tpch_tester LOGIN; END IF; END $$;")
cursor_admin.execute("ALTER ROLE tpch_tester WITH PASSWORD 'password';")
cursor_admin.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tpch_tester;")

conn_tester = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="tpch_tester", password="password", port=5432)
conn_tester.autocommit = True
cursor_tester = conn_tester.cursor()

def run_query_safe(query, timeout_ms=0):
    if timeout_ms > 0: cursor_tester.execute(f"SET statement_timeout = {int(timeout_ms)}")
    else: cursor_tester.execute("SET statement_timeout = 0")
    
    # Unleash 30 cores safely
    cursor_tester.execute("SET max_parallel_workers_per_gather = 30;") 
    cursor_tester.execute("SET work_mem = '1500MB';") 
    cursor_tester.execute("SET enable_nestloop = off;") 
    cursor_tester.execute("SET jit = off;") 
        
    times = []
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
        print(f"      [!] Error: {e}".strip(), flush=True)
        return None

# --- STATE MANAGERS ---

def reset_database():
    cursor_admin.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cursor_admin.fetchall():
        cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
        cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
        cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")
        cursor_admin.execute(f"DROP INDEX IF EXISTS idx_{table}_policy_cov;")

def build_policy_indexes():
    prefix_map = {
        'region': 'r_', 'nation': 'n_', 'part': 'p_',
        'supplier': 's_', 'partsupp': 'ps_',
        'customer': 'c_', 'orders': 'o_', 'lineitem': 'l_'
    }
    for table, pol_data in global_policies.items():
        predicate = pol_data["predicate"]
        all_cols = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', predicate.lower()))
        valid_cols = [col for col in all_cols if col.startswith(prefix_map.get(table, ''))]
        
        if valid_cols:
            col_str = ", ".join(valid_cols)
            print(f"  -> Building index on {table} for policy columns: ({col_str})", flush=True)
            cursor_admin.execute(f"CREATE INDEX idx_{table}_policy_cov ON {table} ({col_str});")
        cursor_admin.execute(f"ANALYZE {table};")

def apply_rls():
    LOCAL_PK_MAP = {
        'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
        'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
        'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
    }
    
    for table, pol_data in global_policies.items():
        policy_sql = pol_data["raw_sql"]
        logical_predicate = pol_data["predicate"]
        
        pk_col = LOCAL_PK_MAP[table]
        pk_left = f"({pk_col})" if "," in pk_col else pk_col
        
        bypass_view = f"rls_bypass_view_{table}"
        cursor_admin.execute(f"CREATE OR REPLACE VIEW {bypass_view} AS {policy_sql};")
        cursor_admin.execute(f"GRANT SELECT ON {bypass_view} TO tpch_tester;")
        
        actual_rls_predicate = f"{pk_left} IN (SELECT {pk_col} FROM {bypass_view})"
        
        print(f"  -> [LOG] Securing {table}", flush=True)
        print(f"     |-- Logical Filter: {logical_predicate}", flush=True)
        print(f"     |-- Applied Policy: USING ({actual_rls_predicate})", flush=True)
        
        cursor_admin.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"CREATE POLICY tpch_rls_pol ON {table} FOR SELECT USING ({actual_rls_predicate});")
        cursor_admin.execute(f"ANALYZE {table};")

def create_secure_views():
    LOCAL_PK_MAP = {
        'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
        'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
        'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
    }
    
    for table, pol_data in global_policies.items():
        policy_sql = pol_data["raw_sql"]
        pk_col = LOCAL_PK_MAP[table]
        pk_left = f"({pk_col})" if "," in pk_col else pk_col
        
        # 1. Create bypass view logic
        bypass_view = f"rls_bypass_view_{table}"
        cursor_admin.execute(f"CREATE OR REPLACE VIEW {bypass_view} AS {policy_sql};")
        cursor_admin.execute(f"GRANT SELECT ON {bypass_view} TO tpch_tester;")
        
        # 2. Project ALL columns from the base table, filtered by the bypass view
        cursor_admin.execute(f"CREATE OR REPLACE VIEW {table}_view AS SELECT * FROM {table} WHERE {pk_left} IN (SELECT {pk_col} FROM {bypass_view});")
        cursor_admin.execute(f"GRANT SELECT ON {table}_view TO tpch_tester;")

def rewrite_for_views(sql):
    modified_sql = sql
    for t in global_policies.keys():
        modified_sql = re.sub(rf'(?i)\bFROM\s+{t}\b', f'FROM {t}_view', modified_sql)
        modified_sql = re.sub(rf'(?i)\bJOIN\s+{t}\b', f'JOIN {t}_view', modified_sql)
        modified_sql = re.sub(rf'(?i)(,\s*){t}\b', rf'\g<1>{t}_view', modified_sql)
    return modified_sql

# --- EXECUTION ---

baseline_times = {}
exp1_times = {}
exp2_times = {}

print("\n--- PHASE 1: Running Baseline (Indexed RLS) ---", flush=True)
reset_database()
build_policy_indexes()
apply_rls()
for i in range(1, 23):
    q_id = str(i)
    if q_id not in queries_dict:
        print(f"  [Q{i}] Skipped: Does not touch protected tables.", flush=True)
        continue
        
    q_data = queries_dict[q_id]
    
    print(f"  -> [DEBUG] Firing Q{q_id}. Active Predicates:", flush=True)
    for tbl, pol in q_data.get("applied_policies", {}).items():
        clean_pred = pol["predicate"].replace('\n', ' ').strip()
        print(f"       |-- {tbl}: {clean_pred}", flush=True)
        
    avg_time = run_query_safe(q_data["sql"], timeout_ms=900000) # 15-Min Hard Limit
    
    if avg_time == float('inf'):
        baseline_times[q_id] = 900.0 # Store math denominator for next phases
        print(f"  [Q{q_id}] Indexed RLS Baseline: TIMEOUT (> 900s)\n", flush=True)
    elif avg_time is None:
        print(f"  [Q{q_id}] Indexed RLS Baseline: ERR\n", flush=True)
    else:
        baseline_times[q_id] = avg_time
        print(f"  [Q{q_id}] Indexed RLS Baseline: {avg_time:.4f}s\n", flush=True)

reset_database() 

print("\n--- PHASE 2: Running Exp 1 (Pure Native RLS) ---", flush=True)
apply_rls()
for i in range(1, 23):
    q_id = str(i)
    if q_id not in queries_dict or q_id not in baseline_times: 
        continue
        
    q_data = queries_dict[q_id]
    
    print(f"  -> [DEBUG] Firing Q{q_id} (Pure RLS). Active Predicates:", flush=True)
    for tbl, pol in q_data.get("applied_policies", {}).items():
        clean_pred = pol["predicate"].replace('\n', ' ').strip()
        print(f"       |-- {tbl}: {clean_pred}", flush=True)
        
    avg_time = run_query_safe(q_data["sql"], timeout_ms=baseline_times[q_id] * 30 * 1000)
    exp1_times[q_id] = avg_time
    
    if avg_time is None:
        print(f"  [Q{q_id}] Pure RLS Avg: ERR\n", flush=True)
    elif avg_time == float('inf'):
        print(f"  [Q{q_id}] Pure RLS Avg: TIMEOUT\n", flush=True)
    else:
        print(f"  [Q{q_id}] Pure RLS Avg: {avg_time:.4f}s\n", flush=True)

print("\n--- PHASE 3: Running Exp 2 (Secure Views) ---", flush=True)
reset_database()
create_secure_views()
for i in range(1, 23):
    q_id = str(i)
    if q_id not in queries_dict or q_id not in baseline_times: 
        continue
        
    q_data = queries_dict[q_id]
    
    print(f"  -> [DEBUG] Firing Q{q_id} (Secure Views). Active Predicates:", flush=True)
    for tbl, pol in q_data.get("applied_policies", {}).items():
        clean_pred = pol["predicate"].replace('\n', ' ').strip()
        print(f"       |-- {tbl}: {clean_pred}", flush=True)
        
    view_sql = rewrite_for_views(q_data["sql"])
    avg_time = run_query_safe(view_sql, timeout_ms=baseline_times[q_id] * 30 * 1000)
    exp2_times[q_id] = avg_time
    
    if avg_time is None:
        print(f"  [Q{q_id}] Secure Views Avg: ERR\n", flush=True)
    elif avg_time == float('inf'):
        print(f"  [Q{q_id}] Secure Views Avg: TIMEOUT\n", flush=True)
    else:
        print(f"  [Q{q_id}] Secure Views Avg: {avg_time:.4f}s\n", flush=True)

cursor_tester.close()
conn_tester.close()
cursor_admin.close()
conn_admin.close()

# --- VISUALIZATION ---
if baseline_times:
    queries = [f"Q{q}" for q in baseline_times.keys()]
    exp1_ratios = [min(15.0, exp1_times[q]/baseline_times[q]) if exp1_times.get(q) is not None else 0 for q in baseline_times.keys()]
    exp2_ratios = [min(15.0, exp2_times[q]/baseline_times[q]) if exp2_times.get(q) is not None else 0 for q in baseline_times.keys()]

    x = np.arange(len(queries))
    width = 0.35

    fig, ax = plt.subplots(figsize=(20, 8))
    ax.bar(x - width/2, exp1_ratios, width, label='Exp 1 (Pure RLS)', color='crimson', edgecolor='black')
    ax.bar(x + width/2, exp2_ratios, width, label='Exp 2 (Secure Views)', color='royalblue', edgecolor='black')

    ax.axhline(1, color='black', linestyle='--', linewidth=2, label='Baseline (Indexed RLS = 1.0x)')
    ax.set_ylabel('Execution Slowdown Factor')
    ax.set_title('PostgreSQL RLS Architecture Benchmark (Bypass View RLS vs Secure Views)', fontsize=16, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(queries, rotation=45, ha='right')
    ax.legend()
    plt.tight_layout()
    plt.savefig('postgres_exp2_clean.png', dpi=300)
    print("\nSaved as postgres_exp2_clean.png", flush=True)
