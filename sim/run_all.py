"""Execute every experiment in the manuscript: main grid, scenarios,
sensitivity sweeps, and ablations, at SEEDS independent seeds each.
Writes results/summary.json with medians and IQRs."""
import json, pathlib, sys
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from model import (CONFIG, latency_hybrid, latency_pow, latency_poa, latency_central,
                   peak_tps, sync_accuracy, compliance_run, auction_run,
                   ranking_fidelity, injection_defense, election_stability)

SEEDS = 30
root = pathlib.Path(__file__).resolve().parents[1]


def med_iqr(x):
    x = np.asarray([v for v in x if v == v], dtype=float)
    return dict(median=float(np.median(x)),
                q1=float(np.percentile(x, 25)), q3=float(np.percentile(x, 75)))


def seeds(fn):
    return [fn(np.random.default_rng(1000 + s)) for s in range(SEEDS)]


R = {}
cfg = CONFIG

# ---- 1. latency at matched load (200 nodes, 200 TPS offered) ----
LOAD = 100.0
R["latency_hybrid_s"] = med_iqr(seeds(lambda r: np.median(latency_hybrid(r, cfg, LOAD, 200))))
R["latency_pow_s"] = med_iqr(seeds(lambda r: np.median(latency_pow(r, cfg, LOAD))))
R["latency_poa_s"] = med_iqr(seeds(lambda r: np.median(latency_poa(r, cfg, LOAD))))
R["latency_central_s"] = med_iqr(seeds(lambda r: np.median(latency_central(r, cfg, LOAD, 200))))
R["latency_ratio_pow_over_hybrid"] = med_iqr(
    [a / b for a, b in zip(
        seeds(lambda r: np.median(latency_pow(r, cfg, LOAD))),
        seeds(lambda r: np.median(latency_hybrid(r, cfg, LOAD, 200))))])

# ---- 2. peak throughput across scales ----
for n in (50, 100, 200):
    R[f"tps_hybrid_{n}"] = med_iqr(seeds(lambda r, n=n: peak_tps(r, cfg, "hybrid", n)))
    R[f"tps_central_{n}"] = med_iqr(seeds(lambda r, n=n: peak_tps(r, cfg, "central", n)))
R["tps_poa"] = med_iqr(seeds(lambda r: peak_tps(r, cfg, "poa", 200)))

# ---- 3. synchronization accuracy ----
R["sync_stable"] = med_iqr(seeds(lambda r: sync_accuracy(r, cfg, "stable")))
R["sync_stress"] = med_iqr(seeds(lambda r: sync_accuracy(r, cfg, "stress")))

# ---- 4. compliance: artifact vs centralized, stable & stress ----
for scen in ("stable", "stress"):
    art = seeds(lambda r, s=scen: compliance_run(r, cfg, weighted=True, centralized=False, scenario=s))
    cen = seeds(lambda r, s=scen: compliance_run(r, cfg, weighted=False, centralized=True, scenario=s))
    R[f"adherence_artifact_{scen}"] = med_iqr([a["adherence"] for a in art])
    R[f"adherence_central_{scen}"] = med_iqr([a["adherence"] for a in cen])
    R[f"penalty_accuracy_{scen}"] = med_iqr([a["penalty_accuracy"] for a in art])
    if scen == "stable":
        R["contraction_after3"] = med_iqr([a["contraction_after3"] for a in art
                                           if a["contraction_after3"] is not None])

# ---- 5. auctions ----
for scen in ("stable", "stress"):
    a = seeds(lambda r, s=scen: auction_run(r, cfg, scenario=s))
    R[f"auction_completion_{scen}"] = med_iqr([x["completion_s"] for x in a])
    R[f"auction_pricedev_{scen}"] = med_iqr([x["price_dev"] for x in a])

# ---- 6. ranking fidelity ----
for w in (0.2, 0.5, 0.8):
    R[f"fidelity_w{w}"] = med_iqr(seeds(lambda r, w=w: ranking_fidelity(r, cfg, w)))
w_grid = np.round(np.arange(0.1, 0.91, 0.1), 2)
R["fidelity_curve"] = {str(w): med_iqr(seeds(lambda r, w=w: ranking_fidelity(r, cfg, w)))
                       for w in w_grid}

# ---- 7. attack scenario ----
R["injection_with_sig"] = med_iqr(seeds(lambda r: injection_defense(r, cfg, True)["rejection_rate"]))
R["injection_hash_only"] = med_iqr(seeds(lambda r: injection_defense(r, cfg, False)["rejection_rate"]))

# ---- 8. sensitivity: lambda ----
R["lambda_sweep"] = {}
for lam in (0.01, 0.05, 0.10, 0.20):
    c2 = dict(cfg, lam=lam)
    runs = seeds(lambda r, c=c2: compliance_run(r, c, weighted=True))
    R["lambda_sweep"][str(lam)] = dict(
        recurrence=med_iqr([x["recurrence"] for x in runs]),
        gini=med_iqr([x["gini"] for x in runs]))

# ---- 9. sensitivity: theta ----
R["theta_sweep"] = {}
for th in (0.4, 0.6, 0.8):
    runs = seeds(lambda r, t=th: election_stability(r, cfg, t))
    R["theta_sweep"][str(th)] = dict(
        reelections=med_iqr([x["reelections"] for x in runs]),
        bad_leader_share=med_iqr([x["bad_leader_share"] for x in runs]))

# ---- 10. ablations ----
# A1 full artifact (reference values already computed above)
# A2 uniform proposer selection
a2 = seeds(lambda r: compliance_run(r, cfg, weighted=False))
R["A2_adherence"] = med_iqr([x["adherence"] for x in a2])
R["A2_recurrence"] = med_iqr([x["recurrence"] for x in a2])
# A3 no clustering: per-tuple anchoring -> PoA-style path at 200 nodes
R["A3_latency_s"] = med_iqr(seeds(lambda r: np.median(latency_poa(r, cfg, LOAD))))
R["A3_tps"] = R["tps_poa"]
# A4 hash-only submissions
R["A4_injection_rejection"] = R["injection_hash_only"]

(root / "results" / "summary.json").write_text(json.dumps(R, indent=1))
print(json.dumps({k: v for k, v in R.items() if not isinstance(v, dict) or "median" in v},
                 indent=1)[:3000])
print("... written results/summary.json")
