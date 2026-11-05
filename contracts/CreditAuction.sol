// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title CreditAuction - Dutch auction with linear price decay for carbon credits
/// @notice Implements Algorithm 3 of the manuscript (Equation 9):
///         P(t) = P_max - delta * (t - t0), closing on a qualifying bid or at P_floor.
contract CreditAuction {
    struct Auction {
        address seller;
        uint256 credits;      // credits offered (kg CO2 equivalent)
        uint256 pMaxWei;      // P_max, wei per credit
        uint256 deltaWeiPerS; // delta, wei per credit per second
        uint256 pFloorWei;    // reserve floor
        uint256 t0;           // opening timestamp
        bool open;
        address buyer;
        uint256 clearingWei;
    }

    address public governor;
    address public tracker; // EmissionTracker allowed to open auctions
    uint256 public nextId;
    mapping(uint256 => Auction) public auctions;

    uint256 public defaultPMaxWei;
    uint256 public defaultDeltaWeiPerS;
    uint256 public defaultPFloorWei;

    event Opened(uint256 indexed id, address indexed seller, uint256 credits, uint256 pMaxWei);
    event Cleared(uint256 indexed id, address indexed buyer, uint256 priceWei);
    event ClosedUnsold(uint256 indexed id);

    modifier onlyAuthorized() {
        require(msg.sender == governor || msg.sender == tracker, "not authorized");
        _;
    }

    constructor(uint256 _pMaxWei, uint256 _deltaWeiPerS, uint256 _pFloorWei) {
        governor = msg.sender;
        defaultPMaxWei = _pMaxWei;
        defaultDeltaWeiPerS = _deltaWeiPerS;
        defaultPFloorWei = _pFloorWei;
    }

    function setTracker(address t) external { require(msg.sender == governor); tracker = t; }

    /// @notice Algorithm 3, step 1: open at P_max.
    function open(address seller, uint256 credits) external onlyAuthorized {
        uint256 id = nextId++;
        auctions[id] = Auction({
            seller: seller,
            credits: credits,
            pMaxWei: defaultPMaxWei,
            deltaWeiPerS: defaultDeltaWeiPerS,
            pFloorWei: defaultPFloorWei,
            t0: block.timestamp,
            open: true,
            buyer: address(0),
            clearingWei: 0
        });
        emit Opened(id, seller, credits, defaultPMaxWei);
    }

    /// @notice Algorithm 3, step 2: current price under linear decay (Eq. 9).
    function currentPrice(uint256 id) public view returns (uint256) {
        Auction storage a = auctions[id];
        require(a.open, "closed");
        uint256 elapsed = block.timestamp - a.t0;
        uint256 drop = a.deltaWeiPerS * elapsed;
        uint256 p = drop >= a.pMaxWei ? 0 : a.pMaxWei - drop;
        return p < a.pFloorWei ? a.pFloorWei : p;
    }

    /// @notice Algorithm 3, step 3: a bid at or above the current price clears the auction.
    function bid(uint256 id) external payable {
        Auction storage a = auctions[id];
        require(a.open, "closed");
        uint256 p = currentPrice(id);
        uint256 cost = p * a.credits;
        require(msg.value >= cost, "bid below price");
        a.open = false;
        a.buyer = msg.sender;
        a.clearingWei = p;
        (bool ok, ) = a.seller.call{value: cost}("");
        require(ok, "transfer failed");
        if (msg.value > cost) {
            (ok, ) = msg.sender.call{value: msg.value - cost}("");
            require(ok, "refund failed");
        }
        emit Cleared(id, msg.sender, p);
    }

    /// @notice Algorithm 3, step 4: close unsold at the floor; credits return to seller reserve.
    function closeUnsold(uint256 id) external onlyAuthorized {
        Auction storage a = auctions[id];
        require(a.open, "closed");
        require(currentPrice(id) <= a.pFloorWei, "above floor");
        a.open = false;
        emit ClosedUnsold(id);
    }
}
