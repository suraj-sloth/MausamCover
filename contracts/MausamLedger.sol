// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MausamLedger: public, tamper-evident audit trail for simulated cover.
/// @notice Testnet only. Holds no funds, mints no tokens. It records what was
///         promised (terms), what was observed, what the market priced, and
///         what was paid, so anyone can check settlement against the terms.
contract MausamLedger {
    address public immutable operator;

    struct Policy {
        bytes32 termsHash;
        uint32 thresholdMmX10;   // rain trigger, mm * 10
        uint32 layer1Payout;     // INR
        uint32 layer2Payout;     // INR (0 if not bought)
        uint64 committedAt;
        bool settled;
    }

    mapping(bytes32 => Policy) public policies;

    event PolicyCommitted(bytes32 indexed policyId, bytes32 termsHash, uint32 thresholdMmX10,
                          uint32 layer1Payout, uint32 layer2Payout);
    event PriceRecorded(bytes32 indexed policyId, uint16 impliedProbBps);
    event ObservationPosted(bytes32 indexed policyId, string day, uint32 rainMmX10, uint16 indexDropBps);
    event Settled(bytes32 indexed policyId, uint32 layer1Paid, uint32 layer2Paid);

    modifier onlyOperator() {
        require(msg.sender == operator, "not operator");
        _;
    }

    constructor() {
        operator = msg.sender;
    }

    function commitPolicy(bytes32 policyId, bytes32 termsHash, uint32 thresholdMmX10,
                          uint32 layer1Payout, uint32 layer2Payout) external onlyOperator {
        require(policies[policyId].committedAt == 0, "exists");
        policies[policyId] = Policy(termsHash, thresholdMmX10, layer1Payout, layer2Payout,
                                    uint64(block.timestamp), false);
        emit PolicyCommitted(policyId, termsHash, thresholdMmX10, layer1Payout, layer2Payout);
    }

    function recordPrice(bytes32 policyId, uint16 impliedProbBps) external onlyOperator {
        require(policies[policyId].committedAt != 0, "no policy");
        emit PriceRecorded(policyId, impliedProbBps);
    }

    function postObservation(bytes32 policyId, string calldata day, uint32 rainMmX10,
                             uint16 indexDropBps) external onlyOperator {
        require(policies[policyId].committedAt != 0, "no policy");
        emit ObservationPosted(policyId, day, rainMmX10, indexDropBps);
    }

    /// Payouts must match the committed terms: layer 1 pays its fixed amount or
    /// nothing; layer 2 likewise. The chain rejects any other number.
    function settle(bytes32 policyId, uint32 layer1Paid, uint32 layer2Paid) external onlyOperator {
        Policy storage p = policies[policyId];
        require(p.committedAt != 0, "no policy");
        require(!p.settled, "settled");
        require(layer1Paid == 0 || layer1Paid == p.layer1Payout, "layer1 != terms");
        require(layer2Paid == 0 || layer2Paid == p.layer2Payout, "layer2 != terms");
        p.settled = true;
        emit Settled(policyId, layer1Paid, layer2Paid);
    }
}
