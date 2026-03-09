#!/usr/bin/env python3
"""Plot 1GB→10GB slowdown for Indexed RLS, Pure RLS, and Views.

Usage:
  python plot_slowdown.py slowdown_data.parquet
  # or
  python plot_slowdown.py slowdown_data.csv

Outputs:
  slowdown_plot.png
"""

import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def read_data(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        sep = ','
        return pd.read_csv(path, sep=sep)
    raise ValueError(f"Unsupported file type: {ext}. Use ..csv")


def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_slowdown.py <slowdown_data.csv>")
        sys.exit(2)

    df = read_data(sys.argv[1])

    # Keep only rows where both timings exist so slowdown is defined
    dfp = df[np.isfinite(df['slowdown_10gb_over_1gb'])].copy()
    if dfp.empty:
        raise RuntimeError("No rows have a finite slowdown_10gb_over_1gb. Check input data.")

    # Query ordering
    all_q = sorted(dfp['query_num'].unique())

    # Geometric mean per case
    geo = (dfp.groupby('case')['slowdown_10gb_over_1gb']
           .apply(lambda s: float(np.exp(np.mean(np.log(s.values)))))
           .reset_index(name='geo_mean_slowdown'))

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True,
                             gridspec_kw={'height_ratios': [3, 1]})

    ax = axes[0]
    for case, g in dfp.groupby('case'):
        g = g.sort_values('query_num')
        ax.plot(g['query_num'], g['slowdown_10gb_over_1gb'], marker='o', linewidth=2, label=case)

    ax.axhline(1.0, color='gray', linestyle='--', linewidth=1)
    ax.set_xticks(all_q)
    ax.set_xticklabels([f'Q{i}' for i in all_q])
    ax.set_ylabel('Slowdown (10GB / 1GB)')
    ax.set_title('Impact of Data Volume on Execution')
    ax.set_yscale('log')
    ax.grid(True, which='both', axis='y', linestyle=':', linewidth=0.7)
    ax.legend(loc='upper left')

    ax2 = axes[1]
    ax2.bar(geo['case'], geo['geo_mean_slowdown'])
    ax2.set_ylabel('Overall slowdown')
    ax2.set_yscale('log')
    ax2.set_title('Mean Slowdown')
    ax2.grid(True, which='both', axis='y', linestyle=':', linewidth=0.7)

    out = 'slowdown_plot.png'
    fig.savefig(out, dpi=200)
    print(f"Wrote {out}")


if __name__ == '__main__':
    main()
