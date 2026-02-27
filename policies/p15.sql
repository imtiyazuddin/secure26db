SELECT DISTINCT c.*
FROM customer c
JOIN orders o ON o.o_custkey = c.c_custkey
JOIN lineitem l ON l.l_orderkey = o.o_orderkey
WHERE o.o_orderdate >= DATEADD(DAY, -90, CAST(GETDATE() AS DATE))
  AND l.l_quantity > 100;