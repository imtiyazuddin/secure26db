-- P1: Only see line items shipped within the last 5 years.
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN1 (
  schema_name IN VARCHAR2,
  table_name  IN VARCHAR2
)
RETURN VARCHAR2
AS
  v_role VARCHAR2(30);
BEGIN
  v_role := SYS_CONTEXT('TPCH_CTX','ROLE');

  IF v_role = 'TPCH_END_USERS' THEN
    RETURN 'L_SHIPDATE >= ADD_MONTHS(SYSDATE, -60)';
  ELSE
    RETURN NULL;
  END IF;
END;
/

BEGIN
  DBMS_RLS.ADD_POLICY(
    object_schema   => 'SYSTEM',
    object_name     => 'LINEITEM',
    policy_name     => 'LINEITEM_P1',
    function_schema => 'SYSTEM', -- User enforcing this policy
    policy_function => 'LINEITEM_POLICY_FN1',
    policy_type     => dbms_rls.CONTEXT_SENSITIVE,
    statement_types => 'SELECT'
  );
END;
/

-- Disable policy
BEGIN
  DBMS_RLS.ENABLE_POLICY(
    object_schema => 'SYSTEM',
    object_name   => 'LINEITEM',
    policy_name   => 'LINEITEM_P1',
    enable        =>TRUE
  );
END;
/

-- Drop policy
BEGIN
  DBMS_RLS.DROP_POLICY(
    object_schema => 'SYSTEM',
    object_name   => 'LINEITEM',
    policy_name   => 'LINEITEM_P1'
  );
END;
/

