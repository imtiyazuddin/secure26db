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
MAPPING_FILE = "policy_index_mapping.json"
QUERIES_FILE = "queries/all_queries.sql"
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
        "r_regionkey": "region", "r_name": "region", "r_comment": "region",
        # nation
        "n_nationkey": "nation", "n_name": "nation", "n_regionkey": "nation", "n_comment": "nation",
        # part
        "p_partkey": "part", "p_name": "part", "p_mfgr": "part", "p_brand": "part",
        "p_type": "part", "p_size": "part", "p_container": "part", "p_retailprice": "part", "p_comment": "part",
        # supplier
        "s_suppkey": "supplier", "s_name": "supplier", "s_address": "supplier",
        "s_nationkey": "supplier", "s_phone": "supplier", "s_acctbal": "supplier", "s_comment": "supplier",
        # partsupp
        "ps_partkey": "partsupp", "ps_suppkey": "partsupp", "ps_availqty": "partsupp",
        "ps_supplycost": "partsupp", "ps_comment": "partsupp",
        # customer
        "c_custkey": "customer", "c_name": "customer", "c_address": "customer",
        "c_nationkey": "customer", "c_phone": "customer", "c_acctbal": "customer",
        "c_mktsegment": "customer", "c_comment": "customer",
        # orders
        "o_orderkey": "orders", "o_custkey": "orders", "o_orderstatus": "orders",
        "o_totalprice": "orders", "o_orderdate": "orders", "o_orderpriority": "orders",
        "o_clerk": "orders", "o_shippriority": "orders", "o_comment": "orders",
        # lineitem
        "l_orderkey": "lineitem", "l_partkey": "lineitem", "l_suppkey": "lineitem",
        "l_linenumber": "lineitem", "l_quantity": "lineitem", "l_extendedprice": "lineitem",
        "l_discount": "lineitem", "l_tax": "lineitem", "l_returnflag": "lineitem",
        "l_linestatus": "lineitem", "l_shipdate": "lineitem", "l_commitdate": "lineitem",
        "l_receiptdate": "lineitem", "l_shipinstruct": "lineitem", "l_shipmode": "lineitem",
        "l_comment": "lineitem",
    }

print(f"[SYSTEM] Loading policy index mapping from {MAPPING_FILE}...", flush=True)
if os.path.exists(MAPPING_FILE):
    with open(MAPPING_FILE, 'r') as f:
        global_policies = json.load(f)
else:
    print(f"  [!] {MAPPING_FILE} not found! Please run generate_policy_map.py first.", flush=True)
    global_policies = {}

def load_tpch_queries():
    queries_dict = {}
    print(f"[SYSTEM] Loading TPC-H queries from {QUERIES_FILE}...", flush=True)
    if not os.path.exists(QUERIES_FILE):
        print(f"  [!] {QUERIES_FILE} not found.", flush=True)
        return queries_dict
        
    with open(QUERIES_FILE, 'r') as f:
        sql_text = f.read()
    raw_queries = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)).split(';')
    for i, q in enumerate([q.strip() for q in raw_queries if len(q.strip()) > 10]):
        queries_dict[str(i + 1)] = q
    return queries_dict

tpch_queries = load_tpch_queries()

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
    cursor_admin.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cursor_admin.fetchall():
        cursor_admin.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        cursor_admin.execute(f"DROP POLICY IF EXISTS tpch_rls_pol ON {table};")
        cursor_admin.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
        cursor_admin.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")

def build_policy_indexes():
    index_done = {}
    tables_to_analyze = set()

    for _, pol_data in global_policies.items():
        predicate = pol_data.get("predicate", "")
        all_cols = set(re.findall(r'\b([a-z]+_[a-z0-9_]+)\b', predicate.lower()))
        
        for col in all_cols:
            if col not in TPCH_COLUMN_TO_TABLE:
                continue 
                
            if index_done.get(col):
                continue
                
            table = TPCH_COLUMN_TO_TABLE[col]
            tables_to_analyze.add(table)
            idx_name = f"idx_{table}_{col}_policy_cov"
            
            print(f"  -> Building index on {table} for policy column: ({col})", flush=True)
            cursor_admin.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("{col}");')
            index_done[col] = True
            
    for table in tables_to_analyze:
        cursor_admin.execute(f"ANALYZE {table};")

def build_pk_indexes():
    LOCAL_PK_MAP = {
        'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
        'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
        'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
    }
    for table, pk_cols in LOCAL_PK_MAP.items():
        cols = [col.strip() for col in pk_cols.split(",")]
        col_str = ", ".join(cols)
        idx_name = f"idx_{table}_pk"
        print(f"  -> Building PK index on {table}: ({col_str})", flush=True)
        cursor_admin.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col_str});')
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
        clean_sql = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', raw_sql, flags=re.DOTALL)).strip()
        policies[filename] = clean_sql.replace(';', '')
    return policies

# --- EXECUTION ---

baseline_times = {}

print("\n--- Phase 1: Normal Query (22 TPC-H) ---", flush=True)
reset_database()
build_pk_indexes()

# run TPCH 22 queries here

reset_database()
build_policy_indexes()

# run policy queries here

cursor_tester.close()
conn_tester.close()
cursor_admin.close()
conn_admin.close()
