// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: VI is applied IFF useOpenInterestInTokens is true
// (the inverse of applyDeltaToOpenInterest).

    function applyDeltaToOpenInterestInTokens(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address market,
        address indexToken,
        address collateralToken,
        bool isLong,
        int256 delta,
        bool useOpenInterestInTokens
    ) internal returns (uint256) {
        uint256 nextValue = dataStore.applyDeltaToUint(
            Keys.openInterestInTokensKey(market, collateralToken, isLong),
            delta,
            "Invalid state: negative open interest in tokens"
        );

        if (useOpenInterestInTokens) {
            applyDeltaToVirtualInventoryForPositionsInTokens(
                dataStore,
                eventEmitter,
                indexToken,
                isLong ? -delta : delta
            );
        }

        MarketEventUtils.emitOpenInterestInTokensUpdated(eventEmitter, market, collateralToken, isLong, delta, nextValue);

        return nextValue;
    }
