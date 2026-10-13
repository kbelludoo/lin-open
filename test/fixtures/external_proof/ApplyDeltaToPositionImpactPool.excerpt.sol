// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics @ a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later
// Pinned for LIN clone-lin external proof. Not a full contract.
    // @dev apply a delta to the position impact pool
    // @param dataStore DataStore
    // @param eventEmitter EventEmitter
    // @param market the market to apply to
    // @param delta the delta amount
    function applyDeltaToPositionImpactPool(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address market,
        int256 delta
    ) internal {
        ApplyDeltaToPositionImpactPoolCache memory cache;
        cache.deltaMagnitude = delta.abs();

        if (delta < 0) {
            cache.positionImpactPoolAmountKey = Keys.positionImpactPoolAmountKey(market);
            cache.poolAmount = dataStore.getUint(cache.positionImpactPoolAmountKey);

            if (cache.deltaMagnitude > cache.poolAmount) {
                cache.excessAmount = cache.deltaMagnitude - cache.poolAmount;

                dataStore.setUint(cache.positionImpactPoolAmountKey, 0);
                MarketEventUtils.emitPositionImpactPoolAmountUpdated(eventEmitter, market, cache.poolAmount.toInt256(), 0);

                cache.nextValue = dataStore.incrementUint(Keys.lentPositionImpactPoolAmountKey(market), cache.excessAmount);
                MarketEventUtils.emitLentPositionImpactPoolAmountUpdated(eventEmitter, market, cache.excessAmount.toInt256(), cache.nextValue);
            } else {
                cache.nextValue = dataStore.decrementUint(cache.positionImpactPoolAmountKey, cache.deltaMagnitude);
                MarketEventUtils.emitPositionImpactPoolAmountUpdated(eventEmitter, market, delta, cache.nextValue);
            }
        } else {
            cache.lentPositionImpactPoolAmountKey = Keys.lentPositionImpactPoolAmountKey(market);
            cache.poolAmount = dataStore.getUint(cache.lentPositionImpactPoolAmountKey);

            if (cache.deltaMagnitude > cache.poolAmount) {
                cache.excessAmount = cache.deltaMagnitude - cache.poolAmount;

                dataStore.setUint(cache.lentPositionImpactPoolAmountKey, 0);
                MarketEventUtils.emitLentPositionImpactPoolAmountUpdated(eventEmitter, market, cache.poolAmount.toInt256(), 0);

                cache.nextValue = dataStore.incrementUint(Keys.positionImpactPoolAmountKey(market), cache.excessAmount);
                MarketEventUtils.emitPositionImpactPoolAmountUpdated(eventEmitter, market, cache.excessAmount.toInt256(), cache.nextValue);
            } else {
                cache.nextValue = dataStore.decrementUint(cache.lentPositionImpactPoolAmountKey, cache.deltaMagnitude);
                MarketEventUtils.emitLentPositionImpactPoolAmountUpdated(eventEmitter, market, delta, cache.nextValue);
            }
        }
    }
