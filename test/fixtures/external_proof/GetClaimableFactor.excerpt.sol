    function _getClaimableFactor(
        DataStore dataStore,
        address market,
        address token,
        uint256 timeKey,
        address account
    ) internal view returns (uint256) {
        uint256 claimableFactorForTime = dataStore.getUint(Keys.claimableCollateralFactorKey(market, token, timeKey));
        uint256 claimableFactorForAccount = dataStore.getUint(Keys.claimableCollateralFactorKey(market, token, timeKey, account));
        uint256 claimableFactor = claimableFactorForTime > claimableFactorForAccount
            ? claimableFactorForTime
            : claimableFactorForAccount;

        // if the divisor is changed the timeDiff calculation would no longer be accurate
        uint256 divisor = dataStore.getUint(Keys.CLAIMABLE_COLLATERAL_TIME_DIVISOR);

        uint256 claimableReductionFactor = dataStore.getUint(Keys.claimableCollateralReductionFactorKey(market, token, timeKey, account));
        uint256 timeDiff = Chain.currentTimestamp() - timeKey * divisor;
        uint256 claimableCollateralDelay = dataStore.getUint(Keys.CLAIMABLE_COLLATERAL_DELAY);

        if (claimableFactor == 0 && claimableReductionFactor == 0 && timeDiff > claimableCollateralDelay) {
            claimableFactor = Precision.FLOAT_PRECISION;
        }

        if (claimableFactor > claimableReductionFactor) {
            claimableFactor -= claimableReductionFactor;
        } else {
            claimableFactor = 0;
        }

        return claimableFactor;
    }
