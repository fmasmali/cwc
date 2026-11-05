"""Sensitivity of the compliance results to the behavioral response model
(manuscript Table 9). Sweeps the relative abatement response without
compliance weighting (uniform_incentive, u) and the abatement gain (g).
Weighted runs do not depend on u. Writes results/response_sweep.json."""
import json, pathlib, sys, copy
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from model import CONFIG, compliance_run

SEEDS = 30
root = pathlib.Path(__file__).resolve().parents[1]

def med_iqr(x):
    x = np.asarray(x, dtype=float)
    return dict(median=float(np.median(x)), q1=float(np.percentile(x, 25)), q3=float(np.percentile(x, 75)))

def runs(cfg, weighted):
    return [compliance_run(np.random.default_rng(1000 + s), cfg, weighted=weighted,
                           centralized=False, scenario="stable") for s in range(SEEDS)]

out = {}
for g in (3.0, 6.0, 9.0):
    cfg = copy.deepcopy(CONFIG); cfg["abate_gain"] = g
    w = runs(cfg, True)
    row = dict(weighted=dict(adherence=med_iqr([r["adherence"] for r in w]),
                             recurrence=med_iqr([r["recurrence"] for r in w])))
    for u in (0.2, 0.35, 0.5, 0.65, 0.8, 1.0):
        c = copy.deepcopy(cfg); c["uniform_incentive"] = u
        un = runs(c, False)
        diff = [a["adherence"] - b["adherence"] for a, b in zip(w, un)]
        row[str(u)] = dict(adherence=med_iqr([r["adherence"] for r in un]),
                           recurrence=med_iqr([r["recurrence"] for r in un]),
                           paired_gain=med_iqr(diff))
    out[str(g)] = row
(root / "results" / "response_sweep.json").write_text(json.dumps(out, indent=2))
for g, row in out.items():
    print("g", g, "weighted adh", round(row["weighted"]["adherence"]["median"], 4), "rec", row["weighted"]["recurrence"]["median"])
    for u in ("0.2", "0.35", "0.5", "0.65", "0.8", "1.0"):
        r = row[u]
        print("  u", u, "adh", round(r["adherence"]["median"], 4), "rec", round(r["recurrence"]["median"], 3),
              "gain", round(r["paired_gain"]["median"], 4), [round(r["paired_gain"][k], 4) for k in ("q1", "q3")])
