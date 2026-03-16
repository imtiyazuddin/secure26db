#!/usr/bin/env python3
"""
Compare RLS-enforced query results vs manually injected predicate query results.

This script:
1. Creates RLS policies and enables RLS before each query
2. Runs TPC-H query with RLS enabled (as rls_user)
3. Drops policies and disables RLS after each query
4. Runs the same query with manual predicates (as postgres, RLS bypassed)
5. Compares results and reports differences

Usage:
    python compare_rls_vs_manual.py [--query N] [--verbose]
"""

import psycopg2
import argparse
import hashlib
import json
import re
from typing import List, Tuple, Any, Optional

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tpch_1gb',
    'user': 'postgres',
    'password': 'postgres'
}

RLS_USER = 'rls_user'
RLS_PASSWORD = 'rls_user'

# ============================================================================
# RLS Policy Setup/Teardown SQL
# ============================================================================
RLS_SETUP_SQL = """
-- Create rls_user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rls_user') THEN
        CREATE ROLE rls_user LOGIN PASSWORD 'rls_user';
    END IF;
END
$$;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO rls_user;
GRANT USAGE ON SCHEMA fresh TO rls_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO rls_user;
GRANT SELECT ON ALL TABLES IN SCHEMA fresh TO rls_user;

-- Drop existing policies (clean slate)
DROP POLICY IF EXISTS customer_tiered_policy ON customer;
DROP POLICY IF EXISTS supplier_tiered_policy ON supplier;
DROP POLICY IF EXISTS partsupp_tiered_policy ON partsupp;
DROP POLICY IF EXISTS lineitem_tiered_policy ON lineitem;

-- Disable RLS first
ALTER TABLE customer DISABLE ROW LEVEL SECURITY;
ALTER TABLE supplier DISABLE ROW LEVEL SECURITY;
ALTER TABLE partsupp DISABLE ROW LEVEL SECURITY;
ALTER TABLE lineitem DISABLE ROW LEVEL SECURITY;

-- P1: CUSTOMER (Tier 1)
CREATE POLICY customer_tiered_policy ON customer
    FOR SELECT TO rls_user
    USING (
        c_acctbal > 0
        AND EXISTS (
            SELECT 1 FROM nation n, region r
            WHERE n.n_nationkey = c_nationkey
              AND n.n_regionkey = r.r_regionkey
              AND r.r_name IN ('EUROPE', 'AMERICA')
        )
    );

-- P2: SUPPLIER (Tier 1)
CREATE POLICY supplier_tiered_policy ON supplier
    FOR SELECT TO rls_user
    USING (
        s_acctbal > 0
        AND EXISTS (
            SELECT 1 FROM nation n, region r
            WHERE n.n_nationkey = s_nationkey
              AND n.n_regionkey = r.r_regionkey
              AND r.r_name = 'EUROPE'
        )
    );

-- P4: PARTSUPP (Tier 2)
CREATE POLICY partsupp_tiered_policy ON partsupp
    FOR SELECT TO rls_user
    USING (
        ps_availqty > 100
        AND EXISTS (
            SELECT 1 FROM supplier s
            WHERE s.s_suppkey = ps_suppkey
              AND s.s_acctbal > 0
        )
    );

-- P3: LINEITEM (Tier 3)
CREATE POLICY lineitem_tiered_policy ON lineitem
    FOR SELECT TO rls_user
    USING (
        EXISTS (
            SELECT 1 FROM orders o
            WHERE o.o_orderkey = l_orderkey
              AND o.o_orderpriority IN ('1-URGENT', '2-HIGH')
        )
        AND EXISTS (
            SELECT 1 FROM partsupp ps
            WHERE ps.ps_partkey = l_partkey
              AND ps.ps_suppkey = l_suppkey
              AND ps.ps_availqty > 0
        )
    );

-- Enable RLS
ALTER TABLE customer ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier ENABLE ROW LEVEL SECURITY;
ALTER TABLE partsupp ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineitem ENABLE ROW LEVEL SECURITY;
"""

