SELECT c.*
FROM customer c
JOIN nation n ON n.n_nationkey = c.c_nationkey
JOIN region r ON r.r_regionkey = n.n_regionkey
WHERE c.c_acctbal > 1000
  AND r.r_name = 'ASIA';