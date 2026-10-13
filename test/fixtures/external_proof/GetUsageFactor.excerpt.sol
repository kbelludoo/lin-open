// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol getUsageFactor
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// This commit's getUsageFactor is reserveUsd / applyFactor(poolUsd, openInterestReserveFactor).
// It is not the older max(openInterestUsage, reserveUsage) form.

    function getUsageFactor(
        DataStore dataStore,
        Market.Props memory market,
        bool isLong,
        uint256 reservedUsd,
        uint256 poolUsd
    ) internal view returns (uint256) {
        uint256 reserveFactor = getOpenInterestReserveFactor(dataStore, market.marketToken, isLong);
        uint256 maxReservedUsd = Precision.applyFactor(poolUsd, reserveFactor);
        uint256 reserveUsageFactor = Precision.toFactor(reservedUsd, maxReservedUsd);

        return reserveUsageFactor;
    }
