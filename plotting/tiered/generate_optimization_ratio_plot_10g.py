import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

csv_path = "rls_optimization_ratios.csv"
output_png = "optimization_view_rewrite_over_pure.png"

df = pd.read_csv(csv_path)

metric_cols = [
    "Pure_RLS_Optimization_ms",
    "View_Optimization_ms",
    "Rewrite_Optimization_ms",
    "Optimization_View_over_Pure",
    "Optimization_Rewrite_over_Pure",
]
for col in metric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df['_q'] = df['QID'].str.extract(r'(\d+)').astype(int)
df = df.sort_values('_q').drop(columns=['_q']).reset_index(drop=True)

TITLE_FS = 24
LABEL_FS = 22
TICK_FS = 16
LEGEND_FS = 18
ANNOT_FS = 12

x = np.arange(len(df))
width = 0.38
view_ratio = df['Optimization_View_over_Pure'].to_numpy(dtype=float)
rewrite_ratio = df['Optimization_Rewrite_over_Pure'].to_numpy(dtype=float)


def finite_max(*arrays):
    finite_parts = [arr[np.isfinite(arr)] for arr in arrays if arr.size]
    if not finite_parts:
        return 1.0
    vals = np.concatenate(finite_parts)
    return float(vals.max()) if vals.size else 1.0


def annotate_timeouts(ax, left_vals, right_vals, xvals, bar_width):
    y_top = ax.get_ylim()[1]
    for i, (lv, rv) in enumerate(zip(left_vals, right_vals)):
        if not np.isfinite(lv):
            ax.text(xvals[i] - bar_width/2, y_top * 0.97, 'TIMEOUT', rotation=90,
                    ha='center', va='top', fontsize=ANNOT_FS, color='crimson')
        if not np.isfinite(rv):
            ax.text(xvals[i] + bar_width/2, y_top * 0.97, 'TIMEOUT', rotation=90,
                    ha='center', va='top', fontsize=ANNOT_FS, color='crimson')


fig, ax = plt.subplots(figsize=(20, 8))
ax.bar(x - width/2, view_ratio, width, label='View / Pure RLS', color='#4C78A8')
ax.bar(x + width/2, rewrite_ratio, width, label='Rewrite / Pure RLS', color='#F58518')

ax.set_title('Normalized Optimization Time per Query', fontsize=TITLE_FS)
ax.set_xlabel('Query ID', fontsize=LABEL_FS)
ax.set_ylabel('Ratio', fontsize=LABEL_FS)
ax.set_xticks(x)
ax.set_xticklabels(df['QID'].tolist(), rotation=45, fontsize=TICK_FS)
ax.tick_params(axis='y', labelsize=TICK_FS)
ax.axhline(1.0, color='black', linestyle='--', linewidth=1, label='Parity = 1.0')
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(fontsize=LEGEND_FS)

ymax = finite_max(view_ratio, rewrite_ratio)
ax.set_ylim(0, ymax * 1.18 if ymax > 0 else 1.0)
annotate_timeouts(ax, view_ratio, rewrite_ratio, x, width)

fig.tight_layout()
fig.savefig(output_png, dpi=220, bbox_inches='tight')
print(f'Saved {output_png}')
