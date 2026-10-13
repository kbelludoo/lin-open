// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol getMaxPositionImpactFactor
//   getMaxPositionImpactFactors
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Named contrast: stored maxPositiveImpactFactor is clamped down to
// maxNegativeImpactFactor. Skipping that clamp over-rebates.

    function getMaxPositionImpactFactor(DataStore dataStore, address market, bool isPositive) internal view returns (uint256) {
        (uint256 maxPositiveImpactFactor, uint256 maxNegativeImpactFactor) = getMaxPositionImpactFactors(dataStore, market);

        return isPositive ? maxPositiveImpactFactor : maxNegativeImpactFactor;
    }

    function getMaxPositionImpactFactors(DataStore dataStore, address market) internal view returns (uint256, uint256) {
        uint256 maxPositiveImpactFactor = dataStore.getUint(Keys.maxPositionImpactFactorKey(market, true));
        uint256 maxNegativeImpactFactor = dataStore.getUint(Keys.maxPositionImpactFactorKey(market, false));

        if (maxPositiveImpactFactor > maxNegativeImpactFactor) {
            maxPositiveImpactFactor = maxNegativeImpactFactor;
        }

        return (maxPositiveImpactFactor, maxNegativeImpactFactor);
    }
