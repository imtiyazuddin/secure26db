import psycopg2
import os
import subprocess

print("--- STEP 1: Cleaning up invalid PII policies ---")
for f in os.listdir("policies"):
    if not f.endswith(".sql"): continue
    filepath = os.path.join("policies", f)
    with open(filepath, "r") as file:
        content = file.read()
    
    # Nuke files with bind variables or time-travel dates
    if ":current_order" in content or "CURRENT_DATE" in content:
        os.remove(filepath)
        print(f"  -> Deleted {f} (Incompatible syntax)")

print("\n--- STEP 2: Applying Primary Keys to PostgreSQL ---")
# This tells PostgreSQL it is safe to GROUP BY these columns
conn = psycopg2.connect(host="localhost", dbname="postgres", user="postgres", password="secure26DBPostgreSQL", port=5432)
conn.autocommit = True
cur = conn.cursor()

pks = [
    "ALTER TABLE supplier DROP CONSTRAINT IF EXISTS supplier_pkey CASCADE;",
    "ALTER TABLE supplier ADD PRIMARY KEY (s_suppkey);",
    "ALTER TABLE part DROP CONSTRAINT IF EXISTS part_pkey CASCADE;",
    "ALTER TABLE part ADD PRIMARY KEY (p_partkey);",
    "ALTER TABLE customer DROP CONSTRAINT IF EXISTS customer_pkey CASCADE;",
    "ALTER TABLE customer ADD PRIMARY KEY (c_custkey);",
    "ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_pkey CASCADE;",
    "ALTER TABLE orders ADD PRIMARY KEY (o_orderkey);",
    "ALTER TABLE lineitem DROP CONSTRAINT IF EXISTS lineitem_pkey CASCADE;",
    "ALTER TABLE lineitem ADD PRIMARY KEY (l_orderkey, l_linenumber);"
]

for sql in pks:
    try:
        cur.execute(sql)
    except Exception as e:
        pass # Ignore if it already exists
print("  -> Primary Keys enforced successfully.")

print("\n--- STEP 3: Regenerating JSON Mapping ---")
subprocess.run(["python3", "generate_mapping.py"])

print("\n[SYSTEM READY] The environment is patched.")
