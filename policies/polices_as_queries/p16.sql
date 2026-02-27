SET STATISTICS XML ON;
GO

SELECT l.*
FROM dbo.lineitem l
JOIN dbo.orders o 
    ON o.o_orderkey = l.l_orderkey
JOIN dbo.customer c 
    ON c.c_custkey = o.o_custkey
JOIN dbo.nation n 
    ON n.n_nationkey = c.c_nationkey
WHERE l.l_quantity >= 0.2 *
(
    SELECT SUM(l2.l_quantity)
    FROM dbo.lineitem l2
    WHERE l2.l_partkey = l.l_partkey
)
AND n.n_regionkey =
(
    SELECT n2.n_regionkey
    FROM dbo.customer c2
    JOIN dbo.nation n2 
        ON n2.n_nationkey = c2.c_nationkey
    WHERE c2.c_custkey = 1111
);