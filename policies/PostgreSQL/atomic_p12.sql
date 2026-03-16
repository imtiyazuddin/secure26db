/* ---------------------------------------------------------
P4c:   Customer visible only if total revenue from suppliers
   in same region exceeds 200000
   --------------------------------------------------------- */
SELECT c.*
FROM customer c
JOIN orders o
     ON o.o_custkey = c.c_custkey
JOIN lineitem l
     ON l.l_orderkey = o.o_orderkey
JOIN supplier s
     ON s.s_suppkey = l.l_suppkey
JOIN nation ns
     ON ns.n_nationkey = s.s_nationkey
JOIN nation nc
     ON nc.n_nationkey = c.c_nationkey
GROUP BY c.c_custkey,
         c.c_name,
         c.c_address,
         c.c_nationkey,
         c.c_phone,
         c.c_acctbal,
         c.c_mktsegment,
         c.c_comment
HAVING SUM(
        CASE 
           WHEN ns.n_regionkey = nc.n_regionkey
           THEN l.l_extendedprice * (1 - l.l_discount)
           ELSE 0
        END
       ) > 200000;
