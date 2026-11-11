// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: max OI is only invoked from applyDeltaToOpenInterest when delta > 0.

    function validateOpenInterest(
        DataStore dataStore,
        Market.Props memory market,
        bool isLong
    ) internal view {
        uint256 openInterest = getOpenInterest(dataStore, market, isLong);
        uint256 maxOpenInterest = getMaxOpenInterest(dataStore, market.marketToken, isLong);

        if (openInterest > maxOpenInterest) {
            revert Errors.MaxOpenInterestExceeded(openInterest, maxOpenInterest);
        }
    }
