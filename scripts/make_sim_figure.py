#!/usr/bin/env python3
"""Figure: simulated evaluation queue wait vs arrival rate, per worker count.
Greyscale-safe (distinct markers + line styles). Reads data/sim_load.json."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "data", "sim_load.json")) as f:
    SIM = json.load(f)

plt.rcParams.update({"font.size": 9, "font.family": "serif",
                     "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 200})

styles = {2: ("-o", "black"), 4: ("--s", "#4d4d4d"), 10: ("-.^", "#808080")}

fig, ax = plt.subplots(figsize=(6.2, 3.1))
by_c = {}
for r in SIM["results"]:
    by_c.setdefault(r["workers"], []).append((r["lambda_per_s"], r["wait_p95_s"]))
for c in sorted(by_c):
    pts = sorted(by_c[c])
    xs = [p[0] for p in pts]
    ys = [max(p[1], 0.01) for p in pts]  # floor for log axis
    fmt, col = styles.get(c, ("-o", "black"))
    ax.plot(xs, ys, fmt, color=col, label=f"{c} evaluator workers", markersize=4)

# reference lines: real observed peak and a 1 s SLA
ax.axvline(0.7, color="black", linewidth=0.8, linestyle=":")
ax.text(0.74, 0.02, "observed peak\n(~0.7 sub/s)", fontsize=6.5, va="bottom")
ax.axhline(1.0, color="black", linewidth=0.6, linestyle=":")
ax.text(0.5, 1.15, "1 s wait SLA", fontsize=6.5)

ax.set_yscale("log")
ax.set_xlabel("Submission arrival rate (submissions/s)")
ax.set_ylabel("p95 queue wait (s, log scale)")
ax.set_title("Simulated evaluation-queue wait vs. load and worker count")
ax.legend(fontsize=7, loc="upper left")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig-sim-load.pdf"))
fig.savefig(os.path.join(HERE, "fig-sim-load.png"))
print("wrote fig-sim-load.pdf")
