-- ================================================================
-- rls_policy_experiment.sql
--
-- Standalone RLS policy experiment script.
-- Run as superuser:  psql -U postgres -f rls_policy_experiment.sql
--
-- What it does:
--   1. Creates a minimal orders table + sample TPC-H-like data
--   2. Creates the analyst role and security-definer predicates
--   3. Defines TWO RLS policies (p∧¬q vs ¬q∧p orderings)
--   4. Enables POLICY 1, runs EXPLAIN ANALYZE COUNT(*), logs output
--   5. Enables POLICY 2, runs EXPLAIN ANALYZE COUNT(*), logs output
--   6. Tears everything down cleanly
--
-- Output log: /tmp/rls_policy_experiment.log
-- ================================================================

\set ON_ERROR_STOP on

-- ================================================================
-- LOGGING: all query output and \qecho messages go to the log file
-- ================================================================
\o /tmp/rls_policy_experiment.log

\qecho '================================================================'
\qecho 'RLS Policy Experiment Log'
\qecho 'Run at: ' :current_timestamp
\qecho '================================================================'
\qecho ''


-- ================================================================
-- PART 0: PRE-TEARDOWN — idempotent cleanup from any previous run
-- ================================================================
\qecho '--- [0] Pre-teardown (idempotent) ---'

-- Suppress "does not exist" noise during pre-teardown
SET client_min_messages = WARNING;

DO $$
BEGIN
    -- Drop policies if they exist
    DROP POLICY IF EXISTS rls_policy_p_then_not_q ON orders;
    DROP POLICY IF EXISTS rls_policy_not_q_then_p ON orders;

    -- Disable & drop RLS
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'orders' AND schemaname = 'public') THEN
        ALTER TABLE orders DISABLE ROW LEVEL SECURITY;
    END IF;

    -- Revoke and drop functions
    DROP FUNCTION IF EXISTS pred_p(bigint);
    DROP FUNCTION IF EXISTS pred_q(bigint);

    -- Drop analyst role if it exists
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        REVOKE ALL ON SCHEMA public FROM analyst;
        REVOKE ALL ON ALL TABLES  IN SCHEMA public FROM analyst;
        DROP ROLE analyst;
    END IF;

    -- Drop orders table if it was created by us
    DROP TABLE IF EXISTS orders;
END;
$$;

RESET client_min_messages;
\qecho 'Pre-teardown complete.'
\qecho ''


-- ================================================================
-- PART 2: ANALYST ROLE + GRANTS
-- ================================================================
\qecho '--- [2] Creating analyst role ---'

CREATE ROLE analyst LOGIN PASSWORD 'analyst123';
GRANT USAGE  ON SCHEMA public TO analyst;
GRANT SELECT ON TABLE  orders TO analyst;

\qecho 'Role created.'
\qecho ''

CREATE INDEX idx_orders_totalprice  ON orders (o_totalprice);
CREATE INDEX idx_orders_orderdate   ON orders (o_orderdate);

-- Used in equality filters inside both predicates
CREATE INDEX idx_orders_orderstatus ON orders (o_orderstatus);

-- Used as the join key in every correlated EXISTS subquery
CREATE INDEX idx_orders_custkey     ON orders (o_custkey);

-- ================================================================
-- PART 3: SECURITY DEFINER FUNCTIONS
-- ================================================================
\qecho '--- [3] Creating security-definer predicate functions ---'

-- pred_p: "premium fulfilled order"
CREATE OR REPLACE FUNCTION pred_p(order_key bigint)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
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

-- pred_q: "significant order"
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

GRANT EXECUTE ON FUNCTION pred_p(bigint) TO analyst;
GRANT EXECUTE ON FUNCTION pred_q(bigint) TO analyst;

\qecho 'Functions created and granted.'
\qecho ''


-- ================================================================
-- PART 4: ENABLE RLS ON orders
-- ================================================================
\qecho '--- [4] Enabling RLS on orders ---'

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE  ROW LEVEL SECURITY;   -- applies to table owner too

\qecho 'RLS enabled (FORCE mode).'
\qecho ''


-- ================================================================
-- PART 6: EXPERIMENT A — Policy: pred_p AND NOT pred_q
-- ================================================================
CREATE POLICY rls_policy_p_then_not_q
    ON orders AS PERMISSIVE FOR SELECT TO analyst
    USING (
        pred_p(o_orderkey)
        AND NOT pred_q(o_orderkey)
    );

SET ROLE analyst;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT COUNT(*) AS implication_violations
FROM   orders;
RESET ROLE;

-- Done with this experiment — drop before creating the next
DROP POLICY rls_policy_p_then_not_q ON orders;


-- ================================================================
-- PART 7: EXPERIMENT B — Policy: NOT pred_q AND pred_p
-- ================================================================
CREATE POLICY rls_policy_not_q_then_p
    ON orders AS PERMISSIVE FOR SELECT TO analyst
    USING (
        NOT pred_q(o_orderkey)
        AND pred_p(o_orderkey)
    );

SET ROLE analyst;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT COUNT(*) AS implication_violations
FROM   orders;
RESET ROLE;

DROP POLICY rls_policy_not_q_then_p ON orders;
-- ================================================================
-- PART 8: TEARDOWN — drop everything in reverse dependency order
-- ================================================================
\qecho '================================================================'
\qecho 'TEARDOWN'
\qecho '================================================================'

-- Drop policies
DROP POLICY IF EXISTS rls_policy_p_then_not_q ON orders;
DROP POLICY IF EXISTS rls_policy_not_q_then_p ON orders;
\qecho 'Policies dropped.'

-- Disable RLS
ALTER TABLE orders DISABLE ROW LEVEL SECURITY;
\qecho 'RLS disabled.'

-- Revoke and drop functions
REVOKE EXECUTE ON FUNCTION pred_p(bigint) FROM analyst;
REVOKE EXECUTE ON FUNCTION pred_q(bigint) FROM analyst;
DROP FUNCTION pred_p(bigint);
DROP FUNCTION pred_q(bigint);
\qecho 'Functions dropped.'

-- Revoke role permissions
REVOKE SELECT ON TABLE  orders FROM analyst;
REVOKE USAGE  ON SCHEMA public FROM analyst;

-- Drop the table (remove this line if you want to keep your data)
DROP TABLE orders;
\qecho 'Table dropped.'

-- Drop the role
DROP ROLE analyst;
\qecho 'Role dropped.'

\qecho ''
\qecho '================================================================'
\qecho 'All done. Full teardown complete.'
\qecho 'Log written to: /tmp/rls_policy_experiment.log'
\qecho '================================================================'

-- Close the log file (output returns to stdout)

---------------------------------------------- expt 2 ------ normal query 1
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

-------------------------------------- expt 3 ------ normal query 2
explain analyze SELECT COUNT(*)
FROM orders o
WHERE
    -- p holds
    o.o_totalprice  > 150000
    AND o.o_orderstatus = 'F'
    AND o.o_orderdate   > '1994-12-31'
    AND NOT (
        o.o_totalprice > 50000
        AND o.o_orderdate > '1993-12-31'
        AND EXISTS (
            SELECT 1 FROM orders o3
            WHERE o3.o_custkey    = o.o_custkey
              AND o3.o_orderstatus = 'F'
        )
    AND EXISTS (
        SELECT 1 FROM orders o2
        WHERE o2.o_custkey    = o.o_custkey
          AND o2.o_orderstatus = 'F'
    );
