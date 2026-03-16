/* ---------------------------------------------------------
P2b:   Orders visible only if they contain at least one
   late-shipped lineitem with discount > 5%
   --------------------------------------------------------- */
SELECT o.*
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM lineitem l
    WHERE l.l_orderkey = o.o_orderkey
      AND l.l_shipdate > l.l_commitdate
      AND l.l_discount > 0.05
);
