import os
import json
import re
import time
import psycopg2
import psycopg2.errors
import matplotlib.pyplot as plt
import numpy as np
import subprocess
from contextlib import contextmanager

# --- CONFIGURATION ---
HOST_IP = "localhost" 
DB_NAME = "postgres" 
MAPPING_FILE = "experiment_mapping.json"
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
    
    # Unleash 30 cores safely
    cursor_tester.execute("SET max_parallel_workers_per_gather = 30;") 
    cursor_tester.execute("SET work_mem = '1500MB';") 
    cursor_tester.execute("SET enable_nestloop = off;") 
    cursor_tester.execute("SET jit = off;") 
        
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
    index_done = {}

    for _, pol_data in global_policies.items():
        predicate = pol_data["predicate"]
        all_cols = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', predicate.lower()))
        
        for col in all_cols:
            if index_done.get(col):
                continue
            table = TPCH_COLUMN_TO_TABLE[col]
            idx_name = f"idx_{table}_{col}_policy_cov"
            print(f"  -> Building index on {table} for policy column: ({col})", flush=True)
            cursor_admin.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ("{col}");')
            print(cursor_admin.query)
            index_done[col] = True
        
        # Wrapped in try/except in case table variable wasn't set 
        try: cursor_admin.execute(f"ANALYZE {table};")
        except: pass

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
        cursor_admin.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col_str});')
        print(cursor_admin.query)
        cursor_admin.execute(f"ANALYZE {table};")

def load_policy_files(policies_dir="policies"):
    policies = {}
    if not os.path.exists(policies_dir):
        print(f"  [!] Directory '{policies_dir}' not found.", flush=True)
        return policies
        
    for filename in os.listdir(policies_dir):
        if not filename.endswith(".sql"): continue
        filepath = os.path.join(policies_dir, filename)
        with open(filepath, "r") as f:
            raw_sql = f.read()
        # Strip comments safely to get bare SQL for execution
        clean_sql = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', raw_sql, flags=re.DOTALL)).strip()
        policies[filename] = clean_sql.replace(';', '')
    return policies

# --- EXECUTION ---

baseline_times = {}

print("\n--- Phase 1: Normal Query (22 TPC-H) ---", flush=True)
reset_database()
build_pk_indexes()

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
    baseline_times[q_id] = avg_time
    
    if avg_time == float('inf'):
        print(f"  [Q{q_id}] Normal Query: TIMEOUT (> 900s)\n", flush=True)
    elif avg_time is None:
        print(f"  [Q{q_id}] Normal Query: ERROR\n", flush=True)
    else:
        print(f"  [Q{q_id}] Normal Query: {avg_time:.4f}s\n", flush=True)

print("\n--- Phase 2: Policy Queries ---", flush=True)
reset_database()
build_policy_indexes()

policy_queries = load_policy_files()

for filename in sorted(policy_queries.keys()):
    sql = policy_queries[filename]
    print(f"  -> [DEBUG] Firing Policy Query: {filename}", flush=True)
    
    avg_time = run_query_safe(sql, timeout_ms=900000) # 15-Min Hard Limit
    
    if avg_time == float('inf'):
        print(f"  [{filename}] Normal Query: TIMEOUT (> 900s)\n", flush=True)
    elif avg_time is None:
        print(f"  [{filename}] Normal Query: ERROR\n", flush=True)
    else:
        print(f"  [{filename}] Normal Query: {avg_time:.4f}s\n", flush=True)

cursor_tester.close()
conn_tester.close()
cursor_admin.close()
conn_admin.close()
