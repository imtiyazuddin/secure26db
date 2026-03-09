#!/usr/bin/env python3
"""Extract timings from two experiment logs and write a columnar data file.

This script expects the raw log files for 1GB and 10GB runs. It produces:
  - slowdown_data.parquet (columnar)
  - slowdown_data.csv (human-readable)

Usage:
  python extract_slowdown_data.py definer_atomic_single_1gb.txt definer_atomic_single_10gb.txt
"""

import re
import sys
import numpy as np
import pandas as pd

PATTERNS = {
    'Indexed RLS': re.compile(r"\[Q(?P<q>\d+)\]\s+Indexed RLS Baseline:\s+(?P<val>TIMEOUT|[0-9]+\.[0-9]+|[0-9]+)s", re.IGNORECASE),
    'Pure RLS': re.compile(r"\[Q(?P<q>\d+)\]\s+Pure RLS Avg:\s+(?P<val>TIMEOUT|[0-9]+\.[0-9]+|[0-9]+)s?", re.IGNORECASE),
    'Views': re.compile(r"\[Q(?P<q>\d+)\]\s+Secure Views Avg:\s+(?P<val>TIMEOUT|[0-9]+\.[0-9]+|[0-9]+)s?", re.IGNORECASE),
}


def parse_log(path: str):
    out = {k: {} for k in PATTERNS}
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        txt = f.read()
    for case, pat in PATTERNS.items():
        for m in pat.finditer(txt):
            q = int(m.group('q'))
            raw = m.group('val').strip()
            if raw.upper() == 'TIMEOUT':
                out[case][q] = (np.nan, True)
            else:
                out[case][q] = (float(raw), False)
    return out


def main():
    if len(sys.argv) != 3:
        print("Usage: python extract_slowdown_data.py <1gb_log> <10gb_log>")
        sys.exit(2)

    one = parse_log(sys.argv[1])
    ten = parse_log(sys.argv[2])

    all_q = sorted(set().union(*[
        set(one[c].keys()) | set(ten[c].keys()) for c in PATTERNS
    ]))

    rows = []
    for case in PATTERNS:
        for q in all_q:
            v1, t1 = one[case].get(q, (np.nan, True))
            v10, t10 = ten[case].get(q, (np.nan, True))
            slowdown = round((v10 / v1), 2) if (np.isfinite(v1) and np.isfinite(v10) and v1 != 0) else np.nan
            rows.append({
                'query': f'Q{q}',
                'query_num': q,
                'case': case,
                'time_1gb_s': v1,
                'time_10gb_s': v10,
                'timeout_1gb': bool(t1),
                'timeout_10gb': bool(t10),
                'slowdown_10gb_over_1gb': slowdown,
            })

    df = pd.DataFrame(rows).sort_values(['case', 'query_num']).reset_index(drop=True)
    df.to_csv('slowdown_data.csv', index=False)
    print('Wrote slowdown_data.csv')


if __name__ == '__main__':
    main()
