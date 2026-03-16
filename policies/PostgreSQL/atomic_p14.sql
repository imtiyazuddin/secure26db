/* ---------------------------------------------------------
P5b:  Lineitem visible only if its shipping delay
        exceeds the average delay for that ship mode
   --------------------------------------------------------- */
SELECT l.*
FROM lineitem l
WHERE (l.l_receiptdate - l.l_shipdate) >
      (
        SELECT AVG(l2.l_receiptdate - l2.l_shipdate)
        FROM lineitem l2
        WHERE l2.l_shipmode = l.l_shipmode
      );
