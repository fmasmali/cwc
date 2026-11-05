"""Figure 5 of the manuscript: (a) ranking fidelity across the consumer
preference weight w; (b) lambda sensitivity - violation recurrence versus
concentration (Gini) of block proposals. Reads results/summary.json only."""
import json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = pathlib.Path(__file__).resolve().parents[1]
R = json.load(open(root / "results" / "summary.json"))

fig, (a, b) = plt.subplots(1, 2, figsize=(8.2, 3.2), dpi=200)
ws = sorted(R["fidelity_curve"], key=float)
x = [float(w) for w in ws]
med = [100 * R["fidelity_curve"][w]["median"] for w in ws]
lo = [100 * R["fidelity_curve"][w]["q1"] for w in ws]
hi = [100 * R["fidelity_curve"][w]["q3"] for w in ws]
a.fill_between(x, lo, hi, color="#1f77b4", alpha=0.18, lw=0, label="IQR (30 seeds)")
a.plot(x, med, "o-", color="#1f77b4", ms=4, lw=1.4, label="Median")
a.set_xlabel("Freshness weight w  (Eq. 10)")
a.set_ylabel("Ranking fidelity (%)")
a.set_ylim(88, 100)
a.set_title("(a) Displayed vs. true ranking", fontsize=9)
a.legend(fontsize=7.5, loc="lower left")
a.grid(alpha=0.25, lw=0.4)

lams = sorted(R["lambda_sweep"], key=float)
lx = [float(l) for l in lams]
rec = [100 * R["lambda_sweep"][l]["recurrence"]["median"] for l in lams]
gini = [R["lambda_sweep"][l]["gini"]["median"] for l in lams]
b.plot(lx, rec, "o-", color="#d62728", ms=4, lw=1.4, label="Violation recurrence (%)")
b.set_xlabel("Score-decay rate \u03bb  (Eq. 7)")
b.set_ylabel("Recurrence within 5 epochs (%)", color="#d62728")
b.set_ylim(0, 40)
b2 = b.twinx()
b2.plot(lx, gini, "s--", color="#2ca02c", ms=4, lw=1.4, label="Gini of proposals")
b2.set_ylabel("Gini of block proposals", color="#2ca02c")
b2.set_ylim(0, 0.45)
b.set_title("(b) Deterrence vs. concentration", fontsize=9)
h1, l1 = b.get_legend_handles_labels(); h2, l2 = b2.get_legend_handles_labels()
b.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="upper center")
b.grid(alpha=0.25, lw=0.4)
fig.tight_layout()
fig.savefig(root / "figures" / "fig5_fidelity_lambda.png")
print("written fig5_fidelity_lambda.png")
