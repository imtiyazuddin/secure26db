import argparse
import json
import re
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
ADMIN_DB_CONFIG = {
    "dbname":   DB_NAME,
    "user":     DB_OWNER,
    "password": OWNER_PASSWD,
    "host":     HOST_IP,
    "port":     PORT,
}

# ---- Globals (populated in main) ----
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

# ---- DB helpers ----
@contextmanager
def get_connection():
    conn = psycopg2.connect(**ADMIN_DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def run_query_safe(query, timeout_ms=0, num_iters=3):
    if timeout_ms > 0:
        cursor_tester.execute(f"SET statement_timeout = {int(timeout_ms)}")
    else:
        cursor_tester.execute("SET statement_timeout = 0")

    apply_perf_settings()

    times = []
    try:
        for _ in range(num_iters + 1):
            start = time.perf_counter()
            cursor_tester.execute(query)
            print(cursor_tester.query)

            rows = cursor_tester.fetchall()  # list[tuple[str]]


            print("\nPretty EXPLAIN output:")
            print("\n".join(r[0] for r in rows))

            times.append(time.perf_counter() - start)
        return sum(times[1:]) / (num_iters * 1.0)
    except psycopg2.errors.QueryCanceled:
        return float('inf')
    except Exception as e:
        print(f"      [!] Error: {e}".strip(), flush=True)
        return None


def apply_perf_settings():
    cursor_tester.execute("SET maintenance_work_mem = '2GB';")
    cursor_tester.execute("SET default_statistics_target = 500;")
    cursor_tester.execute("SET random_page_cost = 4;")
    cursor_tester.execute("SET effective_io_concurrency = 2;")
    cursor_tester.execute("SET work_mem = '187245kB';")
    cursor_tester.execute("SET max_parallel_workers_per_gather = 15;")


def create_secure_views():
    for table, pol_data in global_policies.items():
        policy_sql  = pol_data["raw_sql"]
        pk_col      = LOCAL_PK_MAP[table]
        pk_left     = f"({pk_col})" if "," in pk_col else pk_col
        bypass_view = f"rls_bypass_view_{table}"

        cursor_admin.execute(f"CREATE OR REPLACE VIEW {bypass_view} AS {policy_sql};")
        cursor_admin.execute(f"GRANT SELECT ON {bypass_view} TO tpch_tester;")
        cursor_admin.execute(
            f"CREATE OR REPLACE VIEW {table}_view AS "
            f"SELECT * FROM {table} WHERE {pk_left} IN (SELECT {pk_col} FROM {bypass_view});"
        )
        print(cursor_admin.query)
        cursor_admin.execute(f"GRANT SELECT ON {table}_view TO tpch_tester;")


def rewrite_for_views(sql):
    modified_sql = sql
    for t in global_policies.keys():
        modified_sql = re.sub(rf'(?i)\bFROM\s+{t}\b',  f'FROM {t}_view',  modified_sql)
        modified_sql = re.sub(rf'(?i)\bJOIN\s+{t}\b',  f'JOIN {t}_view',  modified_sql)
        modified_sql = re.sub(rf'(?i)(,\s*){t}\b',     rf'\g<1>{t}_view', modified_sql)
    return modified_sql


def view_expt():
    print("\n--- PHASE 3: Running Exp 2 (Secure Views) ---", flush=True)
    create_secure_views()

    for i in range(1, 23):
        q_id = str(i)
        if q_id not in queries_dict:
            continue

        q_data = queries_dict[q_id]

        view_sql = rewrite_for_views(q_data["sql"])
        print(f"\n {view_sql}", flush=True)
        run_query_safe(f'EXPLAIN {view_sql}', timeout_ms=9000, num_iters=1)


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
       view_expt()

    finally:
        close_connections()


if __name__ == "__main__":
    main()
