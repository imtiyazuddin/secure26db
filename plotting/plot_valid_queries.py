import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

TIMEOUT = 900
CSV_FILE = "atomic_policy_timing.csv"

df = pd.read_csv(CSV_FILE)

phase1 = df["Indexed RLS"].values
phase2 = df["PK-Indexed RLS"].values
phase3 = df["Views"].values
qids   = df["Qid"].values

# ── 1. Drop rows where the baseline itself is a timeout ──────────────────────
valid_mask = phase1 != TIMEOUT
phase1 = phase1[valid_mask]
phase2 = phase2[valid_mask]
phase3 = phase3[valid_mask]
qids   = qids[valid_mask]

# ── 2. Compute ratios ────────────────────────────────────────────────────────
ratio_p2_p1 = phase2 / phase1
ratio_p3_p1 = phase3 / phase1

# ── 3. Y-axis cap: 10× the largest *finite* (non-timeout) ratio ─────────────
finite_ratios = np.concatenate([
    ratio_p2_p1[phase2 != TIMEOUT],
    ratio_p3_p1[phase3 != TIMEOUT],
])
max_finite_ratio = finite_ratios.max() if len(finite_ratios) > 0 else 1.0
Y_MAX = 6          # hard cap
EXPENSIVE_HEIGHT = Y_MAX        # "expensive" bars sit just below the cap

# ── 4. Classify bars ─────────────────────────────────────────────────────────
def classify(ratios, numerators):
    heights, colors, hatches = [], [], []
    for r, n in zip(ratios, numerators):
        if n == TIMEOUT:
            heights.append(EXPENSIVE_HEIGHT)
            colors.append("#e74c3c")
            hatches.append("///")
        else:
            heights.append(r)
            colors.append(None)
            hatches.append("")
    return heights, colors, hatches

h2, c2, hh2 = classify(ratio_p2_p1, phase2)
h3, c3, hh3 = classify(ratio_p3_p1, phase3)

# ── 5. Plot ──────────────────────────────────────────────────────────────────
x      = np.arange(len(qids))
width  = 0.35
cmap   = plt.cm.get_cmap("tab10")
col_p2 = cmap(0)
col_p3 = cmap(1)
col_ex = "#e74c3c"

fig, ax = plt.subplots(figsize=(16, 6))

for i, (h, c, hatch) in enumerate(zip(h2, c2, hh2)):
    fc = col_ex if c == "#e74c3c" else col_p2
    ax.bar(x[i] - width/2, h, width, color=fc, hatch=hatch,
           edgecolor="black", linewidth=0.7, zorder=3)

for i, (h, c, hatch) in enumerate(zip(h3, c3, hh3)):
    fc = col_ex if c == "#e74c3c" else col_p3
    ax.bar(x[i] + width/2, h, width, color=fc, hatch=hatch,
           edgecolor="black", linewidth=0.7, zorder=3)

# Annotate "expensive" bars
label_y = Y_MAX * 0.97
for i, c in enumerate(c2):
    if c == "#e74c3c":
        ax.text(x[i] - width/2, label_y, "expensive", ha="center",
                va="top", fontsize=6.5, color="white", rotation=90,
                fontweight="bold")

for i, c in enumerate(c3):
    if c == "#e74c3c":
        ax.text(x[i] + width/2, label_y, "expensive", ha="center",
                va="top", fontsize=6.5, color="white", rotation=90,
                fontweight="bold")

# Reference line at ratio = 1
ax.axhline(1.0, color="gray", linestyle="--", linewidth=1.0, zorder=2)

ax.set_xticks(x)
ax.set_xticklabels(qids, rotation=45, ha="right", fontsize=9)
ax.set_xlabel("Query ID", fontsize=11)
ax.set_ylabel("Ratio to Baseline", fontsize=11)

# Legend
p2_patch = mpatches.Patch(color=col_p2, label="PK-Indexed RLS / Indexed RLS")
p3_patch = mpatches.Patch(color=col_p3, label="Views / Indexed RLS")
ex_patch = mpatches.Patch(facecolor=col_ex, hatch="///", edgecolor="black",
                           label="Numerator = TIMEOUT (900 s) — 'expensive'")
ref_line = plt.Line2D([0], [0], color="gray", linestyle="--",
                      label="Ratio = 1 (equal to baseline)")
ax.legend(handles=[p2_patch, p3_patch, ex_patch, ref_line],
          fontsize=8, loc="upper left")

ax.set_ylim(0, Y_MAX)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.1f}×"))
ax.grid(axis="y", linestyle=":", alpha=0.5, zorder=0)
ax.set_facecolor("#f9f9f9")

plt.tight_layout()
plt.savefig("query_ratios_valid.png", dpi=150, bbox_inches="tight")
print(f"Saved: query_ratios_valid.png  |  Y-axis cap: {Y_MAX:.2f}×  |  Queries plotted: {len(qids)}")
plt.show()
