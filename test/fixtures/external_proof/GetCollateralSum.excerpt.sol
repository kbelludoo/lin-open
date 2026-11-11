// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// Named contrast: the getter divides by divisor; applyDeltaToCollateralSum
// returns the undivided next uint.

    function getCollateralSum(DataStore dataStore, address market, address collateralToken, bool isLong, uint256 divisor) internal view returns (uint256) {
        return dataStore.getUint(Keys.collateralSumKey(market, collateralToken, isLong)) / divisor;
    }
