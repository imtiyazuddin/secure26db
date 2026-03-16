----================================
-- P2: Existence/Semi-Join
--------------------------------
/* ---------------------------------------------------------
P2a:   Customer visible only if at least one completed order
   --------------------------------------------------------- */
SELECT c.*
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.o_custkey = c.c_custkey
      AND o.o_orderstatus = 'F'
);
