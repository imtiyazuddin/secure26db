explain analyze SELECT COUNT(*)
FROM orders o
WHERE
    -- p holds
    o.o_totalprice  > 150000
    AND o.o_orderstatus = 'F'
    AND o.o_orderdate   > '1994-12-31'
    AND EXISTS (
        SELECT 1 FROM orders o2
        WHERE o2.o_custkey    = o.o_custkey
          AND o2.o_orderstatus = 'F'
    )
    -- q does NOT hold  (¬q)
    AND NOT (
        o.o_totalprice > 50000
        AND o.o_orderdate > '1993-12-31'
        AND EXISTS (
            SELECT 1 FROM orders o3
            WHERE o3.o_custkey    = o.o_custkey
              AND o3.o_orderstatus = 'F'
        )
    );

"Aggregate  (cost=8202111917.35..8202111917.36 rows=1 width=8) (actual time=182124.952..182124.953 rows=1 loops=1)"
"  ->  Hash Join  (cost=49254.77..8202111578.80 rows=135420 width=0) (actual time=182124.948..182124.949 rows=0 loops=1)"
"        Hash Cond: (o.o_custkey = o2.o_custkey)"
"        ->  Seq Scan on orders o  (cost=0.00..8202060462.00 rows=135420 width=8) (actual time=182124.946..182124.947 rows=0 loops=1)"
"              Filter: ((o_totalprice > '150000'::numeric) AND (o_orderdate > '1994-12-31'::date) AND ((o_orderstatus)::text = 'F'::text) AND ((o_totalprice <= '50000'::numeric) OR (o_orderdate <= '1993-12-31'::date) OR (NOT EXISTS(SubPlan 1))))"
"              Rows Removed by Filter: 1500000"
"              SubPlan 1"
"                ->  Seq Scan on orders o3  (cost=0.00..49212.00 rows=9 width=0) (actual time=9.136..9.136 rows=1 loops=19894)"
"                      Filter: ((o_custkey = o.o_custkey) AND ((o_orderstatus)::text = 'F'::text))"
"                      Rows Removed by Filter: 177033"
"        ->  Hash  (cost=48172.75..48172.75 rows=86562 width=8) (never executed)"
"              ->  HashAggregate  (cost=47307.12..48172.75 rows=86562 width=8) (never executed)"
"                    Group Key: o2.o_custkey"
"                    ->  Seq Scan on orders o2  (cost=0.00..45462.00 rows=738050 width=8) (never executed)"
"                          Filter: ((o_orderstatus)::text = 'F'::text)"
"Planning Time: 0.447 ms"
"Execution Time: 182125.872 ms"
