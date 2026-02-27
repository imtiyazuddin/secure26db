SET STATISTICS XML ON;
GO


SELECT l.*
FROM dbo.lineitem l
JOIN dbo.supplier s 
    ON s.s_suppkey = l.l_suppkey
JOIN dbo.nation n 
    ON n.n_nationkey = s.s_nationkey
WHERE
(
    SELECT SUM(lx.l_extendedprice * (1 - lx.l_discount))
    FROM dbo.lineitem lx
    JOIN dbo.supplier sx 
        ON sx.s_suppkey = lx.l_suppkey
    WHERE sx.s_nationkey = n.n_nationkey
)
>
(
    SELECT SUM(ly.l_extendedprice * (1 - ly.l_discount))
    FROM dbo.lineitem ly
    JOIN dbo.orders oy 
        ON oy.o_orderkey = ly.l_orderkey
    JOIN dbo.customer cy 
        ON cy.c_custkey = oy.o_custkey
    WHERE cy.c_nationkey = n.n_nationkey
);