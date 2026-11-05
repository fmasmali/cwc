"""Simulation model for the IoT-enhanced hybrid blockchain artifact.

Every timing and behavioral parameter is declared in CONFIG below and mirrors
Table 2 of the manuscript. The discrete-event components (bottleneck queues)
use SimPy; surrounding stage delays are Monte Carlo compositions. All
randomness flows through a per-run numpy Generator so every figure and number
is reproducible from (config, seed).
"""
import numpy as np
import simpy

CONFIG = dict(
    # --- device / network timing (ms) ---
    sign_ms_mean=12.0, sign_ms_sd=1.5,            # ECDSA sign, CryptoCell-class accelerator
    uplink_lognorm_median=120.0, uplink_sigma=0.45,  # LTE-M uplink latency
    cluster_batch_interval_ms=500.0,              # leader candidate-block cadence
    leader_service_ms=20.0,                       # verify sig + plausibility + aggregate, per tuple
    raft_rtt_ms_mean=40.0, raft_rtt_ms_sd=10.0,   # local replication round
    qbft_block_ms=2000.0, qbft_commit_ms_mean=180.0, qbft_commit_ms_sd=30.0,
    # --- baselines ---
    pow_block_ms=5000.0, pow_conf_depth=1,        # finality = inclusion + 1 confirmation
    pow_exec_ms=6.0,                              # on-chain full validation per tx
    poa_block_ms=2000.0, poa_exec_ms=3.0,         # passive-feed PoA, per-tx execution
    central_service_ms=1.0, central_overhead_per_dev=4e-4,
    # --- topology ---
    cluster_size=8,
    enterprise_validators=10,
    # --- compliance ---
    cap_kg=100.0, batch_mu=85.0, batch_sd=15.0,
    lam=0.05, rho=1.0,
    abate_gain=6.0, abate_relax=1.5,              # adaptive abatement response (kg)
    central_escape=0.20,                          # violations escaping a manipulable registry
    uniform_incentive=0.35,                       # abatement response without weighting, relative to weighted (=1.0)
    epochs=40, orgs=10, batches_per_epoch=6,
    sensor_fault_rate=0.0025, fault_bias_kg=30.0,
    # --- auction ---
    p_max=1.0, delta=0.02, p_floor=0.2,
    bidder_rate_stable=0.4, bidder_rate_stress=0.8,   # arrivals per second
    valuation_low=0.45, valuation_high=0.95,
    # --- consumer ---
    n_products=40, display_age_s=3.0, sensor_noise=0.015, decay_k=0.004,
    # --- eligibility / election ---
    theta=0.6,
    # --- scenario knobs ---
    partition_rate_stable=0.002, partition_rate_stress=0.005,   # per second
    partition_len_s=(1.0, 4.0),
    emission_spike_p=0.20, emission_spike_factor=1.5,
    inject_rate=0.05,                              # forged tuples under attack
)


# ---------------------------------------------------------------- utilities
def uplink(rng, cfg, n):
    mu = np.log(cfg["uplink_lognorm_median"])
    return rng.lognormal(mu, cfg["uplink_sigma"], n)


def mds_queue_wait(env_time_s, arrivals_s, service_ms, rng):
    """SimPy single-server FIFO queue; returns sojourn times (ms) for arrivals."""
    env = simpy.Environment()
    server = simpy.Resource(env, capacity=1)
    out = []

    def job(t_arr):
        yield env.timeout(t_arr)
        with server.request() as req:
            yield req
            # per-job service jitter (~10% lognormal) around the nominal time
            yield env.timeout(service_ms * float(rng.lognormal(-0.005, 0.1)) / 1000.0)
            out.append((env.now - t_arr) * 1000.0)

    for t in arrivals_s:
        env.process(job(t))
    env.run(until=env_time_s + 60)
    return np.array(out)


