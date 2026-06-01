// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// A clean token used to check that the production recipes do not fire here:
/// `mint` is access-controlled and keeps the aggregate `totalSupply` in step
/// with the keyed `balances`.
contract Token {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;
    address public owner;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function mint(address to, uint256 amount) external onlyOwner {
        balances[to] += amount;
        totalSupply += amount;
    }

    function transfer(address to, uint256 amount) external {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }
}
