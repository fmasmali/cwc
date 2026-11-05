"""Generate manuscript Figures 2-4 from the simulation model (30 seeds)."""
import pathlib, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from model import CONFIG as cfg, latency_hybrid, latency_pow, latency_poa, auction_run

root = pathlib.Path(__file__).resolve().parents[1]
SEEDS = 30

# ---------------- Figure 2: latency vs offered load ----------------
loads = [25, 50, 100, 150, 200, 300, 450, 600, 900, 1200]
curves = {"Proposed hybrid (200 nodes)": [], "PoA-IoT baseline": [], "Monolithic PoW": []}
for L in loads:
    h, a, p = [], [], []
    for s in range(SEEDS):
        rng = np.random.default_rng(5000 + s)
        h.append(np.median(latency_hybrid(rng, cfg, L, 200, duration_s=40)))
        a.append(np.median(latency_poa(rng, cfg, L, duration_s=40)))
        p.append(np.median(latency_pow(rng, cfg, L, duration_s=40)))
    curves["Proposed hybrid (200 nodes)"].append(np.median(h))
    curves["PoA-IoT baseline"].append(np.median(a))
    curves["Monolithic PoW"].append(np.median(p))

fig, ax = plt.subplots(figsize=(6.6, 3.8), dpi=200)
styles = {"Proposed hybrid (200 nodes)": ("-", "o", "#1f77b4"),
          "PoA-IoT baseline": ("--", "s", "#2ca02c"),
          "Monolithic PoW": (":", "^", "#d62728")}
for name, ys in curves.items():
    ls, mk, cl = styles[name]
    ax.plot(loads, np.clip(ys, None, 14), ls, marker=mk, ms=4, color=cl, label=name)
ax.set_xlabel("Offered load (transactions per second)")
ax.set_ylabel("Median confirmation latency (s)")
ax.set_ylim(0, 14)
ax.axvline(333, color="#2ca02c", lw=0.7, alpha=0.5)
ax.axvline(1000 / cfg["pow_exec_ms"], color="#d62728", lw=0.7, alpha=0.5)
ax.annotate("PoA saturation", xy=(333, 10.5), fontsize=7, color="#2ca02c", rotation=90, va="top")
ax.annotate("PoW saturation", xy=(1000 / cfg["pow_exec_ms"], 10.5), fontsize=7,
            color="#d62728", rotation=90, va="top")
ax.legend(fontsize=8, loc="upper left")
ax.grid(alpha=0.25, lw=0.4)
fig.tight_layout()
fig.savefig(root / "figures" / "fig2_latency.png")

# ---------------- Figure 3: Dutch auction clearing ----------------
fig, ax = plt.subplots(figsize=(5.4, 3.4), dpi=200)
t = np.linspace(0, (cfg["p_max"] - cfg["p_floor"]) / cfg["delta"], 200)
ax.plot(t, np.maximum(cfg["p_max"] - cfg["delta"] * t, cfg["p_floor"]),
        "k-", lw=1.4, label="Price trajectory  P(t) = P$_{max}$ \u2212 \u03b4t")
pts = {"stable": [], "stress": []}
for scen, color in (("stable", "#1f77b4"), ("stress", "#d62728")):
    for s in range(SEEDS):
        rng = np.random.default_rng(7000 + s)
        # capture individual clearings
        rate = cfg["bidder_rate_stress"] if scen == "stress" else cfg["bidder_rate_stable"]
        horizon = (cfg["p_max"] - cfg["p_floor"]) / cfg["delta"]
        for _ in range(4):
            n_bid = rng.poisson(rate * horizon)
            t_arr = np.sort(rng.uniform(0, horizon, n_bid))
            vals = rng.uniform(cfg["valuation_low"], cfg["valuation_high"], n_bid)
            for tt, v in zip(t_arr, vals):
                if v >= cfg["p_max"] - cfg["delta"] * tt:
                    pts[scen].append((tt, cfg["p_max"] - cfg["delta"] * tt))
                    break
for scen, color, mk in (("stable", "#1f77b4", "o"), ("stress", "#d62728", "^")):
    arr = np.array(pts[scen])
    ax.scatter(arr[:, 0], arr[:, 1], s=10, alpha=0.35, color=color, marker=mk,
               label=f"Clearing points ({scen} demand)")
ax.axhline(cfg["p_floor"], color="gray", lw=0.8, ls="--")
ax.annotate("reserve floor", xy=(1, cfg["p_floor"] + 0.015), fontsize=7, color="gray")
ax.set_xlabel("Time since auction opening (s)")
ax.set_ylabel("Price (normalized)")
ax.legend(fontsize=7.5)
ax.grid(alpha=0.25, lw=0.4)
fig.tight_layout()
fig.savefig(root / "figures" / "fig3_auction.png")

# ---------------- Figure 4: compliance score vs proposal probability ----------------
fig, ax = plt.subplots(figsize=(5.4, 3.4), dpi=200)
S = np.linspace(0.01, 1.0, 200)
m = cfg["orgs"]
P = S / (S + (m - 1))
ax.plot(S, P, "-", color="#1f77b4", lw=1.6,
        label="P$_{prop}$ = \u03c4S / \u03a3\u03c4S  (Eq. 6, equal stakes, m = 10)")
ax.axhline(1 / m, color="gray", lw=0.8, ls="--")
ax.annotate("uniform share 1/m", xy=(0.03, 1 / m + 0.003), fontsize=7, color="gray")
# violation trajectory: median realized excess from the compliance runs
R = json.load(open(root / "results" / "summary.json"))
lam = cfg["lam"]
med_excess = 14.0  # illustrative per-violation excess (kg); stated in the figure caption
S_traj = [1.0]
for _ in range(3):
    S_traj.append(S_traj[-1] * np.exp(-lam * med_excess))
P_traj = [s / (s + (m - 1)) for s in S_traj]
ax.plot(S_traj, P_traj, "o--", color="#d62728", ms=5, lw=1,
        label="Trajectory: three successive violations (Eq. 7)")
for i, (s, p) in enumerate(zip(S_traj, P_traj)):
    dx = -0.075 if i == 0 else 0.02
    ax.annotate(f"k={i}", xy=(s, p), xytext=(s + dx, p + 0.004), fontsize=7)
ax.set_xlabel("Compliance score S")
ax.set_ylabel("Block-proposal probability")
ax.set_ylim(0, 0.112)
ax.legend(fontsize=7.5, loc="lower right")
ax.grid(alpha=0.25, lw=0.4)
fig.tight_layout()
fig.savefig(root / "figures" / "fig4_score.png")

print("figures written:", sorted(p.name for p in (root / "figures").glob("*.png")))
print("fig2 medians:", {k: [round(v, 2) for v in vv] for k, vv in curves.items()})
