/* ---------------------------------------------------------
Customer and supplier who have the same comments
   --------------------------------------------------------- */
SELECT s.*
FROM supplier s
WHERE s.s_acctbal > 0
  AND EXISTS (
        SELECT 1
        FROM customer c
        WHERE c.c_acctbal > 0
          AND c.c_comment LIKE '%' || s.s_comment || '%'
  );
