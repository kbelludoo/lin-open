// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: OI rejects swap-only markets, updates signed VI, and
// checks max open interest ONLY when delta > 0. Collateral sum does none of that.

    function applyDeltaToOpenInterest(
        DataStore dataStore,
        EventEmitter eventEmitter,
        Market.Props memory market,
        address collateralToken,
        bool isLong,
        int256 delta,
        bool useOpenInterestInTokens
    ) internal returns (uint256) {
        if (market.indexToken == address(0)) {
            revert Errors.OpenInterestCannotBeUpdatedForSwapOnlyMarket(market.marketToken);
        }

        uint256 nextValue = dataStore.applyDeltaToUint(
            Keys.openInterestKey(market.marketToken, collateralToken, isLong),
            delta,
            "Invalid state: negative open interest"
        );

        if (!useOpenInterestInTokens) {
            applyDeltaToVirtualInventoryForPositions(
                dataStore,
                eventEmitter,
                market.indexToken,
                isLong ? -delta : delta
            );
        }

        if (delta > 0) {
            validateOpenInterest(
                dataStore,
                market,
                isLong
            );
        }

        MarketEventUtils.emitOpenInterestUpdated(eventEmitter, market.marketToken, collateralToken, isLong, delta, nextValue);

        return nextValue;
    }
