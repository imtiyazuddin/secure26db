# secure26db

# TPC-H RLS Benchmark Runner (PostgreSQL)

This project benchmarks three PostgreSQL row-security architectures against all **22 TPC-H queries**.
It is designed to evaluate the performance impact of different Row-Level Security (RLS) strategies and a secure-views alternative.

---

## Overview

### Benchmark Phases

| Phase | Label | Description |
|---|---|---|
| 1 | Indexed RLS | Baseline — policy-coverage indexes + FK indexes + **RLS implementation selected via `--rls-type`** |
| 2 | Pure Native RLS | PK indexes + FK indexes + **RLS implementation selected via `--rls-type`** (no policy-coverage indexes) |
| 3 | Secure Views | PK indexes + FK indexes + filtered views instead of RLS (**ignores `--rls-type`**) |
| 4 | Query Rewrite | PK indexes + FK indexes + pre-rewritten queries with security predicates inlined (no RLS, no views) |

---

## RLS Implementations (`--rls-type`)

For phases **1** and **2**, you can choose how RLS is applied:

- **`s` — Security-Definer RLS**
  - RLS policies call `SECURITY DEFINER` helper functions (one per protected table).
  - The helper function checks membership via the policy query.

- **`n` — Standard RLS predicate**
  - RLS policies use a standard `USING (...)` predicate built as a membership check against a predicate derived from the policy query.

> **Important:** `--rls-type` is only valid when `--phase` includes **`1`** and/or **`2`**, or **`all`**.
> Phase **3** uses secure views and Phase **4** uses query rewrite — neither uses RLS.

---

## Prerequisites

Install required Python dependencies:

```bash
pip install psycopg2-binary matplotlib numpy
```

You also need:

- PostgreSQL running locally (or reachable at `HOST_IP`)
- A loaded TPC-H database
- The running user must have `sudo` rights if you enable PostgreSQL restarts between phases
- `experiment_mapping.json` — the query-to-policy mapping file

---

## Configuration

Edit the constants at the top of the runner script before running:

```python
SUDO_PASSWORD = "your_linux_sudo_password\n"   # trailing \n required
DB_OWNER      = "postgres"                      # superuser role
OWNER_PASSWD  = "postgres123"                   # superuser password
HOST_IP       = "localhost"
DB_NAME       = "tpch"                          # postgres for 1gb and tpch_10gb for 10gb data. 
PORT          = 5432
```

The script automatically creates a `tpch_tester` role (password: `password`) and grants it the required privileges.

---

## Usage

```bash
python experiment_runner.py <mapping_file> \
  [--phase PHASE [PHASE ...]] \
  [--rls-type RLS [RLS ...]] \
  [--output FILE]
```

### Arguments

- `mapping_file` (required)
  Path to `experiment_mapping.json`

- `--phase` (optional)
  Phases to run: `1`, `2`, `3`, `4`, or `all` (default: `all`)

- `--rls-type` (optional)
  RLS implementation(s) for phases **1/2 only**: `s` or `n` (default: `s`)

- `--output` (optional)
  Output plot filename (default: `postgres_exp2_clean_4P.png`)

### Notes on `--rls-type`

- Use `--rls-type s` for **Security-Definer RLS**
- Use `--rls-type n` for **Standard RLS predicate**
- If you run **only** `--phase 3` or `--phase 4`, do **not** pass `--rls-type`

> If your current `main()` selects a single `fn` (as in the provided script), then only the **first** value is used if multiple are provided (e.g., `--rls-type s n`). Prefer passing a single value.

---

## Examples

Run all phases (default RLS type = `s` for phases 1 and 2):

```bash
python experiment_runner.py experiment_mapping.json
```

Run only Phase 1 using Security-Definer RLS:

```bash
python experiment_runner.py experiment_mapping.json --phase 1 --rls-type s
```

Run only Phase 1 using Standard RLS predicate:

```bash
python experiment_runner.py experiment_mapping.json --phase 1 --rls-type n
```

Run Phase 1 and 2 using Standard RLS predicate:

```bash
python experiment_runner.py experiment_mapping.json --phase 1 2 --rls-type n
```

Run Phase 2 and 3 (Phase 2 uses chosen RLS type, Phase 3 uses views):

```bash
python experiment_runner.py experiment_mapping.json --phase 2 3 --rls-type s
```

Run only Phase 4 (Query Rewrite — no RLS, no views, predicates inlined in SQL):

```bash
python experiment_runner.py experiment_mapping.json --phase 4
```

Run Phase 3 and 4 together:

```bash
python experiment_runner.py experiment_mapping.json --phase 3 4
```

Run all phases with a custom output filename:

```bash
python experiment_runner.py experiment_mapping.json --phase all --output my_results.png
```
### Phase 4 — Query Rewrite

Loads pre-rewritten queries from `queries/all_queries_tiered_predicates_lithe.sql` where security predicates are directly inlined into the SQL. No RLS or views are used — the optimizer sees the full query including security filters.

#compare_rls_vs_manual.py

Compares query result sets across three enforcement methods for TPC-H queries (Q1–Q22):

RLS: Runs each query as rls_user with PostgreSQL Row Level Security policies enabled.
Manual: Runs the same query with security predicates manually injected into the SQL (from all_queries_with_tiered_predicates.sql).
View: Creates secure views from vew_queries_log.txt and runs the view-rewritten queries.
Reports [MATCH] or [MISMATCH] for each pair and outputs a summary. Supports --query N to run a single query and --skip N to exclude specific queries.

