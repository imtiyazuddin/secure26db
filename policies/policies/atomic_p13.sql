----================================
-- P5: Statistical
--------------------------------
/* ---------------------------------------------------------
P5a:   Lineitem visible only if its order date is closer
        to ship date than to receipt date
   --------------------------------------------------------- */
SELECT l.*
FROM lineitem l
JOIN orders o ON o.o_orderkey = l.l_orderkey
WHERE ABS(o.o_orderdate - l.l_shipdate)
    < ABS(o.o_orderdate - l.l_receiptdate);
