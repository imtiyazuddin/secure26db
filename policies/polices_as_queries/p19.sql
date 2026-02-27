SELECT DISTINCT p.*
FROM dbo.part p
JOIN dbo.partsupp ps 
    ON ps.ps_partkey = p.p_partkey
JOIN dbo.supplier s 
    ON s.s_suppkey = ps.ps_suppkey
JOIN dbo.nation n 
    ON n.n_nationkey = s.s_nationkey
JOIN dbo.region r 
    ON r.r_regionkey = n.n_regionkey
WHERE r.r_name = 'EUROPE';
