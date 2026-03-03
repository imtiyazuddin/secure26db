-- P1: Attribute/Join predicate
--------------------------------
/* ---------------------------------------------------------
   P1a: Supplier visible only if supplier
          has shipped items within a time frame
   --------------------------------------------------------- */
SELECT s.*
FROM supplier s
JOIN lineitem l ON l.l_suppkey = s.s_suppkey
WHERE l.l_shipdate >= DATE '1995-05-05' - INTERVAL '180' DAY;
