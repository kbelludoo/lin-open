// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Scalar kernel only. Not the full MarketUtils library.
// Unsigned collateral sum: applyDeltaToUint rejects a negative next uint,
// then ALWAYS checks nextValue > maxCollateralSum (including on decrease).

    function applyDeltaToCollateralSum(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address market,
        address collateralToken,
        bool isLong,
        int256 delta
    ) internal returns (uint256) {
        uint256 nextValue = dataStore.applyDeltaToUint(
            Keys.collateralSumKey(market, collateralToken, isLong),
            delta,
            "Invalid state: negative collateralSum"
        );

        uint256 maxValue = dataStore.getUint(Keys.maxCollateralSumKey(market, collateralToken, isLong));
        if (nextValue > maxValue) {
            revert Errors.MaxCollateralSumExceeded(nextValue, maxValue);
        }

        MarketEventUtils.emitCollateralSumUpdated(eventEmitter, market, collateralToken, isLong, delta, nextValue);

        return nextValue;
    }
