import psycopg2

# --- CONFIGURATION ---
HOST_IP = "localhost"
DB_NAME = "tpch_10gb"

conn_admin = psycopg2.connect(host=HOST_IP, dbname=DB_NAME, user="postgres", password="password", port=5432)
conn_admin.autocommit = True
cursor_admin = conn_admin.cursor()

cursor_admin.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tpch_tester') THEN CREATE ROLE tpch_tester LOGIN; END IF; END $$;")
cursor_admin.execute("ALTER ROLE tpch_tester WITH PASSWORD 'password';")
cursor_admin.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tpch_tester;")

DROP_IDX_SQL = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT n.nspname AS schemaname, c_ind.relname AS indexname,
               format('DROP INDEX %I.%I;', n.nspname, c_ind.relname) AS drop_cmd
        FROM pg_index ind
        JOIN pg_class c_ind ON c_ind.oid = ind.indexrelid
        JOIN pg_namespace n ON n.oid = c_ind.relnamespace
        LEFT JOIN pg_constraint cons ON cons.conindid = ind.indexrelid
        WHERE n.nspname = 'public' AND cons.oid IS NULL
    )
    LOOP
        RAISE INFO '%', r.drop_cmd;
        EXECUTE r.drop_cmd;
    END LOOP;
END $$;
"""

def reset_indexes():
    cursor_admin.execute(DROP_IDX_SQL)
    cursor_admin.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for (table,) in cursor_admin.fetchall():
        cursor_admin.execute(f"DROP INDEX IF EXISTS idx_{table}_policy_cov;")
    print("  Dropped all non-constraint indexes.", flush=True)

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
        cursor_admin.execute(f'CREATE INDEX {idx_name} ON {table} ({col_str});')
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
        cursor_admin.execute(f"ANALYZE {table};")

# --- MAIN ---
print("\nResetting indexes...", flush=True)
reset_indexes()

print("\nBuilding PK indexes...", flush=True)
build_pk_indexes()

print("\nBuilding FK indexes...", flush=True)
build_fk_indexes()

print("\nDone. PK + FK indexes created.", flush=True)

cursor_admin.close()
conn_admin.close()
