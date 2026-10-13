// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics @ a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later
// Pinned for LIN clone-lin external proof. Not a full contract.
    // @dev apply a delta to the swap impact pool
    // @param dataStore DataStore
    // @param eventEmitter EventEmitter
    // @param market the market to apply to
    // @param token the token to apply to
    // @param delta the delta amount
    function applyDeltaToSwapImpactPool(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address market,
        address token,
        int256 delta
    ) internal returns (uint256) {
        uint256 nextValue = dataStore.applyBoundedDeltaToUint(
            Keys.swapImpactPoolAmountKey(market, token),
            delta
        );

        MarketEventUtils.emitSwapImpactPoolAmountUpdated(eventEmitter, market, token, delta, nextValue);

        return nextValue;
    }