RLS_TEARDOWN_SQL = """
-- Drop policies
DROP POLICY IF EXISTS customer_tiered_policy ON customer;
DROP POLICY IF EXISTS supplier_tiered_policy ON supplier;
DROP POLICY IF EXISTS partsupp_tiered_policy ON partsupp;
DROP POLICY IF EXISTS lineitem_tiered_policy ON lineitem;

-- Disable RLS
ALTER TABLE customer DISABLE ROW LEVEL SECURITY;
ALTER TABLE supplier DISABLE ROW LEVEL SECURITY;
ALTER TABLE partsupp DISABLE ROW LEVEL SECURITY;
ALTER TABLE lineitem DISABLE ROW LEVEL SECURITY;
"""

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


def create_secure_views(conn, view_create_sql: str):
    """Execute the CREATE VIEW statements extracted from the log file."""
    with conn.cursor() as cur:
        for stmt in view_create_sql:
            cur.execute(stmt)


def drop_secure_views(conn, view_tables: list):
    """Drop the secure views and bypass views."""
    with conn.cursor() as cur:
        for table in view_tables:
            cur.execute(f"DROP VIEW IF EXISTS {table}_view CASCADE;")
            cur.execute(f"DROP VIEW IF EXISTS rls_bypass_view_{table} CASCADE;")


def load_view_log(filepath: str):
    """Parse vew_queries_log.txt and return (view_create_stmts, view_queries).

    Returns:
        view_create_stmts: list of CREATE OR REPLACE VIEW SQL strings
        view_queries: dict mapping query number (int) -> rewritten SQL string
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    # --- Extract VIEW DEFINITIONS section ---
    view_section_match = re.search(
        r'--- VIEW DEFINITIONS ---(.*?)--- REWRITTEN QUERIES ---',
        content, re.DOTALL
    )
    view_create_stmts = []
    if view_section_match:
        view_block = view_section_match.group(1)
        # Each statement ends with ';' — split on statement boundaries
        for stmt in re.split(r';\s*\n', view_block):
            stmt = stmt.strip()
            # Strip any leading comment lines (e.g. "-- customer")
            sql_lines = [l for l in stmt.splitlines() if not l.strip().startswith('--')]
            sql = '\n'.join(sql_lines).strip()
            if sql:
                view_create_stmts.append(sql)

    # --- Extract REWRITTEN QUERIES section ---
    queries_section_match = re.search(
        r'--- REWRITTEN QUERIES ---(.*)',
        content, re.DOTALL
    )
    view_queries = {}
    if queries_section_match:
        queries_block = queries_section_match.group(1)
        # Split on -- Q{N} markers
        parts = re.split(r'(?=^-- Q\d+$)', queries_block, flags=re.MULTILINE)
        for part in parts:
            m = re.match(r'^-- Q(\d+)$', part.strip().split('\n')[0].strip())
            if not m:
                continue
            qnum = int(m.group(1))
            # Everything after the marker line is the SQL
            lines = part.strip().split('\n')[1:]  # skip the -- QN header
            sql = '\n'.join(lines).strip().rstrip(';')
            if sql:
                view_queries[qnum] = sql

    return view_create_stmts, view_queries


# ============================================================================
# TPC-H Queries (original - will have RLS applied)
# ============================================================================
ORIGINAL_QUERIES = {
    1: """SELECT
        l_returnflag,
        l_linestatus,
        sum(l_quantity) as sum_qty,
        sum(l_extendedprice) as sum_base_price,
        sum(l_extendedprice * (1 - l_discount)) as sum_disc_price,
        sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) as sum_charge,
        avg(l_quantity) as avg_qty,
        avg(l_extendedprice) as avg_price,
        avg(l_discount) as avg_disc,
        count(*) as count_order
FROM lineitem
WHERE l_shipdate <= date '1998-12-01' - interval '3' day
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus""",

    2: """SELECT
        s_acctbal, s_name, n_name, p_partkey, p_mfgr,
        s_address, s_phone, s_comment
