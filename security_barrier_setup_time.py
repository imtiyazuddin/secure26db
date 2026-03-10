import argparse
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.errors

SUDO_PASSWORD = "#secure26DB\n" #give linux sudo password
DB_OWNER = "postgres"
OWNER_PASSWD = "password"
HOST_IP = "localhost"
DB_NAME = "postgres"
PORT = 5432
# ---- Configuration ----
BASELINE_TIMEOUT_MS = 3600000  # 1 hour statement_timeout in milliseconds
BASELINE_TIMEOUT_S  = 3600.0    # 1 hour in seconds (for reporting/plots)


ADMIN_DB_CONFIG = {
    "dbname":   DB_NAME,
    "user":     DB_OWNER,
    "password": OWNER_PASSWD,
    "host":     HOST_IP,
    "port":     PORT,
}

# ---- Globals (populated in main) ----
# Tables to exclude from RLS *only in Phase 1 (Baseline)*
BASELINE_EXCLUDE_RLS_TABLES = {"lineitem"}

global_policies  = {}
queries_dict     = {}
baseline_times   = {}
exp1_times       = {}
exp2_times       = {}
cursor_admin     = None
cursor_tester    = None
conn_admin       = None
conn_tester      = None

# ---- Schema maps ----
TPCH_COLUMN_TO_TABLE = {
    "r_regionkey": "region",  "r_name": "region",    "r_comment": "region",
    "n_nationkey": "nation",  "n_name": "nation",    "n_regionkey": "nation",  "n_comment": "nation",
    "p_partkey":   "part",    "p_name": "part",      "p_mfgr": "part",
    "p_brand":     "part",    "p_type": "part",      "p_size": "part",
    "p_container": "part",    "p_retailprice": "part","p_comment": "part",
    "s_suppkey":   "supplier","s_name": "supplier",  "s_address": "supplier",
    "s_nationkey": "supplier","s_phone": "supplier", "s_acctbal": "supplier",  "s_comment": "supplier",
    "ps_partkey":  "partsupp","ps_suppkey": "partsupp","ps_availqty": "partsupp",
    "ps_supplycost":"partsupp","ps_comment": "partsupp",
    "c_custkey":   "customer","c_name": "customer",  "c_address": "customer",
    "c_nationkey": "customer","c_phone": "customer", "c_acctbal": "customer",
    "c_mktsegment":"customer","c_comment": "customer",
    "o_orderkey":  "orders",  "o_custkey": "orders", "o_orderstatus": "orders",
    "o_totalprice":"orders",  "o_orderdate": "orders","o_orderpriority": "orders",
    "o_clerk":     "orders",  "o_shippriority": "orders","o_comment": "orders",
    "l_orderkey":  "lineitem","l_partkey": "lineitem","l_suppkey": "lineitem",
    "l_linenumber":"lineitem","l_quantity": "lineitem","l_extendedprice": "lineitem",
    "l_discount":  "lineitem","l_tax": "lineitem",   "l_returnflag": "lineitem",
    "l_linestatus":"lineitem","l_shipdate": "lineitem","l_commitdate": "lineitem",
    "l_receiptdate":"lineitem","l_shipinstruct": "lineitem","l_shipmode": "lineitem",
    "l_comment":   "lineitem",
}

LOCAL_PK_MAP = {
    'region':   'r_regionkey',
    'nation':   'n_nationkey',
    'part':     'p_partkey',
    'supplier': 's_suppkey',
    'partsupp': 'ps_partkey, ps_suppkey',
    'customer': 'c_custkey',
    'orders':   'o_orderkey',
    'lineitem': 'l_orderkey, l_linenumber',
}

DROP_IDX_SQL = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT format('DROP INDEX %I.%I;', n.nspname, c_ind.relname) AS drop_cmd
        FROM   pg_index ind
        JOIN   pg_class c_ind ON c_ind.oid = ind.indexrelid
        JOIN   pg_namespace n ON n.oid     = c_ind.relnamespace
        LEFT JOIN pg_constraint cons ON cons.conindid = ind.indexrelid
        WHERE  n.nspname = 'public' AND cons.oid IS NULL
    )
    LOOP
        RAISE INFO '%', r.drop_cmd;
        EXECUTE r.drop_cmd;
    END LOOP;
