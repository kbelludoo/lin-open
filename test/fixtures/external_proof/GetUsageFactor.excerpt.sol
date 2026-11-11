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
