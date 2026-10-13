// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol getNextCumulativeBorrowingFactor
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Named contrast: delta = durationInSeconds * borrowingFactorPerSecond
// (raw product, not Precision.applyFactor). V1-style interval count is not used.

    function getNextCumulativeBorrowingFactor(
        DataStore dataStore,
        Market.Props memory market,
        MarketPrices memory prices,
        bool isLong
    ) internal view returns (uint256, uint256, uint256) {
        uint256 durationInSeconds = getSecondsSinceCumulativeBorrowingFactorUpdated(dataStore, market.marketToken, isLong);
        uint256 borrowingFactorPerSecond = getBorrowingFactorPerSecond(
            dataStore,
            market,
            prices,
            isLong
        );

        uint256 cumulativeBorrowingFactor = getCumulativeBorrowingFactor(dataStore, market.marketToken, isLong);

        uint256 delta = durationInSeconds * borrowingFactorPerSecond;
        uint256 nextCumulativeBorrowingFactor = cumulativeBorrowingFactor + delta;
        return (nextCumulativeBorrowingFactor, delta, borrowingFactorPerSecond);
    }
