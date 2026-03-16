/* ---------------------------------------------------------
P3b:   Supplier visible only if they have never supplied
        a part with retail price below 500
   --------------------------------------------------------- */
SELECT s.*
FROM supplier s
WHERE NOT EXISTS (
    SELECT 1
    FROM partsupp ps
    JOIN part p ON p.p_partkey = ps.ps_partkey
    WHERE ps.ps_suppkey = s.s_suppkey
      AND p.p_retailprice < 500
);
