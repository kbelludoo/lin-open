    function usdToMarketTokenAmount(
        uint256 usdValue,
        uint256 poolValue,
        uint256 supply
    ) internal pure returns (uint256) {
        // if the supply and poolValue is zero, use 1 USD as the token price
        if (supply == 0 && poolValue == 0) {
            return Precision.floatToWei(usdValue);
        }

        // if the supply is zero and the poolValue is more than zero,
        // then include the poolValue for the amount of tokens minted so that
        // the market token price after mint would be 1 USD
        if (supply == 0 && poolValue > 0) {
            return Precision.floatToWei(poolValue + usdValue);
        }

        // round market tokens down
        return Precision.mulDiv(supply, usdValue, poolValue);
    }
