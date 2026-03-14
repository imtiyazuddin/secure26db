import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Input CSV created from the log analysis
csv_path = 'rls_log_analysis.csv'
output_png = 'normalized_rls_two_panel.png'

df = pd.read_csv(csv_path)

# Convert timeout/missing cells to NaN if needed
metric_cols = [
    'Pure_RLS_Optimization_ms', 'Pure_RLS_Execution_ms',
    'View_Optimization_ms', 'View_Execution_ms',
    'Rewrite_Optimization_ms', 'Rewrite_Execution_ms'
]
for col in metric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Keep queries in numeric order (Q1..Q22)
df['_q'] = df['QID'].str.extract(r'(\d+)').astype(int)
df = df.sort_values('_q').drop(columns=['_q']).reset_index(drop=True)

# Required normalized ratios
df['Execution_View_over_Pure'] = df['View_Execution_ms'] / df['Pure_RLS_Execution_ms']
df['Execution_Rewrite_over_Pure'] = df['Rewrite_Execution_ms'] / df['Pure_RLS_Execution_ms']
df['Optimization_View_over_Pure'] = df['View_Optimization_ms'] / df['Pure_RLS_Optimization_ms']
df['Optimization_Rewrite_over_Pure'] = df['Rewrite_Optimization_ms'] / df['Pure_RLS_Optimization_ms']

TITLE_FS = 30
LABEL_FS = 30
TICK_FS = 27
LEGEND_FS = 30
ANNOT_FS = 30

x = np.arange(len(df))
width = 0.38

exec_view = df['Execution_View_over_Pure'].to_numpy(dtype=float)
exec_rewrite = df['Execution_Rewrite_over_Pure'].to_numpy(dtype=float)
opt_view = df['Optimization_View_over_Pure'].to_numpy(dtype=float)
opt_rewrite = df['Optimization_Rewrite_over_Pure'].to_numpy(dtype=float)


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

fig, axes = plt.subplots(2, 1, figsize=(20, 16), sharex=True)

# Top subplot: normalized execution time
ax = axes[0]
ax.bar(x - width/2, exec_view, width, label='View / Pure RLS', color='#4C78A8')
ax.bar(x + width/2, exec_rewrite, width, label='Rewrite / Pure RLS', color='#F58518')
ax.set_title('Normalized Execution Time per Query', fontsize=TITLE_FS)
ax.set_ylabel('Ratio', fontsize=LABEL_FS)
ax.tick_params(axis='y', labelsize=TICK_FS)
ax.axhline(1.0, color='black', linestyle='--', linewidth=1, label='Baseline = 1.0')
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc='upper center',fontsize=LEGEND_FS)
exec_ymax = finite_max(exec_view, exec_rewrite)
ax.set_ylim(0, exec_ymax * 1.15 if exec_ymax > 0 else 1.0)
annotate_timeouts(ax, exec_view, exec_rewrite, x, width)

# Bottom subplot: normalized optimization time
ax = axes[1]
ax.bar(x - width/2, opt_view, width, label='View / Pure RLS', color='#4C78A8')
ax.bar(x + width/2, opt_rewrite, width, label='Rewrite / Pure RLS', color='#F58518')
ax.set_title('Normalized Optimization Time per Query', fontsize=TITLE_FS)
ax.set_xlabel('Query ID', fontsize=LABEL_FS)
ax.set_ylabel('Ratio', fontsize=LABEL_FS)
ax.set_xticks(x)
ax.set_xticklabels(df['QID'].tolist(), rotation=45, fontsize=TICK_FS)
ax.tick_params(axis='y', labelsize=TICK_FS)
ax.axhline(1.0, color='black', linestyle='--', linewidth=1, label='Baseline = 1.0')
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc='upper center',fontsize=LEGEND_FS)
opt_ymax = finite_max(opt_view, opt_rewrite)
ax.set_ylim(0, opt_ymax * 1.18 if opt_ymax > 0 else 1.0)
annotate_timeouts(ax, opt_view, opt_rewrite, x, width)

fig.tight_layout(h_pad=2.0)
fig.savefig(output_png, dpi=220, bbox_inches='tight')
print(f'Saved {output_png}')
