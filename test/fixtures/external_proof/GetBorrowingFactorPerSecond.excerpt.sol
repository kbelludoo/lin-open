// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/market/MarketUtils.sol
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
//   git blob ad7a0b2b5a516ec86ce0afed89ff84ecba11038c
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// Pinned for audit of getBorrowingFactorPerSecond. Not a full dump.

    // @dev get the borrowing factor per second
    // @param dataStore DataStore
    // @param market the market to get the borrowing factor per second for
    // @param prices the prices of the market tokens
    // @param isLong whether to get the factor for the long or short side
    function getBorrowingFactorPerSecond(
        DataStore dataStore,
        Market.Props memory market,
        MarketPrices memory prices,
        bool isLong
    ) internal view returns (uint256) {
        uint256 reservedUsd = getReservedUsd(
            dataStore,
            market,
            prices,
            isLong
        );

        if (reservedUsd == 0) { return 0; }

        // check if the borrowing fee for the smaller side should be skipped
        // if skipBorrowingFeeForSmallerSide is true, and the longOpenInterest is exactly the same as the shortOpenInterest
        // then the borrowing fee would be charged for both sides, this should be very rare
        bool skipBorrowingFeeForSmallerSide = dataStore.getBool(Keys.SKIP_BORROWING_FEE_FOR_SMALLER_SIDE);
        if (skipBorrowingFeeForSmallerSide) {
            bool useOpenInterestInTokens = dataStore.getBool(Keys.USE_OPEN_INTEREST_IN_TOKENS_FOR_BALANCE);
            uint256 longOpenInterest = getOpenInterestForBalance({
                dataStore: dataStore,
                market: market,
                useOpenInterestInTokens: useOpenInterestInTokens,
                indexTokenPrice: prices.indexTokenPrice.midPrice(),
                isLong: true
            });

            uint256 shortOpenInterest = getOpenInterestForBalance({
                dataStore: dataStore,
                market: market,
                useOpenInterestInTokens: useOpenInterestInTokens,
                indexTokenPrice: prices.indexTokenPrice.midPrice(),
                isLong: false
            });

            // if getting the borrowing factor for longs and if the longOpenInterest
            // is smaller than the shortOpenInterest, then return zero
            if (isLong && longOpenInterest < shortOpenInterest) {
                return 0;
            }

            // if getting the borrowing factor for shorts and if the shortOpenInterest
            // is smaller than the longOpenInterest, then return zero
            if (!isLong && shortOpenInterest < longOpenInterest) {
                return 0;
            }
        }

        uint256 poolUsd = getPoolUsdWithoutPnl(dataStore, market, prices, isLong, false);

        if (poolUsd == 0) {
            revert Errors.UnableToGetBorrowingFactorEmptyPoolUsd();
        }

        uint256 optimalUsageFactor = getOptimalUsageFactor(dataStore, market.marketToken, isLong);

        if (optimalUsageFactor != 0) {
            return getKinkBorrowingFactor(
                dataStore,
                market,
                isLong,
                reservedUsd,
                poolUsd,
                optimalUsageFactor
            );
        }

        uint256 borrowingExponentFactor = getBorrowingExponentFactor(dataStore, market.marketToken, isLong);
        uint256 reservedUsdAfterExponent = Precision.applyExponentFactor(reservedUsd, borrowingExponentFactor);

        uint256 reservedUsdToPoolFactor = Precision.toFactor(reservedUsdAfterExponent, poolUsd);
        uint256 borrowingFactor = getBorrowingFactor(dataStore, market.marketToken, isLong);

        return Precision.applyFactor(reservedUsdToPoolFactor, borrowingFactor);
    }
