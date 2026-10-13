// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Scalar kernel only. Not the full MarketUtils library.

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

        // if the open interest for longs is increased then tokens were virtually bought from the pool
        // so the virtual inventory should be decreased
        // if the open interest for longs is decreased then tokens were virtually sold to the pool
        // so the virtual inventory should be increased
        // if the open interest for shorts is increased then tokens were virtually sold to the pool
        // so the virtual inventory should be increased
        // if the open interest for shorts is decreased then tokens were virtually bought from the pool
        // so the virtual inventory should be decreased
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

    function applyDeltaToVirtualInventoryForPositions(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address token,
        int256 delta
    ) internal returns (bool, int256) {
        bytes32 virtualTokenId = dataStore.getBytes32(Keys.virtualTokenIdKey(token));
        if (virtualTokenId == bytes32(0)) {
            return (false, 0);
        }

        int256 nextValue = dataStore.applyDeltaToInt(
            Keys.virtualInventoryForPositionsKey(virtualTokenId),
            delta
        );

        MarketEventUtils.emitVirtualPositionInventoryUpdated(eventEmitter, token, virtualTokenId, delta, nextValue);

        return (true, nextValue);
    }

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
