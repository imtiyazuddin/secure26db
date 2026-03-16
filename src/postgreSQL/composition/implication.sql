-- ================================================================
-- rls_policy_experiment_pgadmin.sql
--
-- pgAdmin-compatible version. Run the entire script at once.
--
-- Logging strategy:
--   - All status messages  → RAISE NOTICE  (pgAdmin Messages tab)
--   - All EXPLAIN output   → experiment_log table (query at the end
--                            to read it, or inspect via pgAdmin)
--
-- After the script finishes, run this to read the log:
--   SELECT * FROM experiment_log ORDER BY id;
-- ================================================================
SET work_mem = '256MB';

DROP INDEX IF EXISTS idx_orders_totalprice;
DROP INDEX IF EXISTS idx_orders_orderdate;
DROP INDEX IF EXISTS idx_orders_orderstatus;
DROP INDEX IF EXISTS idx_orders_custkey;


-- ================================================================
-- PART 0: LOG TABLE — created first so everything can write to it
-- ================================================================
DROP TABLE IF EXISTS experiment_log;
CREATE TABLE experiment_log (
    id          SERIAL PRIMARY KEY,
    logged_at   TIMESTAMPTZ DEFAULT now(),
    section     TEXT,
    message     TEXT
);

-- Helper: insert a log row AND raise a notice simultaneously
CREATE OR REPLACE FUNCTION log(p_section TEXT, p_message TEXT)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO experiment_log(section, message) VALUES (p_section, p_message);
    RAISE NOTICE '[%] %', p_section, p_message;
END;
$$;


-- ================================================================
-- PART 1: PRE-TEARDOWN — idempotent cleanup from any previous run
-- ================================================================
DO $$
BEGIN
    PERFORM log('PRE-TEARDOWN', 'Starting idempotent cleanup...');

    DROP POLICY IF EXISTS rls_policy_p_then_not_q ON orders;
    DROP POLICY IF EXISTS rls_policy_not_q_then_p ON orders;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'orders' AND schemaname = 'public') THEN
        ALTER TABLE orders DISABLE ROW LEVEL SECURITY;
    END IF;

    DROP FUNCTION IF EXISTS pred_p(bigint);
    DROP FUNCTION IF EXISTS pred_q(bigint);

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN
        REVOKE ALL ON SCHEMA public FROM analyst;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst;
        DROP ROLE analyst;
    END IF;

    --DROP TABLE IF EXISTS orders;

    PERFORM log('PRE-TEARDOWN', 'Cleanup complete.');
END;
$$;


-- ================================================================
-- PART 2: CREATE ORDERS TABLE + SAMPLE DATA
-- ================================================================
DO $$ BEGIN PERFORM log('SETUP', 'Creating orders table...'); END $$;


-- ================================================================
-- PART 3: INDEXES
-- ================================================================
CREATE INDEX idx_orders_totalprice  ON orders (o_totalprice);
CREATE INDEX idx_orders_orderdate   ON orders (o_orderdate);
CREATE INDEX idx_orders_orderstatus ON orders (o_orderstatus);
CREATE INDEX idx_orders_custkey     ON orders (o_custkey);

DO $$ BEGIN PERFORM log('SETUP', 'Indexes created.'); END $$;


-- ================================================================
-- PART 4: ANALYST ROLE + GRANTS
--   NOTE: table must exist before GRANT SELECT ON TABLE orders
-- ================================================================
CREATE ROLE analyst LOGIN PASSWORD 'analyst123';
GRANT USAGE  ON SCHEMA public TO analyst;
GRANT SELECT ON TABLE  orders TO analyst;

DO $$ BEGIN PERFORM log('SETUP', 'analyst role created and granted.'); END $$;


-- ================================================================
-- PART 5: SECURITY DEFINER FUNCTIONS
-- ================================================================
CREATE OR REPLACE FUNCTION pred_p(order_key bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM orders o
        WHERE  o.o_orderkey    = order_key
          AND  o.o_totalprice  > 150000
          AND  o.o_orderstatus = 'F'
          AND  o.o_orderdate   > '1994-12-31'
          AND  EXISTS (
              SELECT 1 FROM orders o2
              WHERE  o2.o_custkey    = o.o_custkey
                AND  o2.o_orderstatus = 'F'
          )
    );
$$;

CREATE OR REPLACE FUNCTION pred_q(order_key bigint)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM orders o
        WHERE  o.o_orderkey   = order_key
          AND  o.o_totalprice > 50000
          AND  o.o_orderdate  > '1993-12-31'
          AND  EXISTS (
              SELECT 1 FROM orders o2
              WHERE  o2.o_custkey    = o.o_custkey
                AND  o2.o_orderstatus = 'F'
          )
    );
$$;

GRANT EXECUTE ON FUNCTION pred_p(bigint) TO analyst;
GRANT EXECUTE ON FUNCTION pred_q(bigint) TO analyst;

DO $$ BEGIN PERFORM log('SETUP', 'Security-definer functions created and granted.'); END $$;


-- ================================================================
-- PART 6: ENABLE RLS
-- ================================================================
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE  ROW LEVEL SECURITY;

DO $$ BEGIN PERFORM log('SETUP', 'RLS enabled (FORCE mode).'); END $$;


-- ================================================================
-- PART 7: EXPERIMENT A
--   Policy: pred_p(o_orderkey) AND NOT pred_q(o_orderkey)
--   Query:  plain SELECT COUNT(*) — RLS policy is the filter
-- ================================================================
DO $$ BEGIN PERFORM log('EXPERIMENT-A', 'Creating policy rls_policy_p_then_not_q...'); END $$;

