-- ============================================================
-- FULL CLEAN REBUILD SCRIPT
-- RLS on fresh.orders using ONE policy with TWO functions in AND
-- ============================================================

-- Always start from the original session role
RESET ROLE;

-- Use the intended schema
SET search_path TO fresh, public;

-- ------------------------------------------------------------
-- 0) Optional: terminate any active sessions for app_user
--    This helps avoid DROP ROLE issues if app_user is connected.
--    Requires sufficient privileges (typically superuser).
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        PERFORM pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE usename = 'app_user'
          AND pid <> pg_backend_pid();
    END IF;
END
$$;

-- ------------------------------------------------------------
-- 1) Drop policy and functions first, so roles can be dropped cleanly
-- ------------------------------------------------------------
DROP POLICY IF EXISTS orders_combined_contradiction ON fresh.orders;

DROP FUNCTION IF EXISTS fresh.fn_no_significant_finalized_orders();
DROP FUNCTION IF EXISTS fresh.fn_no_nonfinal_low_old_orders();

-- Optional: disable RLS during cleanup/rebuild
ALTER TABLE fresh.orders DISABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 2) Cleanly drop app_user if it exists
--    DROP OWNED removes grants/default privileges in this database.
--    REASSIGN OWNED handles any owned objects in this database.
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        BEGIN
            EXECUTE 'REASSIGN OWNED BY app_user TO CURRENT_USER';
        EXCEPTION
            WHEN OTHERS THEN
                -- Ignore if app_user owns nothing reassignable here
                NULL;
        END;

        BEGIN
            EXECUTE 'DROP OWNED BY app_user';
        EXCEPTION
            WHEN OTHERS THEN
                -- Ignore if nothing to drop
                NULL;
        END;

        EXECUTE 'DROP ROLE app_user';
    END IF;
END
$$;

-- ------------------------------------------------------------
-- 3) Cleanly drop rls_helper if it exists
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_helper') THEN
        BEGIN
            EXECUTE 'REASSIGN OWNED BY rls_helper TO CURRENT_USER';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        BEGIN
            EXECUTE 'DROP OWNED BY rls_helper';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        EXECUTE 'DROP ROLE rls_helper';
    END IF;
END
$$;

-- ------------------------------------------------------------
-- 4) Recreate roles
-- ------------------------------------------------------------
CREATE ROLE rls_helper NOLOGIN BYPASSRLS;
CREATE ROLE app_user LOGIN PASSWORD 'app_user';

-- ------------------------------------------------------------
-- 5) Grant helper/runtime privileges
-- ------------------------------------------------------------
GRANT USAGE ON SCHEMA fresh TO rls_helper;
GRANT USAGE ON SCHEMA fresh TO app_user;

GRANT SELECT ON fresh.orders TO rls_helper;
GRANT SELECT ON fresh.orders TO app_user;

-- ------------------------------------------------------------
-- 6) Create helper function #1
--    Returns TRUE iff there is NO significant finalized recent order
-- ------------------------------------------------------------
CREATE FUNCTION fresh.fn_no_significant_finalized_orders()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = fresh, pg_catalog
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM fresh.orders
        WHERE o_orderstatus = 'F'
          AND o_totalprice > 100000
          AND o_orderdate >= DATE '1995-01-01'
    );
$$;

ALTER FUNCTION fresh.fn_no_significant_finalized_orders() OWNER TO rls_helper;
REVOKE ALL ON FUNCTION fresh.fn_no_significant_finalized_orders() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fresh.fn_no_significant_finalized_orders() TO app_user;

-- ------------------------------------------------------------
-- 7) Create helper function #2
--    Returns TRUE iff there is NO non-final, low-value, old order
-- ------------------------------------------------------------
CREATE FUNCTION fresh.fn_no_nonfinal_low_old_orders()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = fresh, pg_catalog
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM fresh.orders
        WHERE o_orderstatus <> 'F'
          AND o_totalprice <= 100000
          AND o_orderdate < DATE '1995-01-01'
    );
$$;

ALTER FUNCTION fresh.fn_no_nonfinal_low_old_orders() OWNER TO rls_helper;
REVOKE ALL ON FUNCTION fresh.fn_no_nonfinal_low_old_orders() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fresh.fn_no_nonfinal_low_old_orders() TO app_user;

-- ------------------------------------------------------------
-- 8) Enable and force RLS
-- ------------------------------------------------------------
ALTER TABLE fresh.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE fresh.orders FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 9) Create ONE single RLS policy using both functions with AND
-- ------------------------------------------------------------
CREATE POLICY orders_combined_contradiction
ON fresh.orders
FOR SELECT
TO app_user
USING (
    fresh.fn_no_significant_finalized_orders()
    AND
    fresh.fn_no_nonfinal_low_old_orders()
);

-- ------------------------------------------------------------
-- 10) Test as app_user
-- ------------------------------------------------------------
SET ROLE app_user;

SET search_path TO fresh, public;
SET enable_memoize = OFF;
SET max_parallel_workers_per_gather = 0;

SELECT current_user, session_user;

SELECT count(*) AS visible_orders_count
FROM fresh.orders;

EXPLAIN ANALYZE
SELECT count(*)
FROM fresh.orders;

--RESET ROLE;

-- ============================================================
-- END OF SCRIPT
-- ============================================================