FROM part, supplier, partsupp, nation, region
WHERE p_partkey = ps_partkey
    AND s_suppkey = ps_suppkey
    AND p_size = 15
    AND p_type like '%BRASS'
    AND s_nationkey = n_nationkey
    AND n_regionkey = r_regionkey
    AND r_name = 'EUROPE'
    AND ps_supplycost = (
        SELECT min(ps_supplycost)
        FROM partsupp, supplier, nation, region
        WHERE p_partkey = ps_partkey
            AND s_suppkey = ps_suppkey
            AND s_nationkey = n_nationkey
            AND n_regionkey = r_regionkey
            AND r_name = 'EUROPE'
    )
ORDER BY s_acctbal desc, n_name, s_name, p_partkey
LIMIT 100""",

    3: """SELECT
        l_orderkey,
        sum(l_extendedprice * (1 - l_discount)) as revenue,
        o_orderdate,
        o_shippriority
FROM customer, orders, lineitem
WHERE c_mktsegment = 'FURNITURE'
    AND c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND o_orderdate < date '1995-01-01'
    AND l_shipdate > date '1995-01-01'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue desc, o_orderdate""",

    4: """SELECT
        o_orderpriority,
        count(*) as order_count
FROM orders
WHERE o_orderdate >= date '1994-01-01'
    AND o_orderdate < date '1994-01-01' + interval '3' month
    AND exists (
        SELECT * FROM lineitem
        WHERE l_orderkey = o_orderkey
            AND l_commitdate < l_receiptdate
    )
GROUP BY o_orderpriority
ORDER BY o_orderpriority""",

    5: """SELECT
        n_name,
        sum(l_extendedprice * (1 - l_discount)) as revenue
FROM customer, orders, lineitem, supplier, nation, region
WHERE c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND l_suppkey = s_suppkey
    AND c_nationkey = s_nationkey
    AND s_nationkey = n_nationkey
    AND n_regionkey = r_regionkey
    AND r_name = 'ASIA'
    AND o_orderdate >= date '1995-01-01'
    AND o_orderdate < date '1995-01-01' + interval '1' year
GROUP BY n_name
ORDER BY revenue desc""",

    6: """SELECT
        sum(l_extendedprice * l_discount) as revenue
FROM lineitem
WHERE l_shipdate >= date '1993-01-01'
    AND l_shipdate < date '1994-03-01' + interval '1' year
    AND l_discount between 0.06 - 0.01 and 0.06 + 0.01
    AND l_quantity < 10""",

    7: """SELECT
        supp_nation, cust_nation, l_year, sum(volume) as revenue
FROM (
    SELECT
        n1.n_name as supp_nation,
        n2.n_name as cust_nation,
        extract(year from l_shipdate) as l_year,
        l_extendedprice * (1 - l_discount) as volume
    FROM supplier, lineitem, orders, customer, nation n1, nation n2
    WHERE s_suppkey = l_suppkey
        AND o_orderkey = l_orderkey
        AND c_custkey = o_custkey
        AND s_nationkey = n1.n_nationkey
        AND c_nationkey = n2.n_nationkey
        AND ((n1.n_name = 'GERMANY' and n2.n_name = 'FRANCE')
            or (n1.n_name = 'FRANCE' and n2.n_name = 'GERMANY'))
        AND l_shipdate between date '1995-01-01' and date '1996-12-31'
) as shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year""",

    8: """SELECT
        o_year,
        sum(case when nation = 'INDIA' then volume else 0 end) / sum(volume) as mkt_share
FROM (
    SELECT
        extract(year from o_orderdate) as o_year,
        l_extendedprice * (1 - l_discount) as volume,
        n2.n_name as nation
    FROM part, supplier, lineitem, orders, customer, nation n1, nation n2, region
    WHERE p_partkey = l_partkey
        AND s_suppkey = l_suppkey
        AND l_orderkey = o_orderkey
        AND o_custkey = c_custkey
        AND c_nationkey = n1.n_nationkey
        AND n1.n_regionkey = r_regionkey
        AND r_name = 'ASIA'
        AND s_nationkey = n2.n_nationkey
        AND o_orderdate between date '1995-01-01' and date '1996-12-31'
        AND p_type = 'ECONOMY ANODIZED STEEL'
) as all_nations
GROUP BY o_year
ORDER BY o_year""",

    9: """SELECT
        nation, o_year, sum(amount) as sum_profit
