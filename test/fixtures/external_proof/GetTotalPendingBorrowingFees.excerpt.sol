    function getTotalPendingBorrowingFees(
        DataStore dataStore,
        Market.Props memory market,
        MarketPrices memory prices,
        bool isLong
    ) internal view returns (uint256) {
        uint256 openInterest = getOpenInterest(
            dataStore,
            market,
            isLong
        );

        (uint256 nextCumulativeBorrowingFactor, /* uint256 delta */, ) = getNextCumulativeBorrowingFactor(
            dataStore,
            market,
            prices,
            isLong
        );

        uint256 totalBorrowing = getTotalBorrowing(dataStore, market.marketToken, isLong);

        return Precision.applyFactor(openInterest, nextCumulativeBorrowingFactor) - totalBorrowing;
    }
