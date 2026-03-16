-- P1 TIERED: Customer Policy (Tier 1) - SIMPLE
-- References: nation, region (Tier 0 - no policies)
-- Description: Customers from EUROPE or AMERICA regions with positive balance
-- Complexity: SIMPLE (single EXISTS to dimension tables)

SELECT c.*
FROM customer c, nation n, region r
WHERE c.c_acctbal > 7999
  AND n.n_nationkey = c.c_nationkey
      AND n.n_regionkey = r.r_regionkey
      AND r.r_name IN ('EUROPE', 'AMERICA');

-- PREDICATE (for manual injection):
-- c.c_acctbal > 0
--   AND EXISTS (
--     SELECT 1
--     FROM nation n, region r
--     WHERE n.n_nationkey = c.c_nationkey
--       AND n.n_regionkey = r.r_regionkey
--       AND r.r_name IN ('EUROPE', 'AMERICA')
--   )


