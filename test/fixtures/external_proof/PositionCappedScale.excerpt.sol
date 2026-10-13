// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/position/PositionUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later
// Trader-scale after pool getCappedPnl only. Uncapped pickPriceForPnl omitted.

pragma solidity ^0.8.0;

library PositionCappedScaleExcerpt {
    function scaleAfterPoolCap() internal view {
            cache.cappedPoolPnl = MarketUtils.getCappedPnl(
                dataStore,
                market.marketToken,
                position.isLong(),
                cache.poolPnl,
                cache.poolTokenUsd,
                Keys.MAX_PNL_FACTOR_FOR_TRADERS
            );

            if (cache.cappedPoolPnl != cache.poolPnl && cache.cappedPoolPnl > 0 && cache.poolPnl > 0) {
                cache.totalPositionPnl = Precision.mulDiv(cache.totalPositionPnl.toUint256(), cache.cappedPoolPnl, cache.poolPnl.toUint256());
            }
    }
}
