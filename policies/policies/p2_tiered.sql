-- P2 TIERED: Supplier Policy (Tier 1) - SIMPLE
-- References: nation, region (Tier 0 - no policies)
-- Description: Suppliers from EUROPE with positive balance
-- Complexity: SIMPLE (single EXISTS to dimension tables)

SELECT s.*
FROM supplier s
WHERE s.s_acctbal > 0
  AND EXISTS (
    SELECT 1
    FROM nation n, region r
    WHERE n.n_nationkey = s.s_nationkey
      AND n.n_regionkey = r.r_regionkey
      AND r.r_name = 'EUROPE'
  );

-- PREDICATE (for manual injection):
-- s.s_acctbal > 0
--   AND EXISTS (
--     SELECT 1
--     FROM nation n, region r
--     WHERE n.n_nationkey = s.s_nationkey
--       AND n.n_regionkey = r.r_regionkey
--       AND r.r_name = 'EUROPE'
--   )
