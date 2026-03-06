# secure26db

# TPC-H RLS Benchmark Runner

Benchmarks three PostgreSQL row-security architectures against all 22 TPC-H queries:

| Phase | Label | Description |
|---|---|---|
| 1 | Indexed RLS | Baseline — policy indexes + FK indexes + RLS via `SECURITY DEFINER` functions |
| 2 | Pure Native RLS | PK indexes + FK indexes + same RLS (no policy-coverage indexes) |
| 3 | Secure Views | PK indexes + FK indexes + filtered views instead of RLS |

---

## Prerequisites

```bash
pip install psycopg2-binary matplotlib numpy
```

- PostgreSQL running locally (or reachable at `HOST_IP`)
- A loaded TPC-H database
- The running user must have `sudo` rights to restart PostgreSQL between phases
- `experiment_mapping.json` — the query-to-policy mapping file

---

## Configuration

Edit the constants at the top of the script before running:

```python
SUDO_PASSWORD = "your_linux_sudo_password\n"   # trailing \n required
DB_OWNER      = "postgres"                      # superuser role
OWNER_PASSWD  = "postgres123"                   # superuser password
HOST_IP       = "localhost"
DB_NAME       = "tpch"
PORT          = 5432
```

The script will automatically create a `tpch_tester` role (password: `password`) and grant it the necessary privileges.

---

## Usage

```bash
python experiment_runner.py <mapping_file> [--phase PHASE [PHASE ...]] [--output FILE]
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `mapping_file` | ✅ | Path to `experiment_mapping.json` |
| `--phase` | ❌ | Phases to run: `1`, `2`, `3`, or `all` (default: `all`) |
| `--output` | ❌ | Output plot filename (default: `postgres_exp2_clean_4P.png`) |

---

## Examples

```bash
# Run all three phases
python experiment_runner.py experiment_mapping.json

# Run only Phase 1 (Indexed RLS baseline)
python experiment_runner.py experiment_mapping.json --phase 1

# Run Phase 2 and 3 only (skip baseline)
python experiment_runner.py experiment_mapping.json --phase 2 3

# Run all phases with a custom output filename
python experiment_runner.py experiment_mapping.json --phase all --output my_results.png

# Run against a mapping file in another directory
python experiment_runner.py /data/mappings/custom_mapping.json --phase 1 2
```

---

## What the Script Does

### Phase 1 — Indexed RLS (Baseline)
1. Drops all existing indexes, policies, views, and functions
2. Builds **policy-coverage indexes** on columns referenced in policy predicates
3. Builds **FK indexes** on foreign key columns
4. Creates one `SECURITY DEFINER` function per policy table — the function wraps the `raw_sql` from the mapping file and is called from the `USING` clause of each RLS policy
5. Runs all 22 TPC-H queries with a hard 900s timeout; records average of 3 runs

### Phase 2 — Pure RLS
1. Resets database and restarts PostgreSQL (clears shared buffers)
2. Builds only **PK indexes** and **FK indexes** (no policy-coverage indexes)
3. Applies the same `SECURITY DEFINER` RLS policies as Phase 1
4. Runs queries with a dynamic timeout of `10× the Phase 1 baseline` (capped at 900s)

### Phase 3 — Secure Views
1. Resets database and restarts PostgreSQL
2. Builds only **PK indexes** and **FK indexes**
3. Creates a filtered `{table}_view` for each policy table instead of RLS
4. Rewrites each TPC-H query to reference `{table}_view` instead of the base table
5. Runs queries with the same dynamic timeout as Phase 2

### Output
- Prints per-query timing to stdout as each query completes
- Saves a bar chart comparing Phase 2 and Phase 3 slowdown ratios relative to the Phase 1 baseline

---

## mapping_file Format

```json
{
    "policies": {
        "orders": {
            "file": "atomic_p11.sql",
            "raw_sql": "SELECT o.* FROM orders o WHERE ..."
        },
        "customer": { "..." : "..." },
        "lineitem": { "..." : "..." }
    },
    "queries": {
        "1": {
            "sql": "SELECT ... FROM lineitem WHERE ...",
            "tables_used": ["lineitem"],
            "applied_policies": {
                "lineitem": {
                    "file": "atomic_p15.sql",
                    "raw_sql": "SELECT l.* FROM lineitem l WHERE ..."
                    "predicate": "WHERE ..."

                }
            }
        },
        "2": { "..." : "..." }
    }
}
```

- `policies` — one entry per protected table; `raw_sql` is the full filtering query used to build the `SECURITY DEFINER` function
- `queries` — one entry per TPC-H query (keys `"1"` through `"22"`); queries not present are skipped
- `applied_policies` — which policies are active for a given query (used for debug logging only)

---

## Output Log Format

```
[SYSTEM] Loading execution plan from experiment_mapping.json...

--- PHASE 1: Running Baseline (Indexed RLS) ---
  -> Building policy index on orders for column: (o_orderkey)
  -> Building FK index on lineitem: (l_orderkey)
  -> [LOG] Securing orders
     |-- Applied Policy: USING (rls_bypass_fn_orders(o_orderkey))
  -> [DEBUG] Firing Q1. Active Predicates:
       |-- lineitem: SELECT l.* FROM lineitem l JOIN supplier s ...
  [Q1] Indexed RLS Baseline: 6.8774s

  [Q2] Indexed RLS Baseline: 0.2526s
  ...
  [Q22] Indexed RLS Baseline: TIMEOUT (> 900s)

--- PHASE 2: Running Exp 1 (Pure Native RLS) ---
  ...

--- PHASE 3: Running Exp 2 (Secure Views) ---
  ...

Saved as postgres_exp2_clean_4P.png
```

---

## Timeout Behaviour

| Condition | Timeout used |
|---|---|
| Phase 1 | Hard 900s per query |
| Phase 2 / 3 — baseline was under 900s | `10 × baseline_time` |
| Phase 2 / 3 — baseline timed out | Hard 900s |

Timed-out queries are recorded as `900.0s` for ratio calculations in the plot.