#vew_queries_log.py
Generates view-based query rewrites from a tiered policy mapping (experiment_mapping_tiered.json). Uses a hierarchical algorithm where bypass views for higher-tier tables reference rls_bypass_view_* of lower-tier tables (e.g., partsupp's bypass view references rls_bypass_view_supplier instead of supplier directly). Run with --print-only to output view definitions and rewritten queries without connecting to the database.

 bash 
python vew_queries_log.py experiment_mapping_tiered.json --print-only

#vew_queries_log.py
Output of vew_queries_log.py --print-only. Contains two sections:

VIEW DEFINITIONS: CREATE OR REPLACE VIEW statements for bypass views and _view wrappers for each policy-protected table, ordered by tier.
REWRITTEN QUERIES: All 22 TPC-H queries with policy-protected table names replaced by their _view equivalents (e.g., lineitem → lineitem_view).

---

## What the Script Does

### Phase 1 — Indexed RLS (Baseline)

1. Drops all existing indexes, policies, views, and functions
2. Builds **policy-coverage indexes** on columns referenced in policy predicates
3. Builds **FK indexes** on foreign key columns
4. Applies RLS according to `--rls-type`:
   - `s`: `SECURITY DEFINER` function per table; RLS policy calls function in `USING (...)`
   - `n`: standard `USING (...)` membership predicate derived from policy view
5. Runs all 22 TPC-H queries with a hard 900s timeout and records average runtime

### Phase 2 — Pure RLS

1. Resets database (and optionally restarts PostgreSQL to clear buffers, if enabled)
2. Builds only **PK indexes** and **FK indexes** (no policy-coverage indexes)
3. Applies RLS according to `--rls-type` (same `s`/`n` options as Phase 1)
4. Runs queries with a dynamic timeout of `10× the Phase 1 baseline` (capped at 900s)

### Phase 3 — Secure Views

1. Resets database (and optionally restarts PostgreSQL, if enabled)
2. Builds only **PK indexes** and **FK indexes**
3. Creates filtered `{table}_view` for each protected table instead of RLS
4. Rewrites each TPC-H query to reference `{table}_view` instead of base table
5. Runs queries with the same dynamic timeout as Phase 2

### Phase 4 — Query Rewrite

1. Resets database (and optionally restarts PostgreSQL, if enabled)
2. Builds only **PK indexes** and **FK indexes** (no RLS, no views)
3. Loads pre-rewritten queries from `queries/all_queries_tiered_predicates_lithe.sql` (security predicates inlined into SQL)
4. Runs queries as `tpch_tester` with the same dynamic timeout and session GUCs as other phases
5. EXPLAIN ANALYZE plans saved to `RLS-results/phase4/`

---

## Output

- Prints per-query timing to stdout as each query completes
- Saves a bar chart comparing:
  - Phase 2 slowdown ratio vs Phase 1 baseline
  - Phase 3 slowdown ratio vs Phase 1 baseline
  - Phase 4 slowdown ratio vs Phase 1 baseline

Default output file: `postgres_exp2_clean_4P.png`

---

## `mapping_file` Format

Example `experiment_mapping.json`:

```json
{
  "policies": {
    "orders": {
      "file": "atomic_p11.sql",
      "raw_sql": "SELECT o.* FROM orders o WHERE ..."
    },
    "customer": { "file": "atomic_p12.sql", "raw_sql": "SELECT c.* FROM customer c WHERE ..." }
  },
  "queries": {
    "1": {
      "sql": "SELECT ... FROM lineitem WHERE ...",
      "tables_used": ["lineitem"],
      "applied_policies": {
        "lineitem": {
          "file": "atomic_p15.sql",
          "raw_sql": "SELECT l.* FROM lineitem l WHERE ...",
          "predicate": "WHERE ..."
        }
      }
    },
    "2": { "sql": "SELECT ...", "tables_used": ["supplier"] }
  }
}
```

- `policies`
  One entry per protected table; `raw_sql` is the full filtering query used to derive the RLS logic or view filtering.

- `queries`
  One entry per TPC-H query (`"1"` through `"22"`). Queries not present are skipped.

- `applied_policies`
  Policies active for a query (debug logging only).

---

## Output Log Format (Example)

```text
[SYSTEM] Loading execution plan from experiment_mapping.json...

--- PHASE 1: Running Baseline (Indexed RLS) ---
  [RLS] Using applier: Security-Definer RLS (policies applied via definer)
  -> [DEBUG] Firing Q1. Active Predicates:
       |-- lineitem: SELECT l.* FROM lineitem l JOIN supplier s ...
  [Q1] Indexed RLS Baseline: 6.8774s
...
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
| Phase 2 / 3 / 4 — baseline under 900s | `10 × baseline_time` |
| Phase 2 / 3 / 4 — baseline timed out | Hard 900s |

Timed-out queries are recorded as `900.0s` for ratio calculations in the plot.


## RLS results script

I. RLS Experiment
1. Filename: rls_exp.py 
2. Run: python3 rls_exp.py > rls-output.log           # this will write all the output logs to rls-output.log
3. MAPPING_FILE = "rls_exp.json"                       # this is set inside the code
4. Output directory structure: This creates the folder RLS-results and inside there will three folders one for each phase, where all the explain outputs are dumped per query as Qnumber_phase.json


II. Security Experiment
1. Filename: security_barrier_exp.py 
2. Run: python3 security_barrier_exp.py security_barrier_exp.json --output security_barrier_exp.png  > security_barrier-output.log           # this will write all the output logs to security_barrier-output.log, bar charts created in security_barrier_exp.png
3. MAPPING_FILE: needs to be passed during command line
4. Output directory structure: This creates the folder RLS-results-with-sb and inside there will three folders one for each phase, where all the explain outputs are dumped per query as Qnumber_phase.json
