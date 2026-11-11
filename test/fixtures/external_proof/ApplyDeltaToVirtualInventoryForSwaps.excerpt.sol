// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Scalar kernel only. Not the full MarketUtils library.
// Unsigned long-token / short-token virtual inventory pair for swaps.
// applyBoundedDeltaToUint floors at 0; missing virtualMarketId returns (false, 0)
// before getIsLongToken, so an unexpected token does not revert on that path.

    function getVirtualInventoryForSwaps(DataStore dataStore, address market) internal view returns (bool, uint256, uint256) {
        bytes32 virtualMarketId = dataStore.getBytes32(Keys.virtualMarketIdKey(market));
        if (virtualMarketId == bytes32(0)) {
            return (false, 0, 0);
        }

        return (
            true,
            dataStore.getUint(Keys.virtualInventoryForSwapsKey(virtualMarketId, true)),
            dataStore.getUint(Keys.virtualInventoryForSwapsKey(virtualMarketId, false))
        );
    }

    function getIsLongToken(Market.Props memory market, address token) internal pure returns (bool) {
        if (token != market.longToken && token != market.shortToken) {
            revert Errors.UnexpectedTokenForVirtualInventory(token, market.marketToken);
        }

        return token == market.longToken;
    }

    function applyDeltaToVirtualInventoryForSwaps(
        DataStore dataStore,
        EventEmitter eventEmitter,
        Market.Props memory market,
        address token,
        int256 delta
    ) internal returns (bool, uint256) {
        bytes32 virtualMarketId = dataStore.getBytes32(Keys.virtualMarketIdKey(market.marketToken));
        if (virtualMarketId == bytes32(0)) {
            return (false, 0);
        }

        bool isLongToken = getIsLongToken(market, token);

        uint256 nextValue = dataStore.applyBoundedDeltaToUint(
            Keys.virtualInventoryForSwapsKey(virtualMarketId, isLongToken),
            delta
        );

        MarketEventUtils.emitVirtualSwapInventoryUpdated(eventEmitter, market.marketToken, isLongToken, virtualMarketId, delta, nextValue);

        return (true, nextValue);
    }
