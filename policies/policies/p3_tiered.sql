-- P3 TIERED: Lineitem Policy (Tier 3) - MEDIUM
-- References: orders (Tier 2, no policy), partsupp (Tier 2, has p4)
-- Description: Lineitem from high-priority orders with available partsupp
-- Complexity: MEDIUM (refs partsupp which has policy p4 → supplier p2)
-- Chain: lineitem(p3) → partsupp(p4) → supplier(p2) → nation/region

SELECT l.*
FROM lineitem l
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.o_orderkey = l.l_orderkey
      AND o.o_orderpriority IN ('1-URGENT', '2-HIGH')
  )
  AND EXISTS (
    SELECT 1
    FROM partsupp ps
    WHERE ps.ps_partkey = l.l_partkey
      AND ps.ps_suppkey = l.l_suppkey
      AND ps.ps_availqty > 9000
  );

-- PREDICATE (for manual injection):
-- EXISTS (
--     SELECT 1
--     FROM orders o
--     WHERE o.o_orderkey = l.l_orderkey
--       AND o.o_orderpriority IN ('1-URGENT', '2-HIGH')
--   )
--   AND EXISTS (
--     SELECT 1
--     FROM partsupp ps
--     WHERE ps.ps_partkey = l.l_partkey
--       AND ps.ps_suppkey = l.l_suppkey
--       AND ps.ps_availqty > 0
--   )

