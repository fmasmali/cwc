// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title EmissionTracker - batch emission settlement, penalties, and compliance score decay
/// @notice Implements Algorithm 2 of the manuscript (Equations 7-8).
///         Fixed-point convention: scores and rates are scaled by 1e6 unless noted.
interface ICreditAuction {
    function open(address seller, uint256 credits) external;
}

contract EmissionTracker {
    struct Batch {
        address custodian;
        uint256 emissionsKg;
        bool settled;
        bool violated;
    }

    address public governor;
    ICreditAuction public auction;

    uint256 public capKg;          // per-batch cap C (kg CO2)
    uint256 public epochCapKg;     // organizational epoch cap
    uint256 public rho1e3;         // penalty rate (wei per kg, scaled 1e3)
    uint256 public lambda1e6;      // score decay rate lambda (per kg, scaled 1e6)
    uint256 public kappa1e3;       // auction trigger fraction of epoch cap (scaled 1e3)

    mapping(bytes32 => Batch) public batches;
    mapping(address => uint256) public epochEmissionsKg; // epoch emission ledger
    mapping(address => uint256) public score1e6;         // compliance score S, scaled 1e6
    mapping(address => uint256) public escrow;           // penalty escrow (wei)
    mapping(address => bool) public enrolled;            // enrolled organizations
    mapping(address => bool) public leaders;             // registered cluster leaders
    mapping(bytes32 => uint256) public anchoredAt;       // block number of each batch anchor
    mapping(bytes32 => bytes32) public anchorDigest;     // digest of the anchored tuple values

    event Enrolled(address indexed org);
    event Settled(bytes32 indexed batchId, address indexed custodian, uint256 emissionsKg);
    event Violation(bytes32 indexed batchId, uint256 excessKg, uint256 penaltyWei);
    event AuctionTriggered(address indexed org, uint256 epochEmissionsKg);
    event Anchored(bytes32 indexed batchId, bytes32 digest, address indexed leader);

    modifier onlyGovernor() { require(msg.sender == governor, "not governor"); _; }

    constructor(uint256 _capKg, uint256 _epochCapKg, uint256 _rho1e3,
                uint256 _lambda1e6, uint256 _kappa1e3) {
        governor = msg.sender;
        capKg = _capKg;
        epochCapKg = _epochCapKg;
        rho1e3 = _rho1e3;
        lambda1e6 = _lambda1e6;
        kappa1e3 = _kappa1e3;
    }

    function setAuction(address a) external onlyGovernor { auction = ICreditAuction(a); }

    function enroll(address org) external onlyGovernor {
        enrolled[org] = true;
        score1e6[org] = 1_000_000; // S = 1.0
        emit Enrolled(org);
    }

    function registerLeader(address leader) external onlyGovernor { leaders[leader] = true; }

    /// @notice Cluster leaders anchor a batch digest (Section 5.2). Under QBFT's
    ///         immediate finality, an anchor included in an earlier block is final.
    function recordAnchor(bytes32 batchId, bytes32 digest) external {
        require(leaders[msg.sender], "not a leader");
        require(anchoredAt[batchId] == 0, "already anchored");
        anchoredAt[batchId] = block.number;
        anchorDigest[batchId] = digest;
        emit Anchored(batchId, digest, msg.sender);
    }

    function deposit() external payable { escrow[msg.sender] += msg.value; }

    /// @dev Fixed-point exp(-x) for x scaled by 1e6, via Pade(2,2):
    ///      e^{-x} ~= (x^2 - 6x + 12) / (x^2 + 6x + 12), clamped for large x.
    function expNeg1e6(uint256 x1e6) public pure returns (uint256) {
        if (x1e6 >= 1_000_000) {
            // beyond approximation range: halve repeatedly (e^{-x} = (e^{-x/2})^2)
            uint256 half = expNeg1e6(x1e6 / 2);
            return (half * half) / 1_000_000;
        }
        uint256 x2 = (x1e6 * x1e6) / 1_000_000;        // x^2, scaled 1e6
        uint256 num = x2 + 12_000_000 - 6 * x1e6;      // x^2 - 6x + 12
        uint256 den = x2 + 12_000_000 + 6 * x1e6;      // x^2 + 6x + 12
        return (num * 1_000_000) / den;
    }

    /// @notice Algorithm 2: settle a batch whose anchor is QBFT-final and digest-matched.
    /// @param batchId    identifier of the anchored batch
    /// @param custodian  organization holding custody of the batch
    /// @param tupleKg    verified per-tuple emission estimates (kg)
    function settleBatch(bytes32 batchId, address custodian, uint256[] calldata tupleKg)
        external onlyGovernor
    {
        require(enrolled[custodian], "custodian not enrolled");
        // step 1: the anchor must be committed in an earlier (hence QBFT-final) block,
        // and the settled values must be exactly those that were anchored
        uint256 anchorBlock = anchoredAt[batchId];
        require(anchorBlock != 0 && anchorBlock < block.number, "anchor not final");
        require(keccak256(abi.encodePacked(tupleKg)) == anchorDigest[batchId], "digest mismatch");
        Batch storage b = batches[batchId];
        require(!b.settled, "already settled");

        uint256 total = 0;
        for (uint256 i = 0; i < tupleKg.length; i++) total += tupleKg[i]; // step 2

        b.custodian = custodian;
        b.emissionsKg = total;
        b.settled = true;

        epochEmissionsKg[custodian] += total;                             // step 3

        if (total > capKg) {                                              // step 4
            uint256 excess = total - capKg;
            uint256 penalty = (rho1e3 * excess * 1e15) / 1e3;             // step 5 (Eq. 8)
            uint256 avail = escrow[custodian];
            escrow[custodian] = penalty >= avail ? 0 : avail - penalty;
            // step 6 (Eq. 7): S <- S * exp(-lambda * excess)
            uint256 decay = expNeg1e6(lambda1e6 * excess);
            score1e6[custodian] = (score1e6[custodian] * decay) / 1_000_000;
            b.violated = true;
            emit Violation(batchId, excess, penalty);                     // step 7
        }

        if (address(auction) != address(0) &&
            epochEmissionsKg[custodian] * 1e3 >= kappa1e3 * epochCapKg) { // step 8
            auction.open(custodian, epochEmissionsKg[custodian] - (kappa1e3 * epochCapKg) / 1e3);
            emit AuctionTriggered(custodian, epochEmissionsKg[custodian]);
        }

        emit Settled(batchId, custodian, total);
    }

    function resetEpoch(address org) external onlyGovernor { epochEmissionsKg[org] = 0; }
}
