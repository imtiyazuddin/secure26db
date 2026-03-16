/* ---------------------------------------------------------
P4b:   Orders visible only if total revenue > 100000
   --------------------------------------------------------- */
SELECT o.*
FROM orders o
JOIN lineitem l
     ON l.l_orderkey = o.o_orderkey
GROUP BY o.o_orderkey,
         o.o_custkey,
         o.o_orderstatus,
         o.o_totalprice,
         o.o_orderdate,
         o.o_orderpriority,
         o.o_clerk,
         o.o_shippriority,
         o.o_comment
HAVING SUM(l.l_extendedprice * (1 - l.l_discount)) > 100000;
