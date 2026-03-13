-- ================================================================
-- PART 1: SETUP — run as superuser
-- ================================================================

-- 1a. Create the less-privileged analyst user
CREATE ROLE analyst LOGIN PASSWORD 'analyst123';

-- 1b. Minimal schema access only
GRANT USAGE  ON SCHEMA public  TO analyst;
GRANT SELECT ON TABLE  orders  TO analyst;

-- 1c. Enable RLS — superuser is exempt, analyst is not
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE  ROW LEVEL SECURITY;


-- ================================================================
-- PART 2: SECURITY DEFINER FUNCTIONS (owned by superuser)
--         These run with superuser privileges regardless of caller,
--         bypassing RLS on any internal table access they perform.
-- ================================================================

-- Predicate p: "premium fulfilled order"
CREATE OR REPLACE FUNCTION pred_p(order_key bigint)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER                          -- runs as function owner (superuser)
SET search_path = public                  -- prevents search_path hijacking
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM   orders o
        WHERE  o.o_orderkey    = order_key
          AND  o.o_totalprice  > 150000
          AND  o.o_orderstatus = 'F'
          AND  o.o_orderdate   > '1994-12-31'
          AND  EXISTS (
              SELECT 1
              FROM   orders o2
              WHERE  o2.o_custkey    = o.o_custkey
                AND  o2.o_orderstatus = 'F'
          )
    );
$$;

-- Predicate q: "significant order"
CREATE OR REPLACE FUNCTION pred_q(order_key bigint)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM   orders o
        WHERE  o.o_orderkey   = order_key
          AND  o.o_totalprice > 50000
          AND  o.o_orderdate  > '1993-12-31'
          AND  EXISTS (
              SELECT 1
              FROM   orders o2
              WHERE  o2.o_custkey    = o.o_custkey
                AND  o2.o_orderstatus = 'F'
          )
    );
$$;

-- Grant execution rights to analyst only — not table-level access
GRANT EXECUTE ON FUNCTION pred_p(bigint) TO analyst;
GRANT EXECUTE ON FUNCTION pred_q(bigint) TO analyst;


-- ================================================================
-- PART 3: RLS POLICY
--         Analyst may only read rows that satisfy p OR q.
--         The policy itself calls the SECURITY DEFINER functions,
--         so internal correlated subqueries inside them run as
--         superuser and are not blocked by RLS recursively.
-- ================================================================

CREATE POLICY analyst_orders_policy
    ON     orders
    FOR    SELECT
    TO     analyst
    USING  ( pred_p(o_orderkey) OR pred_q(o_orderkey) );


-- ================================================================
-- PART 4: QUERIES — switch to analyst role
-- ================================================================

SET ROLE analyst;

explain analyze SELECT COUNT(*) AS implication_violations
FROM   orders o
WHERE  pred_p(o.o_orderkey)            -- p holds
  AND  NOT pred_q(o.o_orderkey);       -- q does NOT hold


RESET ROLE;   -- back to superuser


-- ================================================================
-- PART 5: TEARDOWN — drop everything in reverse dependency order
-- ================================================================

-- Drop RLS policy first (depends on functions)
DROP POLICY analyst_orders_policy ON orders;

-- Disable RLS
ALTER TABLE orders DISABLE ROW LEVEL SECURITY;

-- Revoke and drop functions
REVOKE EXECUTE ON FUNCTION pred_p(bigint) FROM analyst;
REVOKE EXECUTE ON FUNCTION pred_q(bigint) FROM analyst;
DROP FUNCTION pred_p(bigint);
DROP FUNCTION pred_q(bigint);

-- Revoke table and schema access
REVOKE SELECT ON TABLE  orders FROM analyst;
REVOKE USAGE  ON SCHEMA public FROM analyst;

-- Drop the user last
DROP ROLE analyst;







-- View for p: "premium fulfilled order"
CREATE VIEW p AS
SELECT o.*
FROM orders o
WHERE o.o_totalprice  > 150000
  AND o.o_orderstatus = 'F'
  AND o.o_orderdate   > '1994-12-31'
  AND EXISTS (
      SELECT 1 FROM orders o2
      WHERE o2.o_custkey    = o.o_custkey
        AND o2.o_orderstatus = 'F'
  );

-- View for q: "significant order"
CREATE VIEW q AS
SELECT o.*
FROM orders o
WHERE o.o_totalprice > 50000
  AND o.o_orderdate  > '1993-12-31'
  AND EXISTS (
      SELECT 1 FROM orders o2
      WHERE o2.o_custkey    = o.o_custkey
        AND o2.o_orderstatus = 'F'
  );

explain analyze  SELECT COUNT(*)
FROM orders o
WHERE o.o_orderkey IN (SELECT o_orderkey FROM p)       -- p holds
  AND o.o_orderkey NOT IN (SELECT o_orderkey FROM q);  -- q does not hold








explain analyze SELECT COUNT(*)
FROM orders o
WHERE
    -- p holds
    o.o_totalprice  > 150000
    AND o.o_orderstatus = 'F'
    AND o.o_orderdate   > '1994-12-31'
    AND EXISTS (
        SELECT 1 FROM orders o2
        WHERE o2.o_custkey    = o.o_custkey
          AND o2.o_orderstatus = 'F'
    )
    -- q does NOT hold  (¬q)
    AND NOT (
        o.o_totalprice > 50000
        AND o.o_orderdate > '1993-12-31'
        AND EXISTS (
            SELECT 1 FROM orders o3
            WHERE o3.o_custkey    = o.o_custkey
              AND o3.o_orderstatus = 'F'
        )
    );

"Aggregate  (cost=8202111917.35..8202111917.36 rows=1 width=8) (actual time=182124.952..182124.953 rows=1 loops=1)"
"  ->  Hash Join  (cost=49254.77..8202111578.80 rows=135420 width=0) (actual time=182124.948..182124.949 rows=0 loops=1)"
"        Hash Cond: (o.o_custkey = o2.o_custkey)"
"        ->  Seq Scan on orders o  (cost=0.00..8202060462.00 rows=135420 width=8) (actual time=182124.946..182124.947 rows=0 loops=1)"
"              Filter: ((o_totalprice > '150000'::numeric) AND (o_orderdate > '1994-12-31'::date) AND ((o_orderstatus)::text = 'F'::text) AND ((o_totalprice <= '50000'::numeric) OR (o_orderdate <= '1993-12-31'::date) OR (NOT EXISTS(SubPlan 1))))"
"              Rows Removed by Filter: 1500000"
"              SubPlan 1"
"                ->  Seq Scan on orders o3  (cost=0.00..49212.00 rows=9 width=0) (actual time=9.136..9.136 rows=1 loops=19894)"
"                      Filter: ((o_custkey = o.o_custkey) AND ((o_orderstatus)::text = 'F'::text))"
"                      Rows Removed by Filter: 177033"
"        ->  Hash  (cost=48172.75..48172.75 rows=86562 width=8) (never executed)"
"              ->  HashAggregate  (cost=47307.12..48172.75 rows=86562 width=8) (never executed)"
"                    Group Key: o2.o_custkey"
"                    ->  Seq Scan on orders o2  (cost=0.00..45462.00 rows=738050 width=8) (never executed)"
"                          Filter: ((o_orderstatus)::text = 'F'::text)"
"Planning Time: 0.447 ms"
"Execution Time: 182125.872 ms"
