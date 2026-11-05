"""Deploy the compiled contracts to a local EVM (eth-tester/py-evm) and measure
real gas consumption for the transaction types reported in the manuscript.
Gas figures are deterministic under EVM semantics, so these numbers are
reproducible on any EVM-compatible chain (e.g., Hyperledger Besu) up to
client-level intrinsic-cost differences."""
import json, pathlib
from web3 import Web3, EthereumTesterProvider

root = pathlib.Path(__file__).resolve().parents[1]
art = json.loads((root / "results" / "artifacts.json").read_text())

w3 = Web3(EthereumTesterProvider())
gov, org, buyer = w3.eth.accounts[0], w3.eth.accounts[1], w3.eth.accounts[2]

def deploy(name, *args):
    c = w3.eth.contract(abi=art[name]["abi"], bytecode=art[name]["bytecode"])
    tx = c.constructor(*args).transact({"from": gov})
    rcpt = w3.eth.get_transaction_receipt(tx)
    return w3.eth.contract(address=rcpt.contractAddress, abi=art[name]["abi"]), rcpt.gasUsed

gas = {}

# --- deploy ---
# cap=100 kg, epochCap=1000 kg, rho=1.0 (1e3), lambda=0.05 (=50000/1e6), kappa=0.8 (800/1e3)
tracker, g = deploy("EmissionTracker", 100, 1000, 1000, 50000, 800)
gas["deploy_EmissionTracker"] = g
# P_max = 1 gwei/credit, delta = 0.02 gwei/s, floor = 0.2 gwei
auction, g = deploy("CreditAuction", 10**9, 2 * 10**7, 2 * 10**8)
gas["deploy_CreditAuction"] = g

tracker.functions.setAuction(auction.address).transact({"from": gov})
auction.functions.setTracker(tracker.address).transact({"from": gov})

g = tracker.functions.enroll(org).transact({"from": gov})
gas["enroll_org"] = w3.eth.get_transaction_receipt(g).gasUsed

tracker.functions.registerLeader(gov).transact({"from": gov})

def anchor(bid, vals):
    d = Web3.solidity_keccak(["uint256[]"], [vals])
    tx = tracker.functions.recordAnchor(bid, d).transact({"from": gov})
    return w3.eth.get_transaction_receipt(tx).gasUsed

g = tracker.functions.deposit().transact({"from": org, "value": 10**18})
gas["escrow_deposit"] = w3.eth.get_transaction_receipt(g).gasUsed

# --- settleBatch: compliant batch, 8-tuple anchor (one cluster block) ---
tuples8 = [10] * 8  # 80 kg total, under 100 kg cap
gas["recordAnchor"] = anchor(b"\x01" * 32, tuples8)
tx = tracker.functions.settleBatch(b"\x01" * 32, org, tuples8).transact({"from": gov})
gas["settleBatch_compliant_8_tuples"] = w3.eth.get_transaction_receipt(tx).gasUsed

# --- settleBatch: violating batch (exceeds cap -> penalty + score decay) ---
tuples_v = [20] * 8  # 160 kg, excess 60 kg
anchor(b"\x02" * 32, tuples_v)
tx = tracker.functions.settleBatch(b"\x02" * 32, org, tuples_v).transact({"from": gov})
gas["settleBatch_violation_8_tuples"] = w3.eth.get_transaction_receipt(tx).gasUsed

# --- settleBatch with larger anchor (64 tuples) to expose per-tuple marginal cost ---
vals64 = [1] * 36 + [2] * 28  # 92 kg: compliant batch with non-zero tuple values
anchor(b"\x03" * 32, vals64)
tx = tracker.functions.settleBatch(b"\x03" * 32, org, vals64).transact({"from": gov})
gas["settleBatch_compliant_64_tuples"] = w3.eth.get_transaction_receipt(tx).gasUsed

# --- negative checks: unanchored and tampered settlements must revert ---
def reverts(fn):
    try:
        fn.transact({"from": gov}); return False
    except Exception:
        return True
gas["_check_unanchored_reverts"] = int(reverts(tracker.functions.settleBatch(b"\x04" * 32, org, tuples8)))
anchor(b"\x05" * 32, tuples8)
gas["_check_tampered_reverts"] = int(reverts(tracker.functions.settleBatch(b"\x05" * 32, org, [9] + tuples8[1:])))

# --- auction: open (manually via governor path), bid ---
tx = auction.functions.open(org, 50).transact({"from": gov})
gas["auction_open"] = w3.eth.get_transaction_receipt(tx).gasUsed

price = auction.functions.currentPrice(0).call()
tx = auction.functions.bid(0).transact({"from": buyer, "value": price * 50})
gas["auction_bid_clear"] = w3.eth.get_transaction_receipt(tx).gasUsed

# score sanity check: after 60 kg excess with lambda=0.05 -> exp(-3) ~ 0.0498
s = tracker.functions.score1e6(org).call()
gas["_score_after_60kg_excess_1e6"] = s

(root / "results" / "gas.json").write_text(json.dumps(gas, indent=2))
print(json.dumps(gas, indent=2))
