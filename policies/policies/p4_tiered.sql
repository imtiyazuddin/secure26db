-- P4 TIERED: Partsupp Policy (Tier 2)
-- References: supplier (Tier 1, has p2)
-- Description: Partsupp from suppliers with positive balance and sufficient stock

SELECT
    ps.ps_partkey,
    ps.ps_suppkey,
    ps.ps_availqty,
    ps.ps_supplycost,
    ps.ps_comment
FROM partsupp ps
JOIN supplier s
    ON s.s_suppkey = ps.ps_suppkey
WHERE ps.ps_availqty > 9000
GROUP BY
    ps.ps_partkey,
    ps.ps_suppkey,
    ps.ps_availqty,
    ps.ps_supplycost,
    ps.ps_comment
HAVING MAX(CASE WHEN s.s_acctbal > 7999 THEN 1 ELSE 0 END) = 1;

