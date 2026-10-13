// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol capPositiveImpactUsdByPositionImpactPool
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
//   git blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Pinned for audit of the impact-pool / lendable positive-impact cap.
// Not a full dump. Cap is impactPoolUsd + getMaxLendableUsdAvailable.
// Negative priceImpactUsd (<= 0) passes through. Distinct from
// capPositiveImpactUsdByMaxPositionImpact (applyFactor(sizeDelta, factor)).

    function capPositiveImpactUsdByPositionImpactPool(
        DataStore dataStore,
        Market.Props memory market,
        MarketPrices memory prices,
        int256 priceImpactUsd
    ) internal view returns (int256) {
        if (priceImpactUsd <= 0) {
            return priceImpactUsd;
        }

        CapPositiveImpactUsdByPositionImpactPoolCache memory cache;

        cache.impactPoolAmount = getPositionImpactPoolAmount(dataStore, market.marketToken);

        cache.impactPoolUsd = cache.impactPoolAmount * prices.indexTokenPrice.min;

        if (priceImpactUsd.toUint256() > cache.impactPoolUsd) {
            cache.usdRequiredToBeLent = priceImpactUsd.toUint256() - cache.impactPoolUsd;
        }

        if (cache.usdRequiredToBeLent > 0) {
            cache.lentAmount = dataStore.getUint(Keys.lentPositionImpactPoolAmountKey(market.marketToken));
            cache.longTokenUsd = getPoolAmount(dataStore, market, market.longToken)  * prices.longTokenPrice.min;
            cache.shortTokenUsd = getPoolAmount(dataStore, market, market.shortToken)  * prices.shortTokenPrice.min;

            cache.maxLendableUsd = getMaxLendableUsdAvailable(
                dataStore,
                market.marketToken,
                cache.longTokenUsd + cache.shortTokenUsd,
                prices.indexTokenPrice.max,
                cache.lentAmount
            );

            if (cache.usdRequiredToBeLent > cache.maxLendableUsd) {
                priceImpactUsd = cache.impactPoolUsd.toInt256() + cache.maxLendableUsd.toInt256();
            }
        }

        return priceImpactUsd;
    }
