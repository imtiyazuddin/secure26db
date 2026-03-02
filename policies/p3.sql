/*
on lineitem 
*/
SELECT l.*
FROM lineitem l, partsupp ps, part p
     WHERE ps.ps_partkey = l.l_partkey
    AND ps.ps_suppkey = l.l_suppkey
     AND p.p_partkey = l.l_partkey
AND ps.ps_supplycost BETWEEN p.p_retailprice * 0.5
                           AND p.p_retailprice * 1.2;