FROM (
    SELECT
        n_name as nation, p_name,
        extract(year from o_orderdate) as o_year,
        l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity as amount
    FROM part, supplier, lineitem, partsupp, orders, nation
    WHERE s_suppkey = l_suppkey
        AND ps_suppkey = l_suppkey
        AND ps_partkey = l_partkey
        AND p_partkey = l_partkey
        AND o_orderkey = l_orderkey
        AND s_nationkey = n_nationkey
        AND p_name like 'co%'
) as profit
GROUP BY nation, o_year
ORDER BY nation, o_year desc""",

    10: """SELECT
        c_custkey, c_name,
        sum(l_extendedprice * (1 - l_discount)) as revenue,
        c_acctbal, n_name, c_address, c_phone, c_comment
FROM customer, orders, lineitem, nation
WHERE c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND o_orderdate >= date '1995-01-01'
    AND o_orderdate < date '1995-01-01' + interval '3' month
    AND l_returnflag = 'R'
    AND c_nationkey = n_nationkey
GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment
ORDER BY revenue desc""",

    11: """SELECT
    ps_partkey, n_name,
    SUM(ps_supplycost * ps_availqty) AS total_value
FROM partsupp, supplier, nation
WHERE ps_suppkey = s_suppkey
    AND s_nationkey = n_nationkey
    AND n_name = 'INDIA'
GROUP BY ps_partkey, n_name
HAVING SUM(ps_supplycost * ps_availqty) > (
    SELECT SUM(ps_supplycost * ps_availqty) * 0.00001
    FROM partsupp, supplier, nation
    WHERE ps_suppkey = s_suppkey
        AND s_nationkey = n_nationkey
        AND n_name = 'INDIA'
)
ORDER BY total_value DESC""",

    12: """SELECT
        l_shipmode,
        sum(case when o_orderpriority = '1-URGENT' or o_orderpriority = '2-HIGH' then 1 else 0 end) as high_line_count,
        sum(case when o_orderpriority <> '1-URGENT' and o_orderpriority <> '2-HIGH' then 1 else 0 end) as low_line_count
FROM orders, lineitem
WHERE o_orderkey = l_orderkey
    AND l_shipmode = 'SHIP'
    AND l_commitdate < l_receiptdate
    AND l_shipdate < l_commitdate
    AND l_receiptdate >= date '1995-01-01'
    AND l_receiptdate < date '1995-01-01' + interval '1' year
GROUP BY l_shipmode
ORDER BY l_shipmode""",

    13: """SELECT
        c_count, c_orderdate, count(*) as custdist
FROM (
    SELECT c_custkey, count(o_orderkey), o_orderdate
    FROM customer left outer join orders on
        c_custkey = o_custkey
        AND o_comment not like '%special%requests%'
    GROUP BY c_custkey, o_orderdate
) as c_orders (c_custkey, c_count, c_orderdate)
GROUP BY c_count, c_orderdate
ORDER BY custdist desc, c_count desc""",

    14: """SELECT
        100.00 * sum(case when p_type like 'PROMO%' then l_extendedprice * (1 - l_discount) else 0 end) / sum(l_extendedprice * (1 - l_discount)) as promo_revenue
FROM lineitem, part
WHERE l_partkey = p_partkey
    AND l_shipdate >= date '1995-01-01'
    AND l_shipdate < date '1995-01-01' + interval '1' month""",

    15: """WITH revenue(supplier_no, total_revenue) AS (
    SELECT l_suppkey, sum(l_extendedprice * (1 - l_discount))
    FROM lineitem
    WHERE l_shipdate >= date '1995-01-01'
        AND l_shipdate < date '1995-01-01' + interval '3' month
    GROUP BY l_suppkey
)
SELECT s_suppkey, s_name, s_address, s_phone, total_revenue
FROM supplier, revenue
WHERE s_suppkey = supplier_no
    AND total_revenue = (SELECT max(total_revenue) FROM revenue)
ORDER BY s_suppkey""",

    16: """SELECT
        p_brand, p_type, p_size,
        count(distinct ps_suppkey) as supplier_cnt
