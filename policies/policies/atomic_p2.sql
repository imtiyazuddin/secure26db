/* ---------------------------------------------------------
  P1b:  Lineitem visible only if supplier and customer
   belong to the same nation and order priority is high
   --------------------------------------------------------- */
SELECT l.*
FROM lineitem l
JOIN orders o 
     ON o.o_orderkey = l.l_orderkey
JOIN customer c 
     ON c.c_custkey = o.o_custkey
JOIN supplier s 
     ON s.s_suppkey = l.l_suppkey
WHERE s.s_nationkey = c.c_nationkey
  AND o.o_orderpriority IN ('1-URGENT', '2-HIGH');
