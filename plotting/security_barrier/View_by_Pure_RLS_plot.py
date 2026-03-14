import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Recently generated data (from the latest extracted CSV)
rows = [
    ['Q1', 1.88, 2283.29, 1.59, 3494.21, 3.99, 3863.43],
    ['Q2', 4.36, 496.99, np.nan, np.nan, np.nan, np.nan],
    ['Q3', 1.41, 11866.41, 3.36, 19314.75, 7.99, 82685.33],
    ['Q4', 0.46, 43617.57, 0.52, 68843.85, 2.49, 43428.38],
    ['Q5', 5.19, 10343.24, np.nan, np.nan, 8.02, 86921.97],
    ['Q6', 0.24, 395.23, 0.53, 621.76, 0.43, 642.23],
    ['Q7', 4.29, 5434.95, 2.69, 17575.21, 9.97, 78279.48],
    ['Q8', 1.88, 2330.35, 3.55, 17822.46, np.nan, np.nan],
    ['Q9', 2.24, 13873.19, 6.97, 67862.38, 7.95, 47080.94],
    ['Q10', 2.04, 101609.02, 1.05, 104725.45, 5.57, 82221.18],
    ['Q11', 1.79, 388.34, 0.86, 603.02, 3.47, 671.00],
    ['Q12', 0.81, 3217.35, 0.75, 3132.51, 2.08, 40649.15],
    ['Q13', 0.45, 163817.04, 0.42, 102273.99, 2.78, 82963.26],
    ['Q14', 0.80, 6048.16, 0.36, 5336.67, 1.06, 4134.63],
    ['Q15', 0.29, 2238.29, 0.24, 986.12, 1.76, 840.40],
    ['Q16', 0.85, 1625.47, 0.73, 3619.43, 2.65, 5219.05],
    ['Q17', 0.91, 621.85, 0.35, 201.77, 1.44, 4200.26],
    ['Q18', 1.78, 9564.61, 0.58, 5060.42, 6.31, 94448.39],
    ['Q19', 0.76, 4612.96, 0.74, 26916.47, 1.80, 1562.82],
    ['Q20', 1.55, 6584.15, 1.64, 39917.00, 3.13, 6010.26],
    ['Q21', 1.19, 3126.88, 2.92, 6553.21, np.nan, np.nan],
    ['Q22', 0.81, 61523.14, 0.83, 90469.68, 7.61, 90095.21],
]

cols = [
    'Query',
    'Indexed_Opt', 'Indexed_Exec',
    'Pure_Opt', 'Pure_Exec',
    'View_Opt', 'View_Exec'
]

df = pd.DataFrame(rows, columns=cols)

# Requested ratios: View / Pure RLS
df['Optimization_Ratio'] = df['View_Opt'] / df['Pure_Opt']
df['Execution_Ratio'] = df['View_Exec'] / df['Pure_Exec']

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
ax.bar(x - width/2, opt_vals, width,
       label='Optimization Ratio (View / Pure RLS)', color='#4C78A8')
ax.bar(x + width/2, exec_vals, width,
       label='Execution Ratio (View / Pure RLS)', color='#F58518')

ax.set_title('Normalized Ratios per Query (View / Pure RLS)', fontsize=TITLE_FS)
ax.set_xlabel('Query ID', fontsize=LABEL_FS)
ax.set_ylabel('Ratio', fontsize=LABEL_FS)
ax.set_xticks(x)
ax.set_xticklabels(df['Query'].tolist(), rotation=45, fontsize=TICK_FS)
ax.tick_params(axis='y', labelsize=TICK_FS)
ax.axhline(1.0, color='black', linestyle='--', linewidth=1, label='Baseline = 1.0')
ax.grid(axis='y', alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc='center left', fontsize=LEGEND_FS)

finite_vals = np.concatenate([
    opt_vals[np.isfinite(opt_vals)],
    exec_vals[np.isfinite(exec_vals)]
])
y_max = finite_vals.max() if finite_vals.size else 1.0
ax.set_ylim(0, y_max * 1.18 if y_max > 0 else 1.0)

# Annotate timeout / undefined ratios
for i, (o, e) in enumerate(zip(opt_vals, exec_vals)):
    if not np.isfinite(o):
        ax.text(x[i] - width/2, y_max - y_max * 0.2, 'TIMEOUT', rotation=90,
                ha='center', va='bottom', fontsize=ANNOT_FS, color='crimson')
    if not np.isfinite(e):
        ax.text(x[i] + width/2, y_max - y_max * 0.2, 'TIMEOUT', rotation=90,
                ha='center', va='bottom', fontsize=ANNOT_FS, color='crimson')

fig.tight_layout()
fig.savefig('view_pure_rls_ratio_plot_large_fonts.png', dpi=220, bbox_inches='tight')
print('Saved view_pure_rls_ratio_plot_large_fonts.png')
