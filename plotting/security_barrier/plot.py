import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

rows = [
    ['Q1', 1.88, 2283.29, 1.59, 3494.21],
    ['Q2', 4.36, 496.99, np.nan, np.nan],
    ['Q3', 1.41, 11866.41, 3.36, 19314.75],
    ['Q4', 0.46, 43617.57, 0.52, 68843.85],
    ['Q5', 5.19, 10343.24, np.nan, np.nan],
    ['Q6', 0.24, 395.23, 0.53, 621.76],
    ['Q7', 4.29, 5434.95, 2.69, 17575.21],
    ['Q8', 1.88, 2330.35, 3.55, 17822.46],
    ['Q9', 2.24, 13873.19, 6.97, 67862.38],
    ['Q10', 2.04, 101609.02, 1.05, 104725.45],
    ['Q11', 1.79, 388.34, 0.86, 603.02],
    ['Q12', 0.81, 3217.35, 0.75, 3132.51],
    ['Q13', 0.45, 163817.04, 0.42, 102273.99],
    ['Q14', 0.80, 6048.16, 0.36, 5336.67],
    ['Q15', 0.29, 2238.29, 0.24, 986.12],
    ['Q16', 0.85, 1625.47, 0.73, 3619.43],
    ['Q17', 0.91, 621.85, 0.35, 201.77],
    ['Q18', 1.78, 9564.61, 0.58, 5060.42],
    ['Q19', 0.76, 4612.96, 0.74, 26916.47],
    ['Q20', 1.55, 6584.15, 1.64, 39917.00],
    ['Q21', 1.19, 3126.88, 2.92, 6553.21],
    ['Q22', 0.81, 61523.14, 0.83, 90469.68],
]
cols = ['Query', 'Indexed_Opt', 'Indexed_Exec', 'Pure_Opt', 'Pure_Exec']
df = pd.DataFrame(rows, columns=cols)
df['Optimization_Ratio'] = df['Pure_Opt'] / df['Indexed_Opt']
df['Execution_Ratio'] = df['Pure_Exec'] / df['Indexed_Exec']

TITLE_FS = 30
LABEL_FS = 30
TICK_FS = 27
LEGEND_FS = 30
ANNOT_FS = 30

x = np.arange(len(df))
width = 0.38
opt_vals = df['Optimization_Ratio'].to_numpy(dtype=float)
exec_vals = df['Execution_Ratio'].to_numpy(dtype=float)

fig, ax = plt.subplots(figsize=(20, 9))
ax.bar(x - width/2, opt_vals, width, label='Optimization Ratio', color='#4C78A8')
ax.bar(x + width/2, exec_vals, width, label='Execution Ratio', color='#F58518')

ax.set_title('Normalized Ratios per Query (Pure RLS / Indexed RLS)', fontsize=TITLE_FS)
ax.set_xlabel('Query ID', fontsize=LABEL_FS)
ax.set_ylabel('Ratio', fontsize=LABEL_FS)
ax.set_xticks(x)
ax.set_xticklabels(df['Query'].tolist(), rotation=45, fontsize=TICK_FS)
ax.tick_params(axis='y', labelsize=TICK_FS)
ax.axhline(1.0, color='black', linestyle='--', linewidth=1, label='Baseline = 1.0')
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(fontsize=LEGEND_FS)

finite_vals = np.concatenate([opt_vals[np.isfinite(opt_vals)], exec_vals[np.isfinite(exec_vals)]])
y_max = finite_vals.max() if finite_vals.size else 1.0
ax.set_ylim(0, y_max * 1.18 if y_max > 0 else 1.0)

for i, (o, e) in enumerate(zip(opt_vals, exec_vals)):
    if not np.isfinite(o):
        ax.text(x[i] - width/2, y_max - y_max * 0.2, 'TIMEOUT', rotation=90,
                ha='center', va='bottom', fontsize=ANNOT_FS, color='crimson')
    if not np.isfinite(e):
        ax.text(x[i] + width/2, y_max - y_max * 0.2, 'TIMEOUT', rotation=90,
                ha='center', va='bottom', fontsize=ANNOT_FS, color='crimson')

fig.tight_layout()
fig.savefig('combined_normalized_ratio_plot_large_fonts.png', dpi=220, bbox_inches='tight')
print('Saved combined_normalized_ratio_plot_large_fonts.png')
