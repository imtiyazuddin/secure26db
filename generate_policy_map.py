import os
import re
import json

POLICIES_DIR = "policies"
OUTPUT_JSON = "policy_index_mapping.json"

# TPC-H validation map
PK_MAP = {
    'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
    'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
    'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
}

def extract_predicate(sql):
    # 1. Try to find a standard WHERE clause
    match_where = re.search(r'\bWHERE\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
    if match_where:
        return match_where.group(1).replace(';', '').strip()
    
    # 2. If no WHERE exists, look for a HAVING clause (Atomic Aggregate Policies)
    match_having = re.search(r'\bHAVING\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
    if match_having:
        return "HAVING " + match_having.group(1).replace(';', '').strip()
        
    return "TRUE"

def generate_policy_mapping():
    if not os.path.exists(POLICIES_DIR):
        print(f"[!] Directory '{POLICIES_DIR}' not found.")
        return

    policy_mapping = {}

    for filename in os.listdir(POLICIES_DIR):
        if not filename.endswith(".sql"):
            continue

        filepath = os.path.join(POLICIES_DIR, filename)
        with open(filepath, "r") as f:
            raw_sql = f.read()

        # Strip comments to safely parse the SQL
        clean_sql = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', raw_sql, flags=re.DOTALL)).strip()

        # Identify the base table
        match = re.search(r'\bFROM\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
        table_name = "unknown"
        if match:
            extracted_table = match.group(1).lower()
            if extracted_table in PK_MAP:
                table_name = extracted_table

        # Extract the predicate
        predicate = extract_predicate(clean_sql)

        # Map the filename directly to its attributes
        policy_mapping[filename] = {
            "table": table_name,
            "predicate": predicate
        }
        print(f" -> Processed {filename} (Table: {table_name})")

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(policy_mapping, f, indent=4)
    
    print(f"\n[SUCCESS] Saved mapping for {len(policy_mapping)} policies to {OUTPUT_JSON}")

if __name__ == "__main__":
    generate_policy_mapping()
