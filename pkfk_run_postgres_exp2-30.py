import json
import re
import time
import psycopg2
import psycopg2.errors
import matplotlib.pyplot as plt
import numpy as np
import subprocess
from contextlib import contextmanager

# ---- Configuration ----
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": 5432,
}

SUDO_PASSWORD = "#secure26DB\n" # give your linux sudo user password, ending with \n


# ---- Database Helper ----
@contextmanager
def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def run_query(query):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()


# ---- Logic Blocks ----
def dummy_logic(label):
    print(f"Running {label}...")
    result = run_query("SELECT now();")
    print(f"{label} time:", result)


# ---- Restart Logic ----
def restart_postgres():
    print("Restarting PostgreSQL...")
    subprocess.run(
        ["sudo", "-S", "systemctl", "restart", "postgresql"],
        input=SUDO_PASSWORD.encode(),
        check=True
    )
    print("Restart command issued.")


def wait_until_ready(timeout=30):
    print("Waiting for PostgreSQL to become ready...")
    start = time.time()

    while True:
        try:
            with get_connection():
                print("PostgreSQL is ready.")
                return
        except psycopg2.OperationalError:
            if time.time() - start > timeout:
                raise TimeoutError("PostgreSQL did not start in time.")
            time.sleep(1)


# --- CONFIGURATION ---
HOST_IP = "localhost" 
DB_NAME = "postgres" 
MAPPING_FILE = "current_experiment_mapping.json"
# ---------------------

DROP_IDX_SQL = """
DO $$
DECLARE
    r RECORD;
    drop_statement TEXT;
BEGIN
    FOR r IN (
        SELECT 
            n.nspname AS schemaname, 
            c_ind.relname AS indexname,
            format('DROP INDEX %I.%I;', n.nspname, c_ind.relname) AS drop_cmd
        FROM 
            pg_index ind
        JOIN 
            pg_class c_ind ON c_ind.oid = ind.indexrelid
        JOIN 
            pg_namespace n ON n.oid = c_ind.relnamespace
        LEFT JOIN 
            pg_constraint cons ON cons.conindid = ind.indexrelid
        WHERE 
            n.nspname = 'public' 
            AND cons.oid IS NULL 
    )
    LOOP
        RAISE INFO '%', r.drop_cmd; 
        EXECUTE r.drop_cmd;
    END LOOP;
END $$;
"""

TPCH_COLUMN_TO_TABLE = {
        # region
        "r_regionkey": "region",
        "r_name": "region",
        "r_comment": "region",

        # nation
        "n_nationkey": "nation",
        "n_name": "nation",
        "n_regionkey": "nation",
        "n_comment": "nation",

        # part
        "p_partkey": "part",
        "p_name": "part",
        "p_mfgr": "part",
        "p_brand": "part",
        "p_type": "part",
        "p_size": "part",
        "p_container": "part",
        "p_retailprice": "part",
        "p_comment": "part",

        # supplier
        "s_suppkey": "supplier",
        "s_name": "supplier",
        "s_address": "supplier",
        "s_nationkey": "supplier",
        "s_phone": "supplier",
        "s_acctbal": "supplier",
        "s_comment": "supplier",

        # partsupp
        "ps_partkey": "partsupp",
        "ps_suppkey": "partsupp",
        "ps_availqty": "partsupp",
        "ps_supplycost": "partsupp",
        "ps_comment": "partsupp",

        # customer
        "c_custkey": "customer",
        "c_name": "customer",
        "c_address": "customer",
        "c_nationkey": "customer",
        "c_phone": "customer",
        "c_acctbal": "customer",
        "c_mktsegment": "customer",
        "c_comment": "customer",

        # orders
        "o_orderkey": "orders",
        "o_custkey": "orders",
        "o_orderstatus": "orders",
        "o_totalprice": "orders",
        "o_orderdate": "orders",
        "o_orderpriority": "orders",
        "o_clerk": "orders",
        "o_shippriority": "orders",
        "o_comment": "orders",

        # lineitem
        "l_orderkey": "lineitem",
        "l_partkey": "lineitem",
        "l_suppkey": "lineitem",
        "l_linenumber": "lineitem",
        "l_quantity": "lineitem",
        "l_extendedprice": "lineitem",
        "l_discount": "lineitem",
        "l_tax": "lineitem",
        "l_returnflag": "lineitem",
        "l_linestatus": "lineitem",
        "l_shipdate": "lineitem",
        "l_commitdate": "lineitem",
        "l_receiptdate": "lineitem",
        "l_shipinstruct": "lineitem",
        "l_shipmode": "lineitem",
        "l_comment": "lineitem",
    }

