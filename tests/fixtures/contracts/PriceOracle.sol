// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IPair {
    function getReserves() external view returns (uint112, uint112, uint32);
}

/// `getPrice` reads an instantaneous reserves ratio (a spot price). This
/// diverges from the Uniswap V2 TWAP canonical reference, which samples the
/// cumulative price accumulators over time.
contract PriceOracle {
    IPair public pair;

    function getPrice() external view returns (uint256) {
        (uint112 reserve0, uint112 reserve1, ) = pair.getReserves();
        return (uint256(reserve1) * 1e18) / uint256(reserve0);
    }
}
