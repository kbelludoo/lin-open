// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol getKinkBorrowingFactor
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.

    function getKinkBorrowingFactor(
        DataStore dataStore,
        Market.Props memory market,
        bool isLong,
        uint256 reservedUsd,
        uint256 poolUsd,
        uint256 optimalUsageFactor
    ) internal view returns (uint256) {
        uint256 usageFactor = getUsageFactor(
            dataStore,
            market,
            isLong,
            reservedUsd,
            poolUsd
        );

        uint256 baseBorrowingFactor = dataStore.getUint(Keys.baseBorrowingFactorKey(market.marketToken, isLong));

        uint256 borrowingFactorPerSecond = Precision.applyFactor(
            usageFactor,
            baseBorrowingFactor
        );

        if (usageFactor > optimalUsageFactor && Precision.FLOAT_PRECISION > optimalUsageFactor) {
            uint256 diff = usageFactor - optimalUsageFactor;

            uint256 aboveOptimalUsageBorrowingFactor = dataStore.getUint(Keys.aboveOptimalUsageBorrowingFactorKey(market.marketToken, isLong));
            uint256 additionalBorrowingFactorPerSecond;

            if (aboveOptimalUsageBorrowingFactor > baseBorrowingFactor) {
                additionalBorrowingFactorPerSecond = aboveOptimalUsageBorrowingFactor - baseBorrowingFactor;
            }

            uint256 divisor = Precision.FLOAT_PRECISION - optimalUsageFactor;

            borrowingFactorPerSecond += additionalBorrowingFactorPerSecond * diff / divisor;
        }

        return borrowingFactorPerSecond;
    }
