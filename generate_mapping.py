import os
import re
import json

QUERIES_FILE = 'queries/all_queries.sql'
POLICIES_DIR = 'policies'
OUTPUT_JSON = 'experiment_mapping.json'

# Hardcoded TPC-H Primary Key Map
PK_MAP = {
    'region': 'r_regionkey', 'nation': 'n_nationkey', 'part': 'p_partkey',
    'supplier': 's_suppkey', 'partsupp': 'ps_partkey, ps_suppkey',
    'customer': 'c_custkey', 'orders': 'o_orderkey', 'lineitem': 'l_orderkey, l_linenumber'
}

def get_tables_in_sql(sql_query):
    words = re.findall(r'\b[a-zA-Z_]+\b', sql_query.lower())
    return list(set(words).intersection(set(PK_MAP.keys())))

def extract_predicate(sql):
    # Extracts the pure WHERE clause for Native RLS injection
    match = re.search(r'WHERE\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).replace(';', '').strip()
    return "TRUE"

print(f"[LOG] Scanning queries from: {QUERIES_FILE}")
queries_dict = {}
with open(QUERIES_FILE, 'r') as f:
    sql_text = f.read()
raw_queries = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)).split(';')
for i, q in enumerate([q.strip() for q in raw_queries if len(q.strip()) > 10]): 
    queries_dict[i + 1] = q

print(f"[LOG] Scanning policies from: {POLICIES_DIR}/")
policies_dict = {}
for p_file in os.listdir(POLICIES_DIR):
    if not p_file.endswith('.sql'): continue
    with open(os.path.join(POLICIES_DIR, p_file), 'r') as f: clean_sql = f.read()
    clean_sql = re.sub(r'--.*', '', re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)).strip()
    
    match = re.search(r'\bFROM\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
    if match:
        table_name = match.group(1).lower()
        if table_name in PK_MAP:
            predicate = extract_predicate(clean_sql)
            policies_dict[table_name] = {
                "file": p_file,
                "raw_sql": clean_sql.replace(';', ''),
                "predicate": predicate
            }
            print(f"  -> Found policy for '{table_name}' in {p_file}")

# Build the execution matrix
experiment_plan = {
    "metadata": {
        "description": "Universal TPC-H Query to Policy Mapping",
        "policies_loaded": list(policies_dict.keys())
    },
    "policies": policies_dict,
    "queries": {}
}

for q_id, q_sql in queries_dict.items():
    tables_used = get_tables_in_sql(q_sql)
    active_policies = {t: policies_dict[t] for t in tables_used if t in policies_dict}
    
    if active_policies:
        experiment_plan["queries"][q_id] = {
            "sql": q_sql,
            "tables_used": tables_used,
            "applied_policies": active_policies
        }

with open(OUTPUT_JSON, 'w') as f:
    json.dump(experiment_plan, f, indent=4)

print(f"\n[SUCCESS] Universal mapping saved to {OUTPUT_JSON}. Ready for Postgres and Oracle.")
