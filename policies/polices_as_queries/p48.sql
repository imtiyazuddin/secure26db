SELECT l.*
FROM dbo.lineitem l
JOIN dbo.orders o
    ON o.o_orderkey = l.l_orderkey
CROSS APPLY (
    SELECT
        ABS(DATEDIFF(DAY, o.o_orderdate, l.l_shipdate))  AS ship_diff,
        ABS(DATEDIFF(DAY, o.o_orderdate, l.l_receiptdate)) AS receipt_diff
) d
WHERE d.ship_diff < d.receipt_diff;
