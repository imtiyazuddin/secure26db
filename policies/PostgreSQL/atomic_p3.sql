/* ---------------------------------------------------------
 P1c:  Lineitem visible only if supplier and customer
        are from different nations but same region
   --------------------------------------------------------- */
SELECT l.*
FROM lineitem l
JOIN supplier s ON s.s_suppkey = l.l_suppkey
JOIN orders o ON o.o_orderkey = l.l_orderkey
JOIN customer c ON c.c_custkey = o.o_custkey
JOIN nation ns ON ns.n_nationkey = s.s_nationkey
JOIN nation nc ON nc.n_nationkey = c.c_nationkey
WHERE ns.n_nationkey <> nc.n_nationkey
  AND ns.n_regionkey = nc.n_regionkey;
