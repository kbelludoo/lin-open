// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: pool amount uses applyDeltaToUint (reject a negative next
// uint). Swap virtual inventory, called afterwards, uses applyBoundedDeltaToUint
// (floor at 0). This kernel clones only the swap-inventory update.

    function applyDeltaToPoolAmount(
        DataStore dataStore,
        EventEmitter eventEmitter,
        Market.Props memory market,
        address token,
        int256 delta
    ) internal returns (uint256) {
        uint256 nextValue = dataStore.applyDeltaToUint(
            Keys.poolAmountKey(market.marketToken, token),
            delta,
            "Invalid state, negative poolAmount"
        );

        applyDeltaToVirtualInventoryForSwaps(
            dataStore,
            eventEmitter,
            market,
            token,
            delta
        );

        MarketEventUtils.emitPoolAmountUpdated(eventEmitter, market.marketToken, token, delta, nextValue);

        return nextValue;
    }
