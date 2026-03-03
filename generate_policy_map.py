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

def extract_all_conditions(sql):
    conditions = []
    
    # 1. Extract JOIN ... ON conditions
    # Stops when it hits the next major SQL keyword
    on_clauses = re.findall(r'\bON\s+(.*?)(?=\b(?:INNER|LEFT|RIGHT|FULL|CROSS|OUTER|JOIN|WHERE|GROUP|HAVING|ORDER|LIMIT|;)\b|$)', sql, re.IGNORECASE | re.DOTALL)
    if on_clauses:
        conditions.extend([c.strip() for c in on_clauses])
        
    # 2. Extract WHERE condition
    match_where = re.search(r'\bWHERE\s+(.*?)(?=\b(?:GROUP|HAVING|ORDER|LIMIT|;)\b|$)', sql, re.IGNORECASE | re.DOTALL)
    if match_where:
        conditions.append(match_where.group(1).strip())
        
    # 3. Extract HAVING condition
    match_having = re.search(r'\bHAVING\s+(.*?)(?=\b(?:ORDER|LIMIT|;)\b|$)', sql, re.IGNORECASE | re.DOTALL)
    if match_having:
        conditions.append(match_having.group(1).strip())
        
    if not conditions:
        return "TRUE"
        
    # Combine them all into one massive string for the index generator to parse
    return " AND ".join(conditions)

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

        # Extract all ON, WHERE, and HAVING predicates
        combined_predicate = extract_all_conditions(clean_sql)

        policy_mapping[filename] = {
            "table": table_name,
            "predicate": combined_predicate
        }
        print(f" -> Processed {filename} (Table: {table_name})")

    with open(OUTPUT_JSON, 'w') as f:
        json.dump(policy_mapping, f, indent=4)
    
    print(f"\n[SUCCESS] Saved mapping for {len(policy_mapping)} policies to {OUTPUT_JSON}")

if __name__ == "__main__":
    generate_policy_mapping()
