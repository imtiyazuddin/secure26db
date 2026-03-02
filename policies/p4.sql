/* on partsupp */
SELECT ps.*
FROM partsupp ps
WHERE NOT EXISTS (
    SELECT 1
    FROM lineitem l
    WHERE l.l_partkey = ps.ps_partkey
      AND l.l_extendedprice 
          < ps.ps_supplycost * l.l_quantity   
);
