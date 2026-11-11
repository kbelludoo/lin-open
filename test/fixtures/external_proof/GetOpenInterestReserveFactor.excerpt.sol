    function getOpenInterestReserveFactor(DataStore dataStore, address market, bool isLong) internal view returns (uint256) {
        return dataStore.getUint(Keys.openInterestReserveFactorKey(market, isLong));
    }
