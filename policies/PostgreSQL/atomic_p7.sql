----================================
-- P3: Universal/Anti-existence
--------------------------------
/* ---------------------------------------------------------
P3a:   Part visible only if it has never been ordered
        in quantities greater than 200
   --------------------------------------------------------- */
SELECT p.*
FROM part p
WHERE NOT EXISTS (
    SELECT 1
    FROM lineitem l
    WHERE l.l_partkey = p.p_partkey
      AND l.l_quantity > 200
);
