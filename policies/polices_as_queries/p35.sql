SET STATISTICS XML ON;
GO


SELECT l.*
FROM dbo.lineitem l
WHERE DATEDIFF(DAY, l.l_shipdate, l.l_receiptdate) >
(
    SELECT AVG(DATEDIFF(DAY, l2.l_shipdate, l2.l_receiptdate))
    FROM dbo.lineitem l2
    WHERE l2.l_shipmode = l.l_shipmode
);