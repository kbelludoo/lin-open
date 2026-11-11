    function incrementClaimableCollateralAmount(
        DataStore dataStore,
        EventEmitter eventEmitter,
        address market,
        address token,
        address account,
        uint256 delta
    ) internal {
        uint256 divisor = dataStore.getUint(Keys.CLAIMABLE_COLLATERAL_TIME_DIVISOR);
        uint256 timeKey = Chain.currentTimestamp() / divisor;

        uint256 nextValue = dataStore.incrementUint(
            Keys.claimableCollateralAmountKey(market, token, timeKey, account),
            delta
        );

        uint256 nextPoolValue = dataStore.incrementUint(
            Keys.claimableCollateralAmountKey(market, token),
            delta
        );

        MarketEventUtils.emitClaimableCollateralUpdated(
            eventEmitter,
            market,
            token,
            timeKey,
            account,
            delta,
            nextValue,
            nextPoolValue
        );
    }
