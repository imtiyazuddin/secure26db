-- P4 TIERED: Partsupp Policy (Tier 2)
-- References: supplier (Tier 1, has p2)
-- Description: Partsupp from suppliers with positive balance and sufficient stock

SELECT ps.*
FROM partsupp ps
WHERE ps.ps_availqty > 9000
  AND EXISTS (
    SELECT 1
    FROM supplier s
    WHERE s.s_suppkey = ps.ps_suppkey
      AND s.s_acctbal > 7999
  );

