SELECT 
    s.s_suppkey,
    s.s_name,
    s.s_address,
    s.s_nationkey,
    s.s_phone,
    s.s_acctbal,
    s.s_comment
FROM dbo.supplier s
JOIN dbo.lineitem l 
    ON l.l_suppkey = s.s_suppkey
JOIN dbo.orders o 
    ON o.o_orderkey = l.l_orderkey
JOIN dbo.customer c 
    ON c.c_custkey = o.o_custkey
JOIN dbo.nation n 
    ON n.n_nationkey = c.c_nationkey
JOIN dbo.region r 
    ON r.r_regionkey = n.n_regionkey
GROUP BY 
    s.s_suppkey,
    s.s_name,
    s.s_address,
    s.s_nationkey,
    s.s_phone,
    s.s_acctbal,
    s.s_comment
HAVING COUNT(DISTINCT r.r_regionkey) >= 2;
