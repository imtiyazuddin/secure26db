/* ---------------------------------------------------------
Customer and supplier who have the same comments
   --------------------------------------------------------- */
SELECT s.*
FROM customer c, supplier s
     WHERE c.c_comment LIKE '%' || s.s_comment || '%'   
AND c.c_acctbal > 0
  AND s.s_acctbal > 0;
