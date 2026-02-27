SET STATISTICS XML ON;
GO


WITH OrderStats AS
(
    SELECT 
        l.l_orderkey,
        COUNT(*) AS n,
        SUM(l.l_quantity) AS sum_x,
        SUM(l.l_discount) AS sum_y,
        SUM(l.l_quantity * l.l_discount) AS sum_xy,
        SUM(l.l_quantity * l.l_quantity) AS sum_x2,
        SUM(l.l_discount * l.l_discount) AS sum_y2
    FROM dbo.lineitem l
    GROUP BY l.l_orderkey
)
SELECT o.*
FROM dbo.orders o
JOIN OrderStats s
    ON s.l_orderkey = o.o_orderkey
WHERE
(
    s.n * s.sum_xy - s.sum_x * s.sum_y
)
/
NULLIF(
    SQRT(
        (s.n * s.sum_x2 - POWER(s.sum_x, 2))
        *
        (s.n * s.sum_y2 - POWER(s.sum_y, 2))
    ),
    0
) > 0;