// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol capPositiveImpactUsdByMaxPositionImpact
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
//   git blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Pinned for audit of the one-sided positive price-impact cap.
// Not a full dump. Cap is applyFactor(sizeDeltaUsd, maxPositiveFactor).
// Negative priceImpactUsd passes through. Distinct from getCappedPnl
// (pool * maxPnlFactor) and from capPositiveImpactUsdByPositionImpactPool.

    function capPositiveImpactUsdByMaxPositionImpact(
        DataStore dataStore,
        address market,
        int256 priceImpactUsd,
        uint256 sizeDeltaUsd
    ) internal view returns (int256) {
        if (priceImpactUsd < 0) {
            return priceImpactUsd;
        }

        uint256 maxPriceImpactFactor = getMaxPositionImpactFactor(dataStore, market, true);
        int256 maxPriceImpactUsdBasedOnMaxPriceImpactFactor = Precision.applyFactor(sizeDeltaUsd, maxPriceImpactFactor).toInt256();

        // capped by the positive price impact
        if (priceImpactUsd > maxPriceImpactUsdBasedOnMaxPriceImpactFactor) {
            priceImpactUsd = maxPriceImpactUsdBasedOnMaxPriceImpactFactor;
        }

        return priceImpactUsd;
    }
