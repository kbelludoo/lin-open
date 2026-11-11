    function getPendingPositionImpactPoolDistributionAmount(
        DataStore dataStore,
        address market
    ) internal view returns (uint256, uint256) {
        uint256 positionImpactPoolAmount = getPositionImpactPoolAmount(dataStore, market);
        if (positionImpactPoolAmount == 0) { return (0, positionImpactPoolAmount); }

        uint256 distributionRate = dataStore.getUint(Keys.positionImpactPoolDistributionRateKey(market));
        if (distributionRate == 0) { return (0, positionImpactPoolAmount); }

        uint256 minPositionImpactPoolAmount = dataStore.getUint(Keys.minPositionImpactPoolAmountKey(market));
        if (positionImpactPoolAmount <= minPositionImpactPoolAmount) { return (0, positionImpactPoolAmount); }

        uint256 maxDistributionAmount = positionImpactPoolAmount - minPositionImpactPoolAmount;

        uint256 durationInSeconds = getSecondsSincePositionImpactPoolDistributed(dataStore, market);
        uint256 distributionAmount = Precision.applyFactor(durationInSeconds, distributionRate);

        if (distributionAmount > maxDistributionAmount) {
            distributionAmount = maxDistributionAmount;
        }

        return (distributionAmount, positionImpactPoolAmount - distributionAmount);
    }
