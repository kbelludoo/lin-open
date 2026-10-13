// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// Kernel only: getNextFundingAmountPerSize fundingUsd. Not the full file.

        // if either long or short open interest is zero, then funding should not be updated
        // as there would not be any user to pay the funding to
        if (cache.longOpenInterest == 0 || cache.shortOpenInterest == 0) {
            return result;
        }

        cache.sizeOfPayingSide = result.longsPayShorts ? cache.longOpenInterest : cache.shortOpenInterest;

        // due to these, the fundingUsd should be divided by the divisor
        cache.fundingUsd = Precision.applyFactor(cache.sizeOfPayingSide, cache.durationInSeconds * result.fundingFactorPerSecond);
        cache.fundingUsd = cache.fundingUsd / divisor;

        if (result.longsPayShorts) {
            cache.fundingUsdForLongCollateral = Precision.mulDiv(cache.fundingUsd, cache.openInterest.long.longToken, cache.longOpenInterest);
            cache.fundingUsdForShortCollateral = Precision.mulDiv(cache.fundingUsd, cache.openInterest.long.shortToken, cache.longOpenInterest);
        }
