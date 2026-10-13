// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol getMaxLendableUsdAvailable
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
//   git blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Lendable headroom is min(applyFactor(poolUsd, maxLendableFactor),
// maxLendableUsdConfig) minus already-lent USD. Over-lent returns 0.

    function getMaxLendableUsdAvailable(
        DataStore dataStore,
        address market,
        uint256 poolUsd,
        uint256 indexTokenPrice,
        uint256 lentAmount
    ) internal view returns (uint256) {
        uint256 maxLendableFactor = dataStore.getUint(Keys.maxLendableImpactFactorKey(market));
        uint256 maxLendableUsd = Precision.applyFactor(poolUsd, maxLendableFactor);

        uint256 maxLendableUsdConfig = dataStore.getUint(Keys.maxLendableImpactUsdKey(market));
        if (maxLendableUsd > maxLendableUsdConfig) {
            maxLendableUsd = maxLendableUsdConfig;
        }

        uint256 lentUsd = lentAmount * indexTokenPrice;

        if (lentUsd > maxLendableUsd) {
            return 0;
        }

        return maxLendableUsd - lentUsd;
    }
