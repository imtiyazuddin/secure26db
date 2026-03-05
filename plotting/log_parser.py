import re
import sys
from collections import defaultdict

def parse_log_file(input_path, output_path):
    # Map log phase labels to output column names
    PHASE_MAP = {
        "Indexed RLS Baseline": "Indexed RLS",
        "Pure RLS Avg":         "PK-Indexed RLS",
        "Secure Views Avg":     "Views",
    }
    COLUMNS = ["Indexed RLS", "PK-Indexed RLS", "Views"]

    # Pattern: [Q1] Indexed RLS Baseline: 6.8774s
    pattern = re.compile(
        r'\[Q(\d+)\]\s+(.+?):\s+([\d.]+)s'
    )

    results = defaultdict(dict)

    with open(input_path, 'r') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                qid    = int(m.group(1))
                label  = m.group(2).strip()
                time   = float(m.group(3))
                col    = PHASE_MAP.get(label)
                if col:
                    results[qid][col] = time

    all_qids = sorted(results.keys())

    with open(output_path, 'w') as f:
        f.write("Qid," + ",".join(COLUMNS) + "\n")
        for qid in all_qids:
            row = [f"Q{qid}"]
            for col in COLUMNS:
                val = results[qid].get(col, "N/A")
                row.append(str(val) if val != "N/A" else "N/A")
            f.write(",".join(row) + "\n")

    print(f"Parsed {len(all_qids)} queries -> {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python parse_log.py <input.txt> <output.txt>")
        sys.exit(1)
    parse_log_file(sys.argv[1], sys.argv[2])