-- P2: Exclude rows where l_comment contains 'carefully'     
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN2 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');

    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'LOWER(L_COMMENT) NOT LIKE ''%carefully%''';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P3: Only allow rows where L_RETURNFLAG <> 'R' or L_DISCOUNT < 0.05
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN3 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');

    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'L_RETURNFLAG <> ''R'' OR L_DISCOUNT < 0.05';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P4: Only allow rows where line is Open and not returned
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN4 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');

    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'L_LINESTATUS = ''O'' AND L_RETURNFLAG <> ''R''';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P5: Final price between 20,000 and 200,000
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN5(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '(L_EXTENDEDPRICE * (1 - L_DISCOUNT)) BETWEEN 20000 AND 200000';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P6: Ship date ≤ commit date + 30 days
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN6(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'L_SHIPDATE <= (L_COMMITDATE + 30)';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P7: Receipt date ≤ commit date + 30 days
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN7(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'L_RECEIPTDATE <= (L_COMMITDATE + 30)';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P8: Ship mode contains AIR or RAIL
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN8(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'UPPER(L_SHIPMODE) LIKE ''%AIR%'' OR UPPER(L_SHIPMODE) LIKE ''%RAIL%''';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P9: Tax between 0.02 and 0.06
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN9(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN 'L_TAX BETWEEN 0.02 AND 0.06';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P10: Discount between 0.02 and 0.06 OR quantity between 10 and 30
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN10(schema_name IN VARCHAR2, table_name IN VARCHAR2) 
RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '(L_DISCOUNT BETWEEN 0.02 AND 0.06) OR (L_QUANTITY BETWEEN 10 AND 30)';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P11: Show LINEITEM only if the region of its order’s customer equals the region of its supplier
CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN11 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    -- Get current session role
    v_role := SYS_CONTEXT('TPCH_CTX', 'ROLE');

    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
    EXISTS (
        SELECT 1
        FROM   SYSTEM.ORDERS   o
        JOIN   SYSTEM.CUSTOMER c  ON o.o_custkey   = c.c_custkey
        JOIN   SYSTEM.NATION  nc  ON c.c_nationkey = nc.n_nationkey
        JOIN   SYSTEM.REGION  rc  ON nc.n_regionkey = rc.r_regionkey
        JOIN   SYSTEM.SUPPLIER s  ON lineitem.l_suppkey = s.s_suppkey
        JOIN   SYSTEM.NATION  ns  ON s.s_nationkey = ns.n_nationkey
        JOIN   SYSTEM.REGION  rs  ON ns.n_regionkey = rs.r_regionkey
        WHERE  o.o_orderkey = lineitem.l_orderkey
        AND    rc.r_regionkey = rs.r_regionkey
    )
';

    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P12: Orders visible if at least one lineitem has discount 5%-10% and discounted price > 1000
CREATE OR REPLACE FUNCTION SYSTEM.ORDERS_POLICY_FN1 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            EXISTS (
                SELECT 1 FROM SYSTEM.LINEITEM l
                WHERE l.l_orderkey = ORDERS.o_orderkey
                  AND l.l_discount BETWEEN 0.05 AND 0.10
                  AND l.l_extendedprice * (1 - l.l_discount) > 1000
            )
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P13: Orders visible if customer resides in EUROPE region
CREATE OR REPLACE FUNCTION SYSTEM.ORDERS_POLICY_FN2 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            EXISTS (
                SELECT 1 FROM SYSTEM.CUSTOMER c
                JOIN SYSTEM.NATION n ON n.n_nationkey = c.c_nationkey
                JOIN SYSTEM.REGION r ON r.r_regionkey = n.n_regionkey
                WHERE c.c_custkey = ORDERS.o_custkey
                  AND r.r_name = ''EUROPE''
            )
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P14: Customer visible if balance>1000 and region=ASIA
CREATE OR REPLACE FUNCTION SYSTEM.CUSTOMER_POLICY_FN1 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            c_acctbal > 1000 AND
            EXISTS (
                SELECT 1 FROM SYSTEM.NATION n
                JOIN SYSTEM.REGION r ON r.r_regionkey = n.n_regionkey
                WHERE n.n_nationkey = CUSTOMER.c_nationkey
                  AND r.r_name = ''ASIA''
            )
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P15: Customer visible if any order in last 90 days has lineitem qty>100
CREATE OR REPLACE FUNCTION SYSTEM.CUSTOMER_POLICY_FN2 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
    EXISTS (
        SELECT 1
        FROM SYSTEM.ORDERS o
        JOIN SYSTEM.LINEITEM l
            ON l.l_orderkey = o.o_orderkey
        WHERE o.o_custkey   = CUSTOMER.c_custkey
          AND o.o_orderdate >= (DATE ''1998-12-01'' - 90)
          AND l.l_quantity  > 100
    )
';

    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P16: Lineitem visible if supplier sold at least 20% of this part to customers in same region as Customer#000001111

CREATE OR REPLACE FUNCTION SYSTEM.LINEITEM_POLICY_FN12 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2

AS
    v_role  VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');

    IF v_role = 'TPCH_END_USERS' THEN
        RETURN q'[
(
    (
        SELECT COUNT(*)
        FROM SYSTEM.lineitem li
        JOIN SYSTEM.orders   o ON li.l_orderkey = o.o_orderkey
        JOIN SYSTEM.customer c ON o.o_custkey   = c.c_custkey
        JOIN SYSTEM.nation   n ON c.c_nationkey = n.n_nationkey
        JOIN SYSTEM.region   r ON n.n_regionkey = r.r_regionkey
        WHERE li.l_suppkey = lineitem.l_suppkey
          AND li.l_partkey = lineitem.l_partkey
          AND r.r_regionkey = (
                SELECT r2.r_regionkey
                FROM SYSTEM.customer me
                JOIN SYSTEM.nation n2 ON me.c_nationkey = n2.n_nationkey
                JOIN SYSTEM.region r2 ON n2.n_regionkey = r2.r_regionkey
                WHERE me.c_name = ''Customer#000001111''
          )
    )
    >=
    0.20 *
    (
        SELECT COUNT(*)
        FROM SYSTEM.lineitem li2
        WHERE li2.l_suppkey = lineitem.l_suppkey
          AND li2.l_partkey = lineitem.l_partkey
    )
)
]';

    ELSE
        RETURN NULL;
    END IF;
END;
/


-- P17: Customer visible if no cancelled orders and at least 5 orders in last 365 days
CREATE OR REPLACE FUNCTION SYSTEM.CUSTOMER_POLICY_FN3 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2

AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            NOT EXISTS (
                SELECT 1 FROM SYSTEM.ORDERS o
                WHERE o.o_custkey = CUSTOMER.c_custkey
                  AND o.o_orderstatus = ''F''
            )
            AND (
                SELECT COUNT(*) FROM SYSTEM.ORDERS o
                WHERE o.o_custkey = CUSTOMER.c_custkey
                  AND o.o_orderdate >= (DATE ''1998-12-01'' - 365)
            ) >= 5
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P18: Supplier visible if they supply at least one 'Small brushed copper' part
CREATE OR REPLACE FUNCTION SYSTEM.SUPPLIER_POLICY_FN1 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AUTHID DEFINER
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            EXISTS (
                SELECT 1 FROM SYSTEM.PARTSUPP ps
                JOIN SYSTEM.PART p ON ps.ps_partkey = p.p_partkey
                WHERE ps.ps_suppkey = SUPPLIER.s_suppkey
                  AND UPPER(p.p_type) = UPPER(''small brushed copper'')
            )
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P19: Part visible if at least one supplier is in EUROPE
CREATE OR REPLACE FUNCTION SYSTEM.PART_POLICY_FN1 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AUTHID DEFINER
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            EXISTS (
                SELECT 1 FROM SYSTEM.PARTSUPP ps
                JOIN SYSTEM.SUPPLIER s ON ps.ps_suppkey = s.s_suppkey
                JOIN SYSTEM.NATION n ON s.s_nationkey = n.n_nationkey
                JOIN SYSTEM.REGION r ON n.n_regionkey = r.r_regionkey
                WHERE ps.ps_partkey = PART.p_partkey
                  AND r.r_name = ''EUROPE''
            )
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/

-- P20: Part visible if avg supply cost < 50
CREATE OR REPLACE FUNCTION SYSTEM.PART_POLICY_FN2 (
    schema_name IN VARCHAR2,
    table_name  IN VARCHAR2
) RETURN VARCHAR2
AS
    v_role VARCHAR2(30);
BEGIN
    v_role := SYS_CONTEXT('TPCH_CTX','ROLE');
    IF v_role = 'TPCH_END_USERS' THEN
        RETURN '
            (SELECT AVG(ps.ps_supplycost) FROM SYSTEM.PARTSUPP ps
             WHERE ps.ps_partkey = PART.p_partkey) < 50
        ';
    ELSE
        RETURN NULL;
    END IF;
END;
/


    