print(f"[SYSTEM] Loading execution plan from {MAPPING_FILE}...", flush=True)
with open(MAPPING_FILE, 'r') as f:
    plan = json.load(f)

global_policies = plan["policies"]
queries_dict = plan["queries"]

conn_admin = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="postgres", password="password", port=5432)
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
    
    # --- Injecting Performance Flags ---
    cursor_tester.execute("SET maintenance_work_mem = '2GB';")
    cursor_tester.execute("SET default_statistics_target = 500;")
    cursor_tester.execute("SET random_page_cost = 4;")
    cursor_tester.execute("SET effective_io_concurrency = 2;")
    cursor_tester.execute("SET work_mem = '187245kB';")
    cursor_tester.execute("SET max_parallel_workers_per_gather = 15;")
    # -----------------------------------    
    times = []
    try:
        for _ in range(4):
            start = time.perf_counter()
            cursor_tester.execute(query)
            cursor_tester.fetchall()
            times.append(time.perf_counter() - start)
        return sum(times[1:]) / 3.0 
    except psycopg2.errors.QueryCanceled:
        return float('inf')
    except Exception as e:
        print(f"      [!] Error: {e}".strip(), flush=True)
        return None

# --- STATE MANAGERS ---

def reset_database():
    cursor_admin.execute(DROP_IDX_SQL)
    print(cursor_admin.query)
    cursor_admin.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cursor_admin.fetchall():
        cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
        cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
        cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")
        cursor_admin.execute(f"DROP INDEX IF EXISTS idx_{table}_policy_cov;")

def build_policy_indexes():
    LOCAL_PK_MAP = {
        'region':   'r_regionkey',
        'nation':   'n_nationkey',
        'part':     'p_partkey',
        'supplier': 's_suppkey',
        'partsupp': 'ps_partkey, ps_suppkey',
        'customer': 'c_custkey',
        'orders':   'o_orderkey',
        'lineitem': 'l_orderkey, l_linenumber'
    }

    prefix_map = {
        'region': 'r_', 'nation': 'n_', 'part': 'p_',
        'supplier': 's_', 'partsupp': 'ps_',
        'customer': 'c_', 'orders': 'o_', 'lineitem': 'l_'
    }

    index_done = {}

    # ── Policy indexes ────────────────────────────────────────────────────────
    for _, pol_data in global_policies.items():
        predicate = pol_data["predicate"]
        all_cols = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', predicate.lower()))

        for col in all_cols:
            if index_done.get(col):
                continue
            table = TPCH_COLUMN_TO_TABLE[col]
            idx_name = f"idx_{table}_{col}_policy_cov"
            print(f"  -> Building policy index on {table} for column: ({col})", flush=True)
            cursor_admin.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ("{col}");')
            print(cursor_admin.query)
            index_done[col] = True
        cursor_admin.execute(f"ANALYZE {table};")

    # ── PK indexes (skip any col already indexed above) ───────────────────────
    for table, pk_col_str in LOCAL_PK_MAP.items():
        pk_cols = [c.strip() for c in pk_col_str.split(",")]
        # Skip entire PK if every constituent column is already indexed
        if all(index_done.get(c) for c in pk_cols):
            print(f"  -> Skipping PK index on {table}: all PK cols already indexed", flush=True)
            continue
        col_str = ", ".join(f'"{c}"' for c in pk_cols)
        idx_name = f"idx_{table}_pk"
        print(f"  -> Building PK index on {table}: ({', '.join(pk_cols)})", flush=True)
        cursor_admin.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ({col_str});')
        print(cursor_admin.query)
        for c in pk_cols:
            index_done[c] = True
        cursor_admin.execute(f"ANALYZE {table};")

