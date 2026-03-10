set search_path TO fresh;

ALTER TABLE customer ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders   ENABLE ROW LEVEL SECURITY;

ALTER TABLE customer FORCE ROW LEVEL SECURITY;
ALTER TABLE orders   FORCE ROW LEVEL SECURITY;


DROP ROLE IF EXISTS app_user;
CREATE USER app_user PASSWORD 'app_user';

DROP POLICY IF EXISTS customer_no_visible_orders on customer;
CREATE POLICY customer_no_visible_orders
ON customer
FOR SELECT
TO app_user
USING (
    NOT EXISTS (
        SELECT 1
        FROM orders o
        WHERE o.o_custkey = customer.c_custkey
    )
);

DROP POLICY IF EXISTS orders_significant_finalized on orders;
CREATE POLICY orders_significant_finalized
ON orders
FOR SELECT
TO app_user
USING (
    o_totalprice > 100000
);

GRANT USAGE ON SCHEMA fresh TO app_user;
GRANT SELECT ON fresh.customer TO app_user;
GRANT SELECT ON fresh.orders   TO app_user;


SET ROLE app_user;

SELECT current_user, session_user;

SET search_path TO fresh, public;
SET enable_memoize = OFF;
SET max_parallel_workers_per_gather = 1;

--SELECT count(*) FROM customer;
--SELECT count(*) FROM orders;

EXPLAIN ANALYZE
SELECT count(*)
FROM customer c
JOIN orders o
  ON c.c_custkey = o.o_custkey;

--RESET ROLE;