FROM partsupp, part
WHERE p_partkey = ps_partkey
    AND p_brand <> 'Brand#23'
    AND p_type NOT LIKE 'MEDIUM POLISHED%'
    AND p_size IN (1, 4, 7)
    AND ps_suppkey not in (
        SELECT s_suppkey FROM supplier
        WHERE s_comment like '%Customer%Complaints%'
    )
GROUP BY p_brand, p_type, p_size
ORDER BY supplier_cnt desc, p_brand, p_type, p_size""",

    17: """SELECT
        sum(l_extendedprice) / 7.0 as avg_yearly
FROM lineitem, part
WHERE p_partkey = l_partkey
    AND p_brand = 'Brand#53'
    AND p_container = 'MED BAG'
    AND l_quantity < (
        SELECT 0.7 * avg(l_quantity)
        FROM lineitem
        WHERE l_partkey = p_partkey
    )""",

    18: """SELECT
        c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice, sum(l_quantity)
FROM customer, orders, lineitem
WHERE o_orderkey in (
    SELECT l_orderkey FROM lineitem
    GROUP BY l_orderkey
    HAVING sum(l_quantity) > 300
)
    AND c_custkey = o_custkey
    AND o_orderkey = l_orderkey
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice desc, o_orderdate""",

    19: """SELECT
        sum(l_extendedprice* (1 - l_discount)) as revenue
FROM lineitem, part
WHERE (
        p_partkey = l_partkey
        AND p_brand = 'Brand#12'
        AND p_container in ('SM CASE', 'SM BOX', 'SM PACK', 'SM PKG')
        AND l_quantity >= 1 AND l_quantity <= 1 + 10
        AND p_size between 1 and 5
        AND l_shipmode in ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    ) OR (
        p_partkey = l_partkey
        AND p_brand = 'Brand#23'
        AND p_container in ('MED BAG', 'MED BOX', 'MED PKG', 'MED PACK')
        AND l_quantity >= 10 AND l_quantity <= 10 + 10
        AND p_size between 1 and 10
        AND l_shipmode in ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    ) OR (
        p_partkey = l_partkey
        AND p_brand = 'Brand#34'
        AND p_container in ('LG CASE', 'LG BOX', 'LG PACK', 'LG PKG')
        AND l_quantity >= 20 AND l_quantity <= 20 + 10
        AND p_size between 1 and 15
        AND l_shipmode in ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    )""",

    20: """SELECT
        s_name, s_address
FROM supplier, nation
WHERE s_suppkey in (
    SELECT ps_suppkey FROM partsupp
    WHERE ps_partkey in (
        SELECT p_partkey FROM part WHERE p_name like '%ivory%'
    )
    AND ps_availqty > (
        SELECT 0.5 * sum(l_quantity) FROM lineitem
        WHERE l_partkey = ps_partkey
            AND l_suppkey = ps_suppkey
            AND l_shipdate >= date '1995-01-01'
            AND l_shipdate < date '1995-01-01' + interval '1' year
    )
)
    AND s_nationkey = n_nationkey
    AND n_name = 'FRANCE'
ORDER BY s_name""",

    21: """SELECT
        s_name, count(*) as numwait
FROM supplier, lineitem l1, orders, nation
WHERE s_suppkey = l1.l_suppkey
    AND o_orderkey = l1.l_orderkey
    AND o_orderstatus = 'F'
    AND l1.l_receiptdate > l1.l_commitdate
    AND exists (
        SELECT * FROM lineitem l2
        WHERE l2.l_orderkey = l1.l_orderkey
            AND l2.l_suppkey <> l1.l_suppkey
    )
    AND not exists (
        SELECT * FROM lineitem l3
        WHERE l3.l_orderkey = l1.l_orderkey
            AND l3.l_suppkey <> l1.l_suppkey
            AND l3.l_receiptdate > l3.l_commitdate
    )
    AND s_nationkey = n_nationkey
    AND n_name = 'ARGENTINA'
GROUP BY s_name
ORDER BY numwait desc, s_name""",

    22: """SELECT
        cntrycode, count(*) as numcust, sum(c_acctbal) as totacctbal
