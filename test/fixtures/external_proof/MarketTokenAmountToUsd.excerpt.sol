    function marketTokenAmountToUsd(
        uint256 marketTokenAmount,
        uint256 poolValue,
        uint256 supply
    ) internal pure returns (uint256) {
        if (supply == 0) { revert Errors.EmptyMarketTokenSupply(); }

        return Precision.mulDiv(poolValue, marketTokenAmount, supply);
    }