END $$;
"""


# ---- DB helpers ----
@contextmanager
def get_connection():
    conn = psycopg2.connect(**ADMIN_DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


# ---- Restart helpers ----
def restart_postgres():
    print("Restarting PostgreSQL...", flush=True)
    subprocess.run(
        ["sudo", "-S", "systemctl", "restart", "postgresql"],
        input=SUDO_PASSWORD.encode(),
        check=True,
    )
    print("Restart command issued.", flush=True)


def wait_until_ready(timeout=30):
    print("Waiting for PostgreSQL to become ready...", flush=True)
    start = time.time()
    while True:
        try:
            with get_connection():
                print("PostgreSQL is ready.", flush=True)
                return
        except psycopg2.OperationalError:
            if time.time() - start > timeout:
                raise TimeoutError("PostgreSQL did not start in time.")
            time.sleep(1)


# ---- State managers ----
def reset_database():
    cursor_admin.execute(DROP_IDX_SQL)
    print(cursor_admin.query, flush=True)
    cursor_admin.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cursor_admin.fetchall():
        cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
        cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
        cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")
        cursor_admin.execute(f"DROP FUNCTION IF EXISTS rls_bypass_fn_{table}   CASCADE;")
        #cursor_admin.execute(f"DROP INDEX IF EXISTS idx_{table}_policy_cov;")


def build_policy_indexes():
    index_done = {}

    for _, pol_data in global_policies.items():
        predicate = pol_data["predicate"]
        all_cols  = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', predicate.lower()))
        for col in all_cols:
            if index_done.get(col):
                continue
            if col not in TPCH_COLUMN_TO_TABLE:
                continue
            table    = TPCH_COLUMN_TO_TABLE[col]
            idx_name = f"idx_{table}_{col}_policy_cov"
            cursor_admin.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ("{col}");')
            print(cursor_admin.query, flush=True)
            index_done[col] = True
        cursor_admin.execute(f"ANALYZE {table};")

    for table, pk_col_str in LOCAL_PK_MAP.items():
        pk_cols = [c.strip() for c in pk_col_str.split(",")]
        if all(index_done.get(c) for c in pk_cols):
            print(f"  -> Skipping PK index on {table}: all PK cols already indexed", flush=True)
            continue
        col_str  = ", ".join(f'"{c}"' for c in pk_cols)
        idx_name = f"idx_{table}_pk"
        cursor_admin.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ({col_str});')
        print(cursor_admin.query, flush=True)
        for c in pk_cols:
            index_done[c] = True
        cursor_admin.execute(f"ANALYZE {table};")


def build_pk_indexes():
    for table, pk_cols in LOCAL_PK_MAP.items():
        cols     = [col.strip() for col in pk_cols.split(",")]
        col_str  = ", ".join(cols)
        idx_name = f"idx_{table}_pk"
        cursor_admin.execute(f'CREATE INDEX {idx_name} ON {table} ({col_str});')
        print(cursor_admin.query, flush=True)
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
            cols     = [col.strip() for col in fk_cols.split(",")]
            col_str  = ", ".join(cols)
            idx_name = f"idx_{table}_fk_{'_'.join(cols)}"
            cursor_admin.execute(f'CREATE INDEX {idx_name} ON {table} ({col_str});')
            print(cursor_admin.query, flush=True)
        cursor_admin.execute(f"ANALYZE {table};")



# ---- RLS disable helper (used to exclude tables from RLS) ----
def disable_rls_for_table(table: str):
    """Drop the benchmark policy and disable RLS for a specific table.

    Used when excluding a hot table (e.g., lineitem) from RLS to isolate
    performance during benchmarking.
    """
    cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
    cursor_admin.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
    cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    # Also drop any artifacts from view/bypass experiments
    cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
    cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")
    cursor_admin.execute(f"DROP FUNCTION IF EXISTS rls_bypass_fn_{table} CASCADE;")

def apply_rls():
    start_time = time.perf_counter()
    for table, pol_data in global_policies.items():
        policy_sql = pol_data["raw_sql"]
        pk_col     = LOCAL_PK_MAP[table]
        bypass_fn  = f"rls_bypass_fn_{table}"

        if "," in pk_col:
            pk_cols   = [c.strip() for c in pk_col.split(",")]
            col_types = {
                "l_orderkey":   "bigint",
                "l_linenumber": "bigint",
                "ps_partkey":   "bigint",
                "ps_suppkey":   "bigint",
            }
            params = ", ".join(f"p_{c} {col_types.get(c, 'bigint')}" for c in pk_cols)
            where  = " AND ".join(f"{c} = p_{c}" for c in pk_cols)
            fn_sql = f"""
                CREATE OR REPLACE FUNCTION {bypass_fn}({params})
                RETURNS BOOLEAN LANGUAGE SQL SECURITY DEFINER STABLE AS $$
                    SELECT EXISTS (
                        SELECT 1 FROM ({policy_sql}) AS _filtered
                        WHERE {where}
                    );
                $$;
            """
            actual_rls_predicate = f"{bypass_fn}(" + ", ".join(pk_cols) + ")"
            cursor_admin.execute(fn_sql)
            cursor_admin.execute(f"GRANT EXECUTE ON FUNCTION {bypass_fn} TO tpch_tester;")
        else:
            col_types = {
                "o_orderkey": "bigint",
                "c_custkey":  "bigint",
                "s_suppkey":  "bigint",
                "p_partkey":  "bigint",
            }
            pk_type = col_types.get(pk_col, "bigint")
            fn_sql = f"""
                CREATE OR REPLACE FUNCTION {bypass_fn}(p_{pk_col} {pk_type})
                RETURNS BOOLEAN LANGUAGE SQL SECURITY DEFINER STABLE AS $$
                    SELECT EXISTS (
                        SELECT 1 FROM ({policy_sql}) AS _filtered
                        WHERE {pk_col} = p_{pk_col}
                    );
                $$;
            """
            actual_rls_predicate = f"{bypass_fn}({pk_col})"

        cursor_admin.execute(fn_sql)
        cursor_admin.execute(f"GRANT EXECUTE ON FUNCTION {bypass_fn} TO tpch_tester;")

        print(f"  -> [LOG] Securing {table}", flush=True)
        print(f"     |-- Applied Policy: USING ({actual_rls_predicate})", flush=True)

        cursor_admin.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        cursor_admin.execute(
            f"CREATE POLICY tpch_rls_pol ON {table} FOR SELECT "
            f"USING ({actual_rls_predicate});"
        )
        cursor_admin.execute(f"ANALYZE {table};")
    dur = time.perf_counter() - start_time
    print(f"  -> [LOG] Apply RLS Done in {dur} seconds", flush=True)
    return dur


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

# ---- Experiment phases ----
def indexed_RLS_expt():
    print("\n--- PHASE 1: Running Baseline (Indexed RLS) ---", flush=True)
    build_policy_indexes()
    build_fk_indexes()
    dur = apply_rls()

    """
    # Exclude selected tables from RLS in baseline (e.g., lineitem)
    for t in BASELINE_EXCLUDE_RLS_TABLES:
        print(f" -> [LOG] Baseline excluding {t}: dropping policy and disabling RLS", flush=True)
        disable_rls_for_table(t)

    for i in range(1, 23):
        q_id = str(i)
        if q_id not in queries_dict:
            print(f"  [Q{i}] Skipped: Does not touch protected tables.", flush=True)
            continue

        q_data = queries_dict[q_id]
        print(f"  -> [DEBUG] Firing Q{q_id}. Active Predicates:", flush=True)
        for tbl, pol in q_data.get("applied_policies", {}).items():
            clean_pred = pol["raw_sql"].replace('\n', ' ').strip()
            print(f"       |-- {tbl}: {clean_pred}", flush=True)

        avg_time, _metrics = run_phase_query_explain(q_data['sql'], q_id, 'phase1', 'baseline', timeout_ms=BASELINE_TIMEOUT_MS)

        if avg_time == float('inf'):
            baseline_times[q_id] = BASELINE_TIMEOUT_S
            print(f"  [Q{q_id}] Indexed RLS Baseline: TIMEOUT (> 3600s)\n", flush=True)
        elif avg_time is None:
            print(f"  [Q{q_id}] Indexed RLS Baseline: ERR\n", flush=True)
        else:
            baseline_times[q_id] = avg_time
            print(f"  [Q{q_id}] Indexed RLS Baseline: {avg_time:.4f}s\n", flush=True)
    """
    return dur


def pure_RLS_expt():
    print("\n--- PHASE 2: Running Exp 1 (Pure Native RLS) ---", flush=True)
    build_pk_indexes()
    build_fk_indexes()
    dur = apply_rls()

    """
    for i in range(1, 23):
        q_id = str(i)
        if q_id not in queries_dict or q_id not in baseline_times:
            continue

        q_data = queries_dict[q_id]
        print(f"  -> [DEBUG] Firing Q{q_id} (Pure RLS). Active Predicates:", flush=True)
        for tbl, pol in q_data.get("applied_policies", {}).items():
            clean_pred = pol["raw_sql"].replace('\n', ' ').strip()
            print(f"       |-- {tbl}: {clean_pred}", flush=True)

        dyn_timeout_ms = (
            BASELINE_TIMEOUT_MS if baseline_times[q_id] >= BASELINE_TIMEOUT_S
            else int(baseline_times[q_id] * 15 * 1000)
        )
        avg_time, _metrics = run_phase_query_explain(q_data['sql'], q_id, 'phase2', 'pure_rls', timeout_ms=dyn_timeout_ms)
        exp1_times[q_id] = avg_time

        if avg_time is None:
            print(f"  [Q{q_id}] Pure RLS Avg: ERR\n", flush=True)
        elif avg_time == float('inf'):
            print(f"  [Q{q_id}] Pure RLS Avg: TIMEOUT\n", flush=True)
        else:
            print(f"  [Q{q_id}] Pure RLS Avg: {avg_time:.4f}s\n", flush=True)
    """
    return dur

# ---- Main ----
def parse_args():
    parser = argparse.ArgumentParser(
        description="TPC-H Benchmark Runner",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "mapping_file",
        help="Path to experiment_mapping.json",
    )
    return parser.parse_args()


def init_connections():
    global conn_admin, cursor_admin, conn_tester, cursor_tester

    conn_admin = psycopg2.connect(
        host=HOST_IP, dbname=DB_NAME,
        user=DB_OWNER, password=OWNER_PASSWD, port=5432,
    )
    conn_admin.autocommit = True
    cursor_admin = conn_admin.cursor()

    cursor_admin.execute(
        "DO $$ BEGIN IF NOT EXISTS "
        "(SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tpch_tester') "
        "THEN CREATE ROLE tpch_tester LOGIN; END IF; END $$;"
    )
    cursor_admin.execute("ALTER ROLE tpch_tester WITH PASSWORD 'password';")
    cursor_admin.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tpch_tester;")

    conn_tester = psycopg2.connect(
        host=HOST_IP, dbname=DB_NAME,
        user="tpch_tester", password="password", port=5432 )
    conn_tester.autocommit = True
    cursor_tester = conn_tester.cursor()


def close_connections():
    cursor_tester.close()
    conn_tester.close()
    cursor_admin.close()
    conn_admin.close()


def main():
    global global_policies, queries_dict

    args = parse_args()

    print(f"[SYSTEM] Loading execution plan from {args.mapping_file}...", flush=True)
    with open(args.mapping_file, 'r') as f:
        plan = json.load(f)

    global_policies = plan["policies"]
    queries_dict    = plan["queries"]

    init_connections()

    try:
            reset_database()
            dur = indexed_RLS_expt()
            reset_database()
            close_connections()
            restart_postgres()
            wait_until_ready()
            init_connections()
            dur = dur + pure_RLS_expt()

            print("[LOG] Apply RLS AVG time: {:.4f}s".format(dur/2), flush=True)
            reset_database()
            close_connections()
    finally:
        close_connections()


if __name__ == "__main__":
    main()
