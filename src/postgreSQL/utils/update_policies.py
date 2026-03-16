import urllib.request
import os

url = "https://raw.githubusercontent.com/ahanapradhan/PostgreSQL_RLS/main/tpch_p1_p50.sql"
os.makedirs("policies", exist_ok=True)

# 1. Wipe out the old incompatible policies
for f in os.listdir("policies"):
    if f.endswith(".sql"):
        os.remove(os.path.join("policies", f))

# 2. Download the exact GitHub file
print("Downloading PostgreSQL-native policies from GitHub...")
req = urllib.request.urlopen(url)
sql_data = req.read().decode('utf-8')

# 3. Split by semicolon
raw_policies = [p.strip() for p in sql_data.split(';') if len(p.strip()) > 10]

# 4. Save Policy 21 and above
saved_count = 0
for i, policy_sql in enumerate(raw_policies):
    policy_id = i + 1 
    if policy_id >= 21:
        with open(f"policies/p{policy_id}.sql", "w") as f:
            f.write(policy_sql + ";\n")
        saved_count += 1

print(f"[SUCCESS] Wiped old files. Saved {saved_count} new policies (P21 onwards).")
