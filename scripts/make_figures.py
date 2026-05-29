#!/usr/bin/env python3
"""Render the paper's data figures from the collected telemetry.

Springer proceedings print in black and white, so series are distinguished by
greyscale fill, hatching, and line/marker style rather than colour alone. Reads
``data/telemetry.json`` and ``data/camp_spike.json``; writes PDF and PNG into
``figures/``.
"""

from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA = "data"
OUT = "figures"

DARK = "#4d4d4d"
LIGHT = "#b3b3b3"

plt.rcParams.update({
    "font.size": 9,
    "font.family": "serif",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.dpi": 200,
})


def load(name: str) -> dict:
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)


def traffic_latency(tel: dict) -> None:
    order = ["backend", "frontend", "website", "keycloak", "admin", "evaluator"]
    labels = ["Backend", "Frontend", "Website", "Keycloak", "Admin", "Evaluator"]
    reqs = [tel["http_traffic"][s]["requests_total"] for s in order]
    p95 = [tel["http_traffic"][s]["latency_seconds"]["p95"] * 1000 for s in order]

    fig, ax1 = plt.subplots(figsize=(6.2, 3.0))
    x = np.arange(len(order))
    ax1.bar(x - 0.2, reqs, width=0.4, color=DARK, edgecolor="black",
            label="Requests (15 d)")
    ax1.set_yscale("log")
    ax1.set_ylabel("HTTP requests (15 d, log scale)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=15, ha="right")

    ax2 = ax1.twinx()
    ax2.bar(x + 0.2, p95, width=0.4, facecolor="white", edgecolor="black",
            hatch="////", label="p95 latency (ms)")
    ax2.set_ylabel("p95 latency (ms)")
    ax2.grid(False)

    handles = ax1.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels_ = ax1.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax1.legend(handles, labels_, fontsize=7, loc="upper right")
    ax1.set_title("Per-service request volume and tail latency (steady state)")
    _save(fig, "fig-traffic-latency")


def memory(tel: dict) -> None:
    apps = ["ro-oai-backend", "ro-oai-frontend", "ro-oai-website",
            "ro-oai-evaluator", "rabbitmq", "ro-oai-admin"]
    labels = ["Backend", "Frontend", "Website", "Evaluator", "RabbitMQ", "Admin"]
    avg = [tel["resources"][a]["mem_avg_mb"] for a in apps]
    peak = [tel["resources"][a]["mem_peak_mb"] for a in apps]

    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    x = np.arange(len(apps))
    ax.bar(x - 0.2, avg, width=0.4, color=DARK, edgecolor="black", label="Mean")
    ax.bar(x + 0.2, peak, width=0.4, facecolor="white", edgecolor="black",
           hatch="\\\\", label="Peak")
    ax.set_ylabel("Working-set memory (MB)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_title("Mean vs. peak memory per service tier")
    ax.legend(fontsize=8)
    _save(fig, "fig-memory")


def spike() -> None:
    path = os.path.join(DATA, "camp_spike.json")
    if not os.path.exists(path):
        return
    camp = load("camp_spike.json")
    days = sorted(camp["by_day"])
    peak = [camp["by_day"][d]["peak_req_s"] for d in days]
    mean = [camp["by_day"][d]["mean_req_s"] for d in days]

    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    x = np.arange(len(days))
    ax.plot(x, peak, "-o", color="black", label="Hourly peak", markersize=3.5)
    ax.plot(x, mean, "--s", color=DARK, label="Daily mean", markersize=3.5)
    camp_idx = [i for i, d in enumerate(days) if "05-21" <= d <= "05-25"]
    if camp_idx:
        ax.axvspan(min(camp_idx) - 0.5, max(camp_idx) + 0.5, color=LIGHT,
                   alpha=0.4, label="Team camp (21-25 May)")
    ax.set_ylabel("Backend request rate (req/s)")
    ax.set_xlabel("Day (2026)")
    ax.set_xticks(x)
    ax.set_xticklabels([d[5:] for d in days], rotation=45, ha="right", fontsize=7)
    ax.set_title("Contest-load spike during the National Team Selection Camp")
    ax.legend(fontsize=7)
    _save(fig, "fig-spike")


def _save(fig, name: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, f"{name}.pdf"))
    fig.savefig(os.path.join(OUT, f"{name}.png"))
    plt.close(fig)
    print(f"wrote {OUT}/{name}.pdf")


def main() -> None:
    tel = load("telemetry.json")
    traffic_latency(tel)
    memory(tel)
    spike()


if __name__ == "__main__":
    main()
