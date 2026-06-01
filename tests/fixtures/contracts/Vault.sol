// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// A small vault used as a scan fixture. `setFeeRecipient` is missing an
/// access-control guard; `setOwner` has one.
contract Vault {
    address public owner;
    address public feeRecipient;
    mapping(address => uint256) public balances;
    uint256 public totalDeposits;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    // Missing access control: any caller can change the fee recipient.
    function setFeeRecipient(address recipient) external {
        feeRecipient = recipient;
    }

    // Has access control.
    function setOwner(address newOwner) external onlyOwner {
        owner = newOwner;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }
}
