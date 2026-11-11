// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: position virtual inventory is a SINGLE signed int
// (applyDeltaToInt), not the unsigned long-token/short-token pair used by swaps.

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