FROM (
    SELECT substring(c_phone from 1 for 2) as cntrycode, c_acctbal
    FROM customer
    WHERE substring(c_phone from 1 for 2) in ('13', '31', '23', '29', '30', '18', '17')
        AND c_acctbal > (
            SELECT avg(c_acctbal) FROM customer
            WHERE c_acctbal > 0.00
                AND substring(c_phone from 1 for 2) in ('13', '31', '23', '29', '30', '18', '17')
        )
        AND not exists (
            SELECT * FROM orders WHERE o_custkey = c_custkey
        )
) as custsale
GROUP BY cntrycode
ORDER BY cntrycode""",
}


def load_manual_queries(filepath: str) -> dict:
    """Load manually injected predicate queries from file."""
    import re
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    queries = {}
    # Split by query markers (lines starting with -- === followed by Qn:)
    # Pattern: -- ==...== followed by -- Qn: header
    parts = re.split(r'(?=-- =+\n-- Q\d+:)', content)
    
    for part in parts:
        # Look for Qn: pattern anywhere in the part
        match = re.search(r'-- Q(\d+):', part)
        if match:
            qnum = int(match.group(1))
            
            # Find the SQL: everything between the header comments and the end/next section
            lines = part.strip().split('\n')
            sql_lines = []
            in_sql = False
            
            for line in lines:
                stripped = line.strip()
                # Skip comment lines at the start
                if stripped.startswith('-- ') or stripped.startswith('--') and not stripped.startswith('---'):
                    if in_sql:
                        # Comment after SQL started - might be inline comment, include it
                        sql_lines.append(line)
                    continue
                if stripped == '':
                    if in_sql:
                        sql_lines.append(line)
                    continue
                # Start of SQL
                in_sql = True
                sql_lines.append(line)
            
            sql = '\n'.join(sql_lines).strip()
            if sql.endswith(';'):
                sql = sql[:-1]  # Remove trailing semicolon
            if sql:
                queries[qnum] = sql
    
    return queries


def get_result_hash(rows: List[Tuple]) -> str:
    """Generate a hash of query results for comparison (order-insensitive)."""
    sorted_rows = sorted([list(map(str, row)) for row in rows])
    result_str = json.dumps(sorted_rows, sort_keys=True)
    return hashlib.md5(result_str.encode()).hexdigest()


def compare_results(rows1: List[Tuple], rows2: List[Tuple], label2: str = "Manual") -> Tuple[bool, str]:
    """Compare two result sets and return (match, description)."""
    if len(rows1) != len(rows2):
        return False, f"Row count mismatch: RLS={len(rows1)}, {label2}={len(rows2)}"
    
    if len(rows1) == 0:
        return True, "Both empty"
    
    # Compare hashes first (fast)
    hash1 = get_result_hash(rows1)
    hash2 = get_result_hash(rows2)
    
    if hash1 == hash2:
        return True, f"Match ({len(rows1)} rows)"
    
    # Find differences
    set1 = set(tuple(map(str, row)) for row in rows1)
    set2 = set(tuple(map(str, row)) for row in rows2)
    
    only_in_rls = set1 - set2
    only_in_manual = set2 - set1

    if not only_in_rls and not only_in_manual:
        return True, f"Match ({len(rows1)} rows, order differs)"

    desc = f"Mismatch: {len(only_in_rls)} only in RLS, {len(only_in_manual)} only in {label2}"
    return False, desc


def run_query(conn, query: str) -> Tuple[List[Tuple], Optional[str]]:
    """Execute a query and return (results, error)."""
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            return rows, None
    except Exception as e:
        return [], str(e)


def main():
    parser = argparse.ArgumentParser(description='Compare RLS vs Manual predicate queries')
    parser.add_argument('--query', '-q', type=int, help='Run only specific query number')
    parser.add_argument('--skip', '-s', type=int, nargs='+', default=[], help='Skip specific query numbers')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--manual-file', default='queries/all_queries_with_tiered_predicates.sql',
                        help='Path to manual predicate queries file')
    parser.add_argument('--view-log', default='vew_queries_log.txt',
                        help='Path to view queries log file (vew_queries_log.txt)')
    args = parser.parse_args()
    
    # Load manual queries
    print(f"Loading manual queries from: {args.manual_file}")
    try:
        manual_queries = load_manual_queries(args.manual_file)
        print(f"Loaded {len(manual_queries)} manual queries")
    except Exception as e:
        print(f"Error loading manual queries: {e}")
        return

    # Load policies for secure view creation
    print(f"Loading view queries from: {args.view_log}")
    try:
        view_create_stmts, view_queries = load_view_log(args.view_log)
        view_tables = [re.sub(r'_view$', '', t) for t in
                       re.findall(r'CREATE OR REPLACE VIEW (\w+_view)\b', ' '.join(view_create_stmts))]
        print(f"Loaded {len(view_create_stmts)} CREATE VIEW statements, {len(view_queries)} rewritten queries")
    except Exception as e:
        print(f"Error loading view log: {e}")
        return
    
    # Connect as postgres first (for setup/teardown)
    print("\nConnecting to database...")
    try:
        conn_postgres = psycopg2.connect(**DB_CONFIG)
        conn_postgres.autocommit = True
        with conn_postgres.cursor() as cur:
            cur.execute("SET search_path TO fresh, public")
        print(f"  Connected as postgres (for RLS setup/teardown)")
    except Exception as e:
        print(f"Error connecting as postgres: {e}")
        return
    
    # Ensure rls_user exists before attempting to connect
    try:
        with conn_postgres.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rls_user') THEN
                        CREATE ROLE rls_user LOGIN PASSWORD 'rls_user';
                    END IF;
                END
                $$;
                GRANT USAGE ON SCHEMA public TO rls_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA public TO rls_user;
            """)
        print("  Ensured rls_user exists")
    except Exception as e:
        print(f"Warning: Could not create rls_user: {e}")
    
    # Connect as RLS user
    rls_config = DB_CONFIG.copy()
    rls_config['user'] = RLS_USER
    rls_config['password'] = RLS_PASSWORD
    
    try:
        conn_rls = psycopg2.connect(**rls_config)
        conn_rls.autocommit = True
        with conn_rls.cursor() as cur:
            cur.execute("SET search_path TO fresh, public")
        print(f"  Connected as {RLS_USER} (for RLS queries)")
    except Exception as e:
        print(f"Error connecting as rls_user: {e}")
        conn_postgres.close()
        return
    
    # Run comparisons
    print("\n" + "=" * 70)
    print("COMPARING RESULTS")
    print("=" * 70)
    
    queries_to_run = [args.query] if args.query else sorted(ORIGINAL_QUERIES.keys())
    queries_to_run = [q for q in queries_to_run if q not in args.skip]
    
    results_summary = []
    
    for qnum in queries_to_run:
        if qnum not in ORIGINAL_QUERIES:
            print(f"\nQ{qnum}: Not found in original queries")
            continue
        if qnum not in manual_queries:
            print(f"\nQ{qnum}: Not found in manual queries")
            continue
        
        print(f"\nQ{qnum}: ", end="", flush=True)
        
        # STEP 1: Setup RLS policies (using postgres connection)
        try:
            with conn_postgres.cursor() as cur:
                cur.execute(RLS_SETUP_SQL)
            if args.verbose:
                print("[RLS enabled] ", end="", flush=True)
        except Exception as e:
            print(f"RLS SETUP ERROR: {e}")
            results_summary.append((qnum, "SETUP_ERROR", str(e), 'rls'))
            continue
        
        # STEP 2: Run with RLS (using rls_user connection)
        rls_rows, rls_err = run_query(conn_rls, ORIGINAL_QUERIES[qnum])
        
        # STEP 3: Teardown RLS policies (using postgres connection)
        try:
            with conn_postgres.cursor() as cur:
                cur.execute(RLS_TEARDOWN_SQL)
            if args.verbose:
                print("[RLS disabled] ", end="", flush=True)
        except Exception as e:
            print(f"WARNING: RLS teardown failed: {e}")
        
        if rls_err:
            print(f"RLS ERROR: {rls_err}")
            results_summary.append((qnum, "RLS_ERROR", rls_err, 'rls'))
            continue
        
        # STEP 4: Run manual query (as postgres, no RLS)
        manual_rows, manual_err = run_query(conn_postgres, manual_queries[qnum])
        if manual_err:
            print(f"MANUAL ERROR: {manual_err}")
            results_summary.append((qnum, "MANUAL_ERROR", manual_err, 'manual'))
            continue

        # STEP 5: Create views from log file and run pre-generated view query
        view_rows, view_err = [], None
        if qnum in view_queries:
            try:
                create_secure_views(conn_postgres, view_create_stmts)
            except Exception as e:
                view_err = f"VIEW SETUP ERROR: {e}"

            if not view_err:
                view_rows, view_err = run_query(conn_postgres, view_queries[qnum])

            try:
                drop_secure_views(conn_postgres, view_tables)
            except Exception as e:
                print(f"WARNING: View teardown failed: {e}")
        else:
            view_err = "No view query in log"

        # Compare RLS vs Manual
        match_manual, desc_manual = compare_results(rls_rows, manual_rows)
        # Compare RLS vs View
        match_view, desc_view = compare_results(rls_rows, view_rows, label2="View") if not view_err else (False, f"VIEW ERROR: {view_err}")

        rls_vs_manual = "[MATCH]" if match_manual else "[MISMATCH]"
        rls_vs_view   = "[MATCH]" if match_view   else "[MISMATCH]"
        print(f"RLS vs Manual: {rls_vs_manual} {desc_manual} | RLS vs View: {rls_vs_view} {desc_view}")

        results_summary.append((qnum, "MATCH" if match_manual else "MISMATCH", desc_manual, 'manual'))
        results_summary.append((qnum, "MATCH" if match_view   else "MISMATCH", desc_view,   'view'))

        if args.verbose:
            if not match_manual or not match_view:
                print(f"    RLS rows: {len(rls_rows)}")
                print(f"    Manual rows: {len(manual_rows)}")
                print(f"    View rows: {len(view_rows) if not view_err else 'ERR'}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    manual_results = [(q, s, d) for q, s, d, t in results_summary if t == 'manual']
    view_results   = [(q, s, d) for q, s, d, t in results_summary if t == 'view']

    manual_matches    = [r for r in manual_results if r[1] == "MATCH"]
    manual_mismatches = [r for r in manual_results if r[1] == "MISMATCH"]
    manual_errors     = [r for r in manual_results if "ERROR" in r[1]]
    view_matches      = [r for r in view_results   if r[1] == "MATCH"]
    view_mismatches   = [r for r in view_results   if r[1] == "MISMATCH"]
    view_errors       = [r for r in view_results   if "ERROR" in r[1]]

    total = len(manual_results)
    print(f"{'Metric':<25} {'RLS vs Manual':>15} {'RLS vs View':>15}")
    print("-" * 57)
    print(f"{'Total queries':<25} {total:>15} {total:>15}")
    print(f"{'Matches':<25} {len(manual_matches):>15} {len(view_matches):>15}")
    print(f"{'Mismatches':<25} {len(manual_mismatches):>15} {len(view_mismatches):>15}")
    print(f"{'Errors':<25} {len(manual_errors):>15} {len(view_errors):>15}")

    if manual_mismatches:
        print("\nRLS vs Manual mismatches:")
        for qnum, status, desc in manual_mismatches:
            print(f"  Q{qnum}: {desc}")

    if view_mismatches:
        print("\nRLS vs View mismatches:")
        for qnum, status, desc in view_mismatches:
            print(f"  Q{qnum}: {desc}")

    if manual_errors or view_errors:
        print("\nQueries with errors:")
        for qnum, status, desc in manual_errors + view_errors:
            print(f"  Q{qnum}: {desc}")
    
    # Final cleanup - ensure RLS is disabled
    try:
        with conn_postgres.cursor() as cur:
            cur.execute(RLS_TEARDOWN_SQL)
        print("\nFinal cleanup: RLS disabled")
    except Exception as e:
        print(f"\nWarning: Final cleanup failed: {e}")
    
    # Cleanup connections
    conn_rls.close()
    conn_postgres.close()
    
    # Return exit code
    return 0 if len(manual_mismatches) == 0 and len(view_mismatches) == 0 and len(manual_errors) == 0 and len(view_errors) == 0 else 1


if __name__ == '__main__':
    exit(main() or 0)