CREATE POLICY rls_policy_p_then_not_q
    ON orders AS PERMISSIVE FOR SELECT TO analyst
    USING (
        pred_p(o_orderkey)
        AND NOT pred_q(o_orderkey)
    );

DO $$ BEGIN PERFORM log('EXPERIMENT-A', 'Policy active. Running EXPLAIN ANALYZE...'); END $$;

-- Capture EXPLAIN output into the log table
DO $$
DECLARE r text;
BEGIN
    FOR r IN
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT COUNT(*) AS implication_violations FROM orders
    LOOP
        INSERT INTO experiment_log(section, message)
        VALUES ('EXPERIMENT-A PLAN', r);
    END LOOP;
END;
$$;


DROP POLICY rls_policy_p_then_not_q ON orders;
DO $$ BEGIN PERFORM log('EXPERIMENT-A', 'Policy dropped. Experiment A complete.'); END $$;


-- ================================================================
-- PART 8: EXPERIMENT B
--   Policy: NOT pred_q(o_orderkey) AND pred_p(o_orderkey)
--   Query:  plain SELECT COUNT(*) — RLS policy is the filter
-- ================================================================
DO $$ BEGIN PERFORM log('EXPERIMENT-B', 'Creating policy rls_policy_not_q_then_p...'); END $$;

CREATE POLICY rls_policy_not_q_then_p
    ON orders AS PERMISSIVE FOR SELECT TO analyst
    USING (
        NOT pred_q(o_orderkey)
        AND pred_p(o_orderkey)
    );

DO $$ BEGIN PERFORM log('EXPERIMENT-B', 'Policy active. Running EXPLAIN ANALYZE...'); END $$;

DO $$
DECLARE r text;
BEGIN
    FOR r IN
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT COUNT(*) AS implication_violations FROM orders
    LOOP
        INSERT INTO experiment_log(section, message)
        VALUES ('EXPERIMENT-B PLAN', r);
    END LOOP;
END;
$$;


DROP POLICY rls_policy_not_q_then_p ON orders;
DO $$ BEGIN PERFORM log('EXPERIMENT-B', 'Policy dropped. Experiment B complete.'); END $$;


-- ================================================================
-- PART 9: INLINE QUERIES (no RLS / no functions)
--   Expt 2 — p ∧ ¬q  with EXISTS outside NOT
--   Expt 3 — p ∧ ¬q  with EXISTS inside NOT
-- ================================================================
ALTER TABLE orders DISABLE ROW LEVEL SECURITY;

DO $$ BEGIN PERFORM log('TEARDOWN', 'Starting teardown...'); END $$;

DROP POLICY IF EXISTS rls_policy_p_then_not_q ON orders;
DROP POLICY IF EXISTS rls_policy_not_q_then_p ON orders;

REVOKE EXECUTE ON FUNCTION pred_p(bigint) FROM analyst;
REVOKE EXECUTE ON FUNCTION pred_q(bigint) FROM analyst;
DROP FUNCTION pred_p(bigint);
DROP FUNCTION pred_q(bigint);

REVOKE SELECT ON TABLE  orders FROM analyst;
REVOKE USAGE  ON SCHEMA public FROM analyst;
DROP ROLE analyst;

DO $$ BEGIN PERFORM log('INLINE-QUERIES', 'RLS disabled. Running inline predicate queries...'); END $$;

-- Expt 2: EXISTS for the correlated check sits OUTSIDE the NOT block
DO $$
DECLARE r text;
BEGIN
    FOR r IN
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT COUNT(*) 
    FROM orders o
    WHERE o.o_totalprice  > 150000
      AND o.o_orderstatus = 'F'
      AND o.o_orderdate   > '1994-12-31'
      AND EXISTS (
              SELECT 1 FROM orders o2
              WHERE o2.o_custkey    = o.o_custkey
                AND o2.o_orderstatus = 'F'
          )
      AND NOT (
              o.o_totalprice > 50000
          AND o.o_orderdate  > '1993-12-31'
          AND EXISTS (
                  SELECT 1 FROM orders o3
                  WHERE o3.o_custkey    = o.o_custkey
                    AND o3.o_orderstatus = 'F'
              )
          )
    LOOP
        INSERT INTO experiment_log(section, message)
        VALUES ('INLINE-QUERIES-A PLAN (EXISTS outside NOT)', r);
    END LOOP;
END;
$$;

-- Expt 3: EXISTS for the correlated check sits INSIDE the NOT block

DO $$
DECLARE r text;
BEGIN
    FOR r IN
        EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
        SELECT COUNT(*) 
    FROM orders o
    WHERE o.o_totalprice  > 150000
      AND o.o_orderstatus = 'F'
      AND o.o_orderdate   > '1994-12-31'
      AND NOT (
              o.o_totalprice > 50000
          AND o.o_orderdate  > '1993-12-31'
          AND EXISTS (
                  SELECT 1 FROM orders o3
                  WHERE o3.o_custkey    = o.o_custkey
                    AND o3.o_orderstatus = 'F'
              )
          AND EXISTS (
                  SELECT 1 FROM orders o2
                  WHERE o2.o_custkey    = o.o_custkey
                    AND o2.o_orderstatus = 'F'
              )
          )
    LOOP
        INSERT INTO experiment_log(section, message)
        VALUES ('INLINE-QUERIES-B PLAN (EXISTS inside NOT)', r);
    END LOOP;
END;
$$;


-- ================================================================
-- PART 10: TEARDOWN
-- ================================================================



DO $$ BEGIN PERFORM log('TEARDOWN', 'Teardown complete.'); END $$;

DROP FUNCTION log(TEXT, TEXT);


-- ================================================================
-- READ THE LOG — run this cell last, or separately in pgAdmin
-- ================================================================
SELECT id, logged_at, section, message
FROM   experiment_log
ORDER  BY id;
