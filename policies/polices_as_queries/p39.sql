SELECT c.*
FROM dbo.customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM dbo.orders o
    WHERE o.o_custkey = c.c_custkey
      AND NOT EXISTS (
          SELECT 1
          FROM dbo.lineitem l
          WHERE l.l_orderkey = o.o_orderkey
            AND l.l_shipmode IN ('TRUCK', 'MAIL')
      )
);