/* ---------------------------------------------------------
P5b:   Customer visible only if ALL orders in last year
       were HIGH priority
   --------------------------------------------------------- */
SELECT c.*
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.o_custkey = c.c_custkey
      AND o.o_orderdate >= DATE '1997-01-01'
)
AND NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.o_custkey = c.c_custkey
      AND o.o_orderdate >= DATE '1997-01-01'
      AND o.o_orderpriority <> '1-URGENT'
);
