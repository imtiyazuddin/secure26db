import matplotlib.pyplot as plt
import numpy as np

# -----------------------------
# Data extracted from the images
# -----------------------------
# Plot 1: Query + VPD policy Execution time (ratio vs baseline)
query_ids_vpd = ['Q2', 'Q3', 'Q5', 'Q7', 'Q8', 'Q21']
ratio_values = [2.46, 1.00, 0.72, 0.74, 1.14, 5.67]
baseline = 1.0

# Plot 2: Execution time by query for different predicate orderings
query_ids_or = ['Q5', 'Q14', 'Q21']
p16 = [7.86, 15.17, 74.06]
p16_or_p2 = [15.09, 7.08, 59.41]
p2_or_p16 = [15.07, 7.03, 67.56]

# Optional: style similar to the original plots
plt.style.use('ggplot')

# -----------------------------
# Plot 1 (square aspect ratio)
# -----------------------------
fig1, ax1 = plt.subplots(figsize=(6, 6))
bar_color = '#5aa64f'  # close to the original green
bars1 = ax1.bar(query_ids_vpd, ratio_values, color=bar_color, width=0.38,
                label='Without indexing / Indexed')
ax1.axhline(baseline, color='black', linestyle=(0, (2, 2)), linewidth=1,
            label='Baseline')

ax1.set_title('Query + RLS policy Execution time', fontsize=18)
ax1.set_xlabel('Query ID', fontsize=18)
ax1.set_ylabel('Ratio', fontsize=18)
ax1.tick_params(axis='x', rotation=45, labelsize=16)
ax1.tick_params(axis='y', labelsize=16)
ax1.set_ylim(0, 6.5)
ax1.grid(True, axis='both', alpha=0.25)

# Put legend in the same order as the source image
handles, labels = ax1.get_legend_handles_labels()
order = [1, 0]  # Baseline first, then bars
ax1.legend([handles[i] for i in order], [labels[i] for i in order],
           loc='upper center', framealpha=0.9, fontsize=16, borderpad=0.8)

for bar, val in zip(bars1, ratio_values):
    ax1.text(bar.get_x() + bar.get_width()/2, val + 0.05, "",
             ha='center', va='bottom', fontsize=11)

fig1.tight_layout()
fig1.savefig('vpd.png', dpi=300, bbox_inches='tight')

# -----------------------------
# Plot 2 (square aspect ratio)
# -----------------------------
fig2, ax2 = plt.subplots(figsize=(6, 6))
x = np.arange(len(query_ids_or))
width = 0.24

bars_p16 = ax2.bar(x - width, p16, width, label='P16', color='#4C72B0')
bars_p16_or_p2 = ax2.bar(x, p16_or_p2, width, label='P16 OR P2', color='#C44E52')
bars_p2_or_p16 = ax2.bar(x + width, p2_or_p16, width, label='P2 OR P16', color='#55A868')

ax2.set_xlabel('Query ID', fontsize=18)
ax2.set_ylabel('Time (s)', fontsize=18)
ax2.set_xticks(x)
ax2.set_xticklabels(query_ids_or, rotation=45, fontsize=16)
ax2.tick_params(axis='y', labelsize=16)
ax2.set_ylim(0, 80)
ax2.legend(loc='upper left', framealpha=0.9, fontsize=16, borderpad=0.8)
ax2.grid(True, axis='both', alpha=0.25)

for container in [bars_p16, bars_p16_or_p2, bars_p2_or_p16]:
    for bar in container:
        h = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2, h + 0.5,"",
                 ha='center', va='bottom', fontsize=11)

fig2.tight_layout()
fig2.savefig('vpd_or.png', dpi=300, bbox_inches='tight')

plt.show()
