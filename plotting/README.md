# TPCH RLS Experiment — Pipeline README

## Overview

This pipeline has two steps:

1. **Parse** a raw experiment log (`.txt`) into a structured CSV data file
2. **Plot** the CSV data file into a ratio comparison chart

---

## Scripts

| Script | Input | Output |
|---|---|---|
| `parse_log.py` | `experiment_log.txt` | `plot_data.csv` |
| `plot_ratios.py` | `plot_data.csv` | `query_ratios_valid.png` |

---

## Step 1 — Parse the Log File

The log file is the raw stdout output from the experiment runner. It contains timing results across three phases:

- **Phase 1** — Indexed RLS Baseline
- **Phase 2** — Pure Native RLS (mapped to `PK-Indexed RLS` column)
- **Phase 3** — Secure Views

Run:

```bash
python parse_log.py <input_log.txt> <output_data.csv>
```

**Example:**

```bash
python parse_log.py experiment_log.txt plot_data.csv
```

### Output CSV format

```
Qid,Indexed RLS,PK-Indexed RLS,Views
Q1,6.8774,6.8825,3.0432
Q2,0.2526,0.2516,2.1315
...
```

- One row per query (Q1–Q22)
- Times are in **seconds**
- Queries that timed out appear as `900` (the `TIMEOUT` constant)

---

## Step 2 — Plot the Data

Takes the CSV produced in Step 1 and generates a grouped bar chart showing the performance ratio of each approach relative to the Indexed RLS baseline.

Run:

```bash
python plot_ratios.py <input_data.csv>
```

**Example:**

```bash
python plot_ratios.py plot_data.csv
```

### Output

- **`query_ratios_valid.png`** — saved in the current directory
- Bars show the ratio of `PK-Indexed RLS / Indexed RLS` and `Views / Indexed RLS`
- Queries where the baseline itself timed out are **excluded** from the plot
- Queries where only the numerator timed out are shown as red hatched bars labelled `expensive`
- The dashed reference line at `1.0×` marks parity with the baseline

---

## Full Example Run

```bash
# Step 1: parse the raw log
python parse_log.py experiment_log.txt plot_data.csv

# Step 2: generate the plot
python plot_ratios.py plot_data.csv
```

---

## Dependencies

```bash
pip install pandas numpy matplotlib
```
