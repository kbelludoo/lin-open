// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/market/MarketUtils.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// function getFundingAmountPerSizeDelta (internal pure)

    function getFundingAmountPerSizeDelta(
        uint256 fundingUsd,
        uint256 openInterest,
        uint256 tokenPrice,
        bool roundUpMagnitude
    ) internal pure returns (uint256) {
        if (fundingUsd == 0 || openInterest == 0) { return 0; }

        uint256 fundingUsdPerSize = Precision.mulDiv(
            fundingUsd,
            Precision.FLOAT_PRECISION * Precision.FLOAT_PRECISION_SQRT,
            openInterest,
            roundUpMagnitude
        );

        if (roundUpMagnitude) {
            return Calc.roundUpDivision(fundingUsdPerSize, tokenPrice);
        } else {
            return fundingUsdPerSize / tokenPrice;
        }
    }