-- ============================================================
-- FULL CLEAN REBUILD SCRIPT
-- Contradictory orders policy using TWO VIEWS + ONE RLS POLICY
-- ============================================================

-- Always start clean
RESET ROLE;
SET search_path TO fresh, public;

-- ------------------------------------------------------------
-- 0) Optional: terminate active sessions for app_user
--    Helps avoid DROP ROLE failures if app_user is connected.
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        PERFORM pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE usename = 'app_user'
          AND pid <> pg_backend_pid();
    END IF;
END
$$;

-- ------------------------------------------------------------
-- 1) Drop policy first, then helper views, then disable RLS
-- ------------------------------------------------------------
DROP POLICY IF EXISTS orders_combined_contradiction_view ON fresh.orders;

DROP VIEW IF EXISTS fresh.v_orders_significant_finalized CASCADE;
DROP VIEW IF EXISTS fresh.v_orders_nonfinal_low_old CASCADE;

ALTER TABLE fresh.orders DISABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 2) Drop roles safely, if they exist
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        BEGIN
            EXECUTE 'REASSIGN OWNED BY app_user TO CURRENT_USER';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        BEGIN
            EXECUTE 'DROP OWNED BY app_user';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        EXECUTE 'DROP ROLE app_user';
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_helper') THEN
        BEGIN
            EXECUTE 'REASSIGN OWNED BY rls_helper TO CURRENT_USER';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        BEGIN
            EXECUTE 'DROP OWNED BY rls_helper';
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        EXECUTE 'DROP ROLE rls_helper';
    END IF;
END
$$;

-- ------------------------------------------------------------
-- 3) Recreate roles
--    rls_helper owns the views and bypasses RLS on fresh.orders
-- ------------------------------------------------------------
CREATE ROLE rls_helper NOLOGIN BYPASSRLS;
CREATE ROLE app_user LOGIN PASSWORD 'app_user';

-- ------------------------------------------------------------
-- 4) Grants
-- ------------------------------------------------------------
GRANT USAGE ON SCHEMA fresh TO rls_helper;
GRANT USAGE ON SCHEMA fresh TO app_user;

GRANT SELECT ON fresh.orders TO rls_helper;
GRANT SELECT ON fresh.orders TO app_user;

-- ------------------------------------------------------------
-- 5) Create TWO policy views
--
--    View 1: significant, finalized, recent orders
--    View 2: non-final, low-value, old orders
--
--    SECURITY BARRIER is used so the view behaves as a barrier
--    for planner pushdown; ownership by rls_helper is what
--    prevents recursive RLS on fresh.orders.
-- ------------------------------------------------------------

CREATE VIEW fresh.v_orders_significant_finalized
WITH (security_barrier = true)
AS
SELECT
    o_orderkey,
    o_custkey,
    o_orderstatus,
    o_totalprice,
    o_orderdate
FROM fresh.orders
WHERE o_orderstatus = 'F'
  AND o_totalprice > 100000
  AND o_orderdate >= DATE '1995-01-01';

ALTER VIEW fresh.v_orders_significant_finalized OWNER TO rls_helper;

CREATE VIEW fresh.v_orders_nonfinal_low_old
WITH (security_barrier = true)
AS
SELECT
    o_orderkey,
    o_custkey,
    o_orderstatus,
    o_totalprice,
    o_orderdate
FROM fresh.orders
WHERE o_orderstatus <> 'F'
  AND o_totalprice <= 100000
  AND o_orderdate < DATE '1995-01-01';

ALTER VIEW fresh.v_orders_nonfinal_low_old OWNER TO rls_helper;

-- App user may query the views directly if desired
GRANT SELECT ON fresh.v_orders_significant_finalized TO app_user;
GRANT SELECT ON fresh.v_orders_nonfinal_low_old TO app_user;

-- ------------------------------------------------------------
-- 6) Enable and force RLS on orders
-- ------------------------------------------------------------
ALTER TABLE fresh.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE fresh.orders FORCE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 7) ONE single RLS policy on fresh.orders
--
--    The row is visible only if it appears in BOTH views.
--    Since the view predicates are contradictory, the
--    intersection is empty.
-- ------------------------------------------------------------
CREATE POLICY orders_combined_contradiction_view
ON fresh.orders
FOR SELECT
TO app_user
USING (
    EXISTS (
        SELECT 1
        FROM fresh.v_orders_significant_finalized v1
        WHERE v1.o_orderkey = orders.o_orderkey
    )
    AND
    EXISTS (
        SELECT 1
        FROM fresh.v_orders_nonfinal_low_old v2
        WHERE v2.o_orderkey = orders.o_orderkey
    )
);

-- ------------------------------------------------------------
-- 8) Test section
-- ------------------------------------------------------------
SET ROLE app_user;
SET search_path TO fresh, public;
SET enable_memoize = OFF;
SET max_parallel_workers_per_gather = 0;

SELECT current_user, session_user;

-- Each view may individually return rows
--SELECT count(*) AS cnt_significant_finalized
--FROM fresh.v_orders_significant_finalized;

--SELECT count(*) AS cnt_nonfinal_low_old
--FROM fresh.v_orders_nonfinal_low_old;

-- But the base table under RLS should expose zero rows
--SELECT count(*) AS visible_orders_count
--FROM fresh.orders;

EXPLAIN ANALYZE
SELECT count(*)
FROM fresh.orders;

--RESET ROLE;

-- ============================================================
-- END OF SCRIPT
-- ============================================================
