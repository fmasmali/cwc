"""Figure 1 of the manuscript: layered architecture of the artifact."""
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

root = pathlib.Path(__file__).resolve().parents[1]
fig, ax = plt.subplots(figsize=(11, 8.2), dpi=200)
ax.set_xlim(0, 110); ax.set_ylim(0, 82); ax.axis("off")

C = dict(phys="#e8f1fb", iot="#e7f5ea", ent="#f3e9f7", app="#fff4e0", edge="#555555")

def band(y, h, color, title, dp):
    ax.add_patch(FancyBboxPatch((1, y), 92, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc=color, ec="#999999", lw=0.8))
    ax.text(2.5, y + h - 1.6, title, fontsize=9.5, weight="bold", va="top")
    ax.add_patch(FancyBboxPatch((95, y), 14, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc="white", ec="#999999", lw=0.8))
    ax.text(102, y + h / 2, dp, fontsize=7.6, ha="center", va="center", linespacing=1.4)

def box(x, y, w, h, text, fc="white", fs=7.6, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8",
                                fc=fc, ec=C["edge"], lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, fontsize=fs, ha="center", va="center",
            weight="bold" if bold else "normal", linespacing=1.3)

def arrow(p, q, text=None, off=(0, 0), color="#333333", style="-|>", ls="-", rad=0.0, fs=7):
    a = FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=10, lw=1.1, color=color,
                        linestyle=ls, connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)
    if text:
        ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], text, fontsize=fs,
                ha="center", va="center", color=color,
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))

# layers (bottom -> top)
band(2, 15, C["phys"], "Physical layer: attested sensing", "DP1\nProximal\nvalidation")
band(20, 19, C["iot"], "IoT tier: crash-fault-tolerant coordination (Raft)", "DP1, DP2\nLayered trust\nseparation")
band(42, 22, C["ent"], "Enterprise tier: QBFT finality (m = 10)", "DP2, DP3\nCompliance-\nweighted\nauthority")
band(67, 13, C["app"], "Application layer", "DP4\nPreference-\nparameterized\ntransparency")

# physical
for i, x in enumerate((5, 26, 47, 68)):
    box(x, 4, 18, 8.5, "IoT device\nT, H, activity data\nsign (Eq. 3) in HW\n" + ("cluster 1" if i < 2 else "cluster k"), fc="white")
# iot tier
box(5, 22, 39, 12.5, "Cluster 1 (8 devices)\nleader elected by U·A (Eqs. 4–5)\nverify signatures · plausibility check\naggregate every 500 ms → digest", fc="white")
box(50, 22, 39, 12.5, "Cluster k\nleader + Raft log replication\n(tolerates crash faults,\nsub-second local validation)", fc="white")
# enterprise tier
box(4, 45, 26, 13, "Proposer selection\nP = τ·S / Στ·S  (Eq. 6)\nVRF sortition over\nprevious block hash", fc="white")
box(33, 45, 28, 13, "EmissionTracker contract\nrecordAnchor → settleBatch\n(finality + digest checks)\npenalty (Eq. 8) · S decay (Eq. 7)", fc="white")
box(64, 45, 25, 13, "CreditAuction contract\nDutch auction (Eq. 9)\nescrowed settlement", fc="white")
box(64, 59.2, 25, 3.6, "ERP oracle quorum (custody, orders)", fc="#f7f7f7", fs=7)
# app
box(5, 69, 40, 8, "Consumer dApp: ranking by w·Q + (1−w)·(C−E)/C\n(Eq. 10) over attested, anchored evidence", fc="white")
box(50, 69, 39, 8, "Regulator / auditor view: settlements, penalties,\nscores, bounded ledger–sensor divergence", fc="white")

# flows
for x in (14, 35):
    arrow((x, 12.8), (x if x < 30 else 30, 21.8), None)
for x in (56, 77):
    arrow((x, 12.8), (x if x > 60 else 62, 21.8), None)
ax.text(46, 17.6, "signed tuples (vᵢ, σᵢ)", fontsize=7, ha="center", color="#333333",
        bbox=dict(fc=C["phys"], ec="none", pad=0.5))
arrow((24.5, 34.8), (40, 44.8), "anchor digest", off=(-4, 0))
arrow((69.5, 34.8), (52, 44.8), "anchor digest", off=(4, 0))
arrow((61.2, 51.5), (63.8, 51.5))
arrow((63.8, 60.6), (58, 58.3), None, color="#777777")
# feedback loop: score -> proposer weight
arrow((33, 48), (30.2, 48), None, color="#b2182b")
ax.text(17, 43.4, "feedback: settled score S sets proposer weight", fontsize=6.8, ha="center", color="#b2182b")
arrow((45, 58.4), (30, 68.8), "verified evidence", off=(-4, 0))
arrow((76.5, 58.4), (69.5, 68.8), None)
arrow((52, 58.4), (60, 68.8), "settlement records", off=(4.5, 0))

fig.tight_layout()
fig.savefig(root / "figures" / "fig1_architecture.png")
print("written fig1_architecture.png")
