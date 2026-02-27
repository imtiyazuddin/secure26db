SELECT DISTINCT o.*
FROM orders o
JOIN lineitem l ON l.l_orderkey = o.o_orderkey
WHERE l.l_discount BETWEEN 0.05 AND 0.10
  AND l.l_extendedprice * (1 - l.l_discount) > 1000;