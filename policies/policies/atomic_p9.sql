/* ---------------------------------------------------------
P3c:   Customer visible only if all their orders have
        at least one lineitem shipped via TRUCK or MAIL
   --------------------------------------------------------- */
SELECT c.*
FROM customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.o_custkey = c.c_custkey
      AND NOT EXISTS (
          SELECT 1
          FROM lineitem l
          WHERE l.l_orderkey = o.o_orderkey
            AND l.l_shipmode IN ('TRUCK', 'MAIL')
      )
);