def build_pk_indexes():
    LOCAL_PK_MAP = {
        'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
        'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
        'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
    }
    for table, pk_cols in LOCAL_PK_MAP.items():
        # Split composite keys into clean column list
        cols = [col.strip() for col in pk_cols.split(",")]
        col_str = ", ".join(cols)
        # Create a unique index name per table
        idx_name = f"idx_{table}_pk"
        print(f"  -> Building PK index on {table}: ({col_str})", flush=True)
        cursor_admin.execute(f'CREATE INDEX {idx_name} ON {table} ({col_str});')
        print(cursor_admin.query)
    cursor_admin.execute(f"ANALYZE {table};")

def build_fk_indexes():
    LOCAL_FK_MAP = {
        'nation':   ['n_regionkey'],
        'supplier': ['s_nationkey'],
        'customer': ['c_nationkey'],
        'partsupp': ['ps_partkey', 'ps_suppkey'],
        'orders':   ['o_custkey'],
        'lineitem': ['l_orderkey', 'l_partkey, l_suppkey'],
    }
    for table, fk_cols_list in LOCAL_FK_MAP.items():
        for fk_cols in fk_cols_list:
            cols = [col.strip() for col in fk_cols.split(",")]
            col_str = ", ".join(cols)
            idx_name = f"idx_{table}_fk_{'_'.join(cols)}"
            print(f"  -> Building FK index on {table}: ({col_str})", flush=True)
            cursor_admin.execute(f'CREATE INDEX {idx_name} ON {table} ({col_str});')
            print(cursor_admin.query)
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
build_fk_indexes()
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
restart_postgres()
wait_until_ready()

print("\n--- PHASE 2: Running Exp 1 (Pure Native RLS) ---", flush=True)
# building only PK indexes
build_pk_indexes()
build_fk_indexes()
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
        
    # --- NEW DYNAMIC TIMEOUT LOGIC ---
    if baseline_times[q_id] >= 900.0:
        dyn_timeout_ms = 900000  # Hard cap at 900s if baseline timed out
    else:
        dyn_timeout_ms = int(baseline_times[q_id] * 10 * 1000)  # 10x the baseline
        
    avg_time = run_query_safe(q_data["sql"], timeout_ms=dyn_timeout_ms)
    exp1_times[q_id] = avg_time
    
    if avg_time is None:
        print(f"  [Q{q_id}] Pure RLS Avg: ERR\n", flush=True)
    elif avg_time == float('inf'):
        print(f"  [Q{q_id}] Pure RLS Avg: TIMEOUT\n", flush=True)
    else:
        print(f"  [Q{q_id}] Pure RLS Avg: {avg_time:.4f}s\n", flush=True)

print("\n--- PHASE 3: Running Exp 2 (Secure Views) ---", flush=True)
reset_database()

restart_postgres()
wait_until_ready()



# building only PK indexes
build_pk_indexes()
build_fk_indexes()
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
    # --- NEW DYNAMIC TIMEOUT LOGIC ---
    if baseline_times[q_id] >= 900.0:
        dyn_timeout_ms = 900000  # Hard cap at 900s if baseline timed out
    else:
        dyn_timeout_ms = int(baseline_times[q_id] * 10 * 1000)  # 10x the baseline
        
    avg_time = run_query_safe(view_sql, timeout_ms=dyn_timeout_ms)
    
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
    plt.savefig('postgres_exp2_clean_4P.png', dpi=300)
    print("\nSaved as postgres_exp2_clean_4P.png", flush=True)