# ---------------------------------------------------------------- latency & throughput
def latency_hybrid(rng, cfg, offered_tps, n_nodes, duration_s=60):
    n_clusters = max(1, n_nodes // cfg["cluster_size"])
    per_cluster_tps = offered_tps / n_clusters
    n = rng.poisson(per_cluster_tps * duration_s)
    arrivals = np.sort(rng.uniform(0, duration_s, n))
    sojourn = mds_queue_wait(duration_s, arrivals, cfg["leader_service_ms"], rng)
    m = len(sojourn)
    if m == 0:
        return np.array([np.nan])
    sign = rng.normal(cfg["sign_ms_mean"], cfg["sign_ms_sd"], m)
    up = uplink(rng, cfg, m)
    batch_wait = rng.uniform(0, cfg["cluster_batch_interval_ms"], m)
    raft = rng.normal(cfg["raft_rtt_ms_mean"], cfg["raft_rtt_ms_sd"], m).clip(5)
    anchor_wait = rng.uniform(0, cfg["qbft_block_ms"], m)
    commit = rng.normal(cfg["qbft_commit_ms_mean"], cfg["qbft_commit_ms_sd"], m).clip(50)
    return (sign + up + batch_wait + sojourn + raft + anchor_wait + commit) / 1000.0


def latency_pow(rng, cfg, offered_tps, duration_s=60):
    n = rng.poisson(offered_tps * duration_s)
    arrivals = np.sort(rng.uniform(0, duration_s, n))
    sojourn = mds_queue_wait(duration_s, arrivals, cfg["pow_exec_ms"], rng)
    m = len(sojourn)
    sign = rng.normal(cfg["sign_ms_mean"], cfg["sign_ms_sd"], m)
    up = uplink(rng, cfg, m)
    incl = rng.uniform(0, cfg["pow_block_ms"], m)
    conf = cfg["pow_conf_depth"] * cfg["pow_block_ms"]
    return (sign + up + sojourn + incl + conf) / 1000.0


def latency_poa(rng, cfg, offered_tps, duration_s=60):
    n = rng.poisson(offered_tps * duration_s)
    arrivals = np.sort(rng.uniform(0, duration_s, n))
    sojourn = mds_queue_wait(duration_s, arrivals, cfg["poa_exec_ms"], rng)
    m = len(sojourn)
    sign = rng.normal(cfg["sign_ms_mean"], cfg["sign_ms_sd"], m)
    up = uplink(rng, cfg, m)
    incl = rng.uniform(0, cfg["poa_block_ms"], m)
    commit = rng.normal(cfg["qbft_commit_ms_mean"], cfg["qbft_commit_ms_sd"], m).clip(50)
    return (sign + up + sojourn + incl + commit) / 1000.0


def latency_central(rng, cfg, offered_tps, n_nodes, duration_s=60):
    svc = cfg["central_service_ms"] * (1 + cfg["central_overhead_per_dev"] * n_nodes)
    n = rng.poisson(offered_tps * duration_s)
    arrivals = np.sort(rng.uniform(0, duration_s, n))
    sojourn = mds_queue_wait(duration_s, arrivals, svc, rng)
    m = len(sojourn)
    up = uplink(rng, cfg, m)
    return (up + sojourn) / 1000.0


def peak_tps(rng, cfg, arch, n_nodes, duration_s=30):
    """Saturation throughput: drive well past capacity, count completions/s."""
    if arch == "hybrid":
        n_clusters = max(1, n_nodes // cfg["cluster_size"])
        cap = n_clusters * 1000.0 / cfg["leader_service_ms"]
        offered = cap * 1.5
        per_cluster = offered / n_clusters
        done = 0
        for _ in range(n_clusters):
            n = rng.poisson(per_cluster * duration_s)
            arr = np.sort(rng.uniform(0, duration_s, n))
            s = mds_queue_wait(duration_s, arr, cfg["leader_service_ms"], rng)
            fin = arr + s / 1000.0
            done += np.sum((fin >= 5) & (fin <= duration_s))
        return done / (duration_s - 5)
    if arch == "poa":
        offered = 1.5 * 1000.0 / cfg["poa_exec_ms"]
    elif arch == "pow":
        offered = 1.5 * 1000.0 / cfg["pow_exec_ms"]
    else:  # central
        svc = cfg["central_service_ms"] * (1 + cfg["central_overhead_per_dev"] * n_nodes)
        offered = 1.5 * 1000.0 / svc
    svc_ms = dict(poa=cfg["poa_exec_ms"], pow=cfg["pow_exec_ms"],
                  central=cfg["central_service_ms"] * (1 + cfg["central_overhead_per_dev"] * n_nodes))[arch]
    n = rng.poisson(offered * duration_s)
    arr = np.sort(rng.uniform(0, duration_s, n))
    s = mds_queue_wait(duration_s, arr, svc_ms, rng)
    fin = arr + s / 1000.0
    return np.sum((fin >= 5) & (fin <= duration_s)) / (duration_s - 5)


# ---------------------------------------------------------------- synchronization
def sync_accuracy(rng, cfg, scenario, duration_s=600):
    rate = cfg["partition_rate_stress"] if scenario == "stress" else cfg["partition_rate_stable"]
    n_part = rng.poisson(rate * duration_s)
    starts = rng.uniform(0, duration_s, n_part)
    lens = rng.uniform(*cfg["partition_len_s"], n_part)
    block = cfg["qbft_block_ms"] / 1000.0
    grid = np.arange(0, duration_s, 1.0)
    diverged = np.zeros_like(grid, dtype=bool)
    for s0, L in zip(starts, lens):
        heal = s0 + L + block  # reconciliation within one block interval
        diverged |= (grid >= s0) & (grid < heal)
    return 1.0 - diverged.mean()


# ---------------------------------------------------------------- compliance agents
def compliance_run(rng, cfg, weighted=True, centralized=False, scenario="stable"):
    """Adaptive organizations; returns adherence, penalty accuracy,
    violation recurrence, proposal Gini, contraction stats."""
    orgs = cfg["orgs"]
    mu = np.full(orgs, cfg["batch_mu"])
    S = np.ones(orgs)
    tau = np.ones(orgs)
    proposals = np.zeros(orgs)
    violations = []
    total_b = comply_b = 0
    tp = fp = fn = tn = 0
    first_viol = {}
    recur = []
    contraction_after3 = None
    viol_count = np.zeros(orgs, dtype=int)

    for ep in range(cfg["epochs"]):
        for _ in range(cfg["batches_per_epoch"]):
            j = int(rng.integers(orgs))
            e = rng.normal(mu[j], cfg["batch_sd"])
            if scenario == "stress" and rng.random() < cfg["emission_spike_p"]:
                e *= cfg["emission_spike_factor"]
            e = max(e, 5.0)
            # sensor faults inflate the *measured* value
            measured = e
            faulty = rng.random() < cfg["sensor_fault_rate"] * cfg["cluster_size"]
            if faulty:
                measured += cfg["fault_bias_kg"]
            true_v = e > cfg["cap_kg"]
            det_v = measured > cfg["cap_kg"]
            if centralized and det_v and rng.random() < cfg["central_escape"]:
                det_v = False  # manipulable registry drops the record
            total_b += 1
            comply_b += (not true_v)
            tp += (true_v and det_v); fp += ((not true_v) and det_v)
            fn += (true_v and (not det_v)); tn += ((not true_v) and (not det_v))
            if det_v:
                excess = measured - cfg["cap_kg"]
                S[j] *= np.exp(-cfg["lam"] * excess)
                viol_count[j] += 1
                violations.append((ep, j, excess))
                if j not in first_viol:
                    first_viol[j] = ep
                elif ep - first_viol[j] <= 5:
                    recur.append(j)
                # deterrence: abatement response scales with the realized score loss,
                # i.e., with the marginal consensus-income loss of Proposition 1
                incentive = 1.0 if weighted else cfg["uniform_incentive"]
                loss = 1.0 - np.exp(-cfg["lam"] * excess)
                mu[j] = max(50.0, mu[j] - cfg["abate_gain"] * incentive * (0.4 + 2.2 * loss))
            else:
                mu[j] = min(cfg["batch_mu"], mu[j] + cfg["abate_relax"] / cfg["batches_per_epoch"])
        # proposer selection this epoch (one proposal per block; 30 blocks/epoch)
        w = tau * (S if weighted else 1.0)
        p = w / w.sum()
        proposals += rng.multinomial(30, p)

    # contraction after 3 violations for the worst violator vs compliant counterfactual
    if violations:
        j = int(np.argmax(viol_count))
        exc = [v[2] for v in violations if v[1] == j][:3]
        if len(exc) >= 3:
            Sv = np.exp(-cfg["lam"] * np.sum(exc))
            others = orgs - 1
            p_v = Sv / (Sv + others)
            p_c = 1.0 / orgs
            contraction_after3 = 1 - p_v / p_c

    gini = _gini(proposals)
    adherence = comply_b / total_b
    pen_acc = (tp + tn) / total_b
    n_first = len(first_viol)
    recurrence = (len(set(recur)) / n_first) if n_first else 0.0
    return dict(adherence=adherence, penalty_accuracy=pen_acc,
                recurrence=recurrence, gini=gini,
                contraction_after3=contraction_after3)


def _gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if x.sum() == 0:
        return 0.0
    return (2 * np.sum((np.arange(1, n + 1)) * x) / (n * x.sum())) - (n + 1) / n


# ---------------------------------------------------------------- auction
def auction_run(rng, cfg, scenario="stable", n_auctions=50):
    rate = cfg["bidder_rate_stress"] if scenario == "stress" else cfg["bidder_rate_stable"]
    horizon = (cfg["p_max"] - cfg["p_floor"]) / cfg["delta"]
    times, prices, sold = [], [], 0
    devs = []  # deviation from per-auction competitive benchmark (best valuation)
    for _ in range(n_auctions):
        n_bid = rng.poisson(rate * horizon)
        t_arr = np.sort(rng.uniform(0, horizon, n_bid))
        vals = rng.uniform(cfg["valuation_low"], cfg["valuation_high"], n_bid)
        cleared = False
        best = -np.inf
        for t, v in zip(t_arr, vals):
            best = max(best, v)
            price_t = cfg["p_max"] - cfg["delta"] * t
            if v >= price_t:
                times.append(t); prices.append(price_t); sold += 1
                if vals.size:
                    devs.append(abs(price_t - vals.max()) / vals.max())
                cleared = True
                break
        if not cleared and best >= cfg["p_floor"]:
            t_hit = (cfg["p_max"] - best) / cfg["delta"]
            times.append(t_hit); prices.append(best); sold += 1
            devs.append(abs(best - vals.max()) / vals.max())
    return dict(completion_s=float(np.mean(times)) if times else np.nan,
                clearing=float(np.mean(prices)) if prices else np.nan,
                price_dev=float(np.mean(devs)) if devs else np.nan,
                fill=sold / n_auctions)


# ---------------------------------------------------------------- consumer fidelity
def ranking_fidelity(rng, cfg, w):
    n = cfg["n_products"]
    Q0 = 1.0
    age_h = rng.uniform(2, 48, n)                      # product age (hours)
    k = cfg["decay_k"]
    Q_true = Q0 * np.exp(-k * age_h)
    E_true = rng.normal(cfg["batch_mu"], cfg["batch_sd"], n).clip(20, cfg["cap_kg"])
    U_true = w * Q_true / Q0 + (1 - w) * (cfg["cap_kg"] - E_true) / cfg["cap_kg"]
    # displayed values: bounded staleness + attested-sensor noise
    stale_h = cfg["display_age_s"] / 3600.0
    Q_disp = Q0 * np.exp(-k * (age_h + stale_h)) * (1 + rng.normal(0, cfg["sensor_noise"], n))
    E_disp = E_true * (1 + rng.normal(0, cfg["sensor_noise"], n))
    U_disp = w * Q_disp / Q0 + (1 - w) * (cfg["cap_kg"] - E_disp) / cfg["cap_kg"]
    # normalized Kendall agreement
    r_true = np.argsort(np.argsort(-U_true))
    r_disp = np.argsort(np.argsort(-U_disp))
    disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            disc += ((r_true[i] - r_true[j]) * (r_disp[i] - r_disp[j]) < 0)
    return 1 - 2 * disc / (n * (n - 1) / 2) / 2  # 1 - normalized Kendall distance


# ---------------------------------------------------------------- attack / ablation A4
def injection_defense(rng, cfg, signatures=True, n_tuples=20000):
    forged = rng.random(n_tuples) < cfg["inject_rate"]
    n_f = forged.sum()
    if signatures:
        accepted = 0  # rejected deterministically at signature verification
    else:
        # hash-only: forged values must merely pass neighbor plausibility
        plaus_reject = rng.random(n_f) < 0.35
        accepted = int((~plaus_reject).sum())
    return dict(injected=int(n_f), accepted=int(accepted),
                rejection_rate=1.0 if signatures else 1 - accepted / max(n_f, 1))


# ---------------------------------------------------------------- election stability
def election_stability(rng, cfg, theta, blocks=100):
    size = cfg["cluster_size"]
    U = rng.uniform(0.5, 1.0, size)
    A = rng.uniform(0.6, 1.0, size)
    C = rng.uniform(0.7, 1.0, size)
    low_acc = A < 0.75
    relections = 0
    admitted_bad = 0
    cur = -1
    th = theta
    for _ in range(blocks):
        # scores drift
        U = np.clip(U + rng.normal(0, 0.02, size), 0.3, 1.0)
        A = np.clip(A + rng.normal(0, 0.02, size), 0.4, 1.0)
        elig = U * A * C > th
        t = th
        while not elig.any():
            t *= 0.9
            elig = U * A * C > t
        lead = int(np.argmax(np.where(elig, U * A, -1)))
        if lead != cur:
            relections += 1
            cur = lead
        admitted_bad += int(low_acc[lead])
    return dict(reelections=relections, bad_leader_share=admitted_bad / blocks)
