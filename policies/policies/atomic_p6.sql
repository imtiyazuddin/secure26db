/* ---------------------------------------------------------
P2c:   Customer visible only if they have at least one order
   containing a lineitem supplied by a supplier from
   a different nation but same region as the customer
   --------------------------------------------------------- */

SELECT c.*
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    JOIN lineitem l 
         ON l.l_orderkey = o.o_orderkey
    JOIN supplier s 
         ON s.s_suppkey = l.l_suppkey
    JOIN nation ns 
         ON ns.n_nationkey = s.s_nationkey
    JOIN nation nc 
         ON nc.n_nationkey = c.c_nationkey
    WHERE o.o_custkey = c.c_custkey
      AND ns.n_regionkey = nc.n_regionkey
      AND ns.n_nationkey <> nc.n_nationkey
);
