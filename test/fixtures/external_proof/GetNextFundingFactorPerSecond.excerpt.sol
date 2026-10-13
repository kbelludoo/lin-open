// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// Kernel only: getNextFundingFactorPerSecond. Not the full file.
// Not getNextFundingAmountPerSize (other clone).

    // in case the minFundingFactorPerSecond is not zero, and the long / short skew has flipped
    // if orders are being created frequently it is possible that the minFundingFactorPerSecond prevents
    // the nextSavedFundingFactorPerSecond from being decreased fast enough for the sign to eventually flip
    // if it is bound by minFundingFactorPerSecond
    // for that reason, only the nextFundingFactorPerSecond is bound by minFundingFactorPerSecond
    // and the nextSavedFundingFactorPerSecond is not bound by minFundingFactorPerSecond
    function getNextFundingFactorPerSecond(
        DataStore dataStore,
        Market.Props memory market,
        uint256 indexTokenPrice,
        uint256 durationInSeconds
    ) internal view returns (uint256, bool, int256) {
        if (cache.diffUsd == 0 && configCache.fundingIncreaseFactorPerSecond == 0) {
            return (0, true, 0);
        }
        bool isSkewTheSameDirectionAsFunding = (cache.savedFundingFactorPerSecond > 0 && longOpenInterest > shortOpenInterest) || (cache.savedFundingFactorPerSecond < 0 && shortOpenInterest > longOpenInterest);
        int256 increaseValue = Precision.applyFactor(cache.diffUsdToOpenInterestFactor, configCache.fundingIncreaseFactorPerSecond).toInt256() * durationInSeconds.toInt256();
        uint256 decreaseValue = configCache.fundingDecreaseFactorPerSecond * durationInSeconds;
        cache.nextSavedFundingFactorPerSecond = cache.savedFundingFactorPerSecond / cache.savedFundingFactorPerSecondMagnitude.toInt256();
        cache.nextSavedFundingFactorPerSecond = Calc.boundMagnitude(
            cache.nextSavedFundingFactorPerSecond,
            0,
            configCache.maxFundingFactorPerSecond
        );
        cache.nextSavedFundingFactorPerSecondWithMinBound = Calc.boundMagnitude(
            cache.nextSavedFundingFactorPerSecond,
            configCache.minFundingFactorPerSecond,
            configCache.maxFundingFactorPerSecond
        );
        return (
            cache.nextSavedFundingFactorPerSecondWithMinBound.abs(),
            cache.nextSavedFundingFactorPerSecondWithMinBound > 0,
            cache.nextSavedFundingFactorPerSecond
        );
    }
