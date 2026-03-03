/* ---------------------------------------------------------
P5c:  Lineitem visible only if its supplier’s nation
        has higher total export value than import value
   --------------------------------------------------------- */
SELECT l.*
FROM lineitem l
JOIN supplier s ON s.s_suppkey = l.l_suppkey
JOIN nation n ON n.n_nationkey = s.s_nationkey
WHERE
(
    SELECT SUM(lx.l_extendedprice * (1 - lx.l_discount))
    FROM lineitem lx
    JOIN supplier sx ON sx.s_suppkey = lx.l_suppkey
    WHERE sx.s_nationkey = n.n_nationkey
)
>
(
    SELECT SUM(ly.l_extendedprice * (1 - ly.l_discount))
    FROM lineitem ly
    JOIN orders oy ON oy.o_orderkey = ly.l_orderkey
    JOIN customer cy ON cy.c_custkey = oy.o_custkey
    WHERE cy.c_nationkey = n.n_nationkey
);
