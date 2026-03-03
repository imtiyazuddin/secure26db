----================================
-- P4: Group/Agg
--------------------------------
/* ---------------------------------------------------------
P4a:   Customer visible only if total account balance > 0
   --------------------------------------------------------- */
SELECT c.*
FROM customer c
GROUP BY c.c_custkey,
         c.c_name,
         c.c_address,
         c.c_nationkey,
         c.c_phone,
         c.c_acctbal,
         c.c_mktsegment,
         c.c_comment
HAVING SUM(c.c_acctbal) > 0;
