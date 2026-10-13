// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/utils/Precision.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// blob 047143722beaf6adceac3fc2ef1817f054dfe00a

    uint256 public constant FLOAT_PRECISION = 10 ** 30;

    function applyFactor(uint256 value, uint256 factor) internal pure returns (uint256) {
        return mulDiv(value, factor, FLOAT_PRECISION);
    }

    function toFactor(uint256 value, uint256 divisor) internal pure returns (uint256) {
        return toFactor(value, divisor, false);
    }

    function applyExponentFactor(
        uint256 floatValue,
        uint256 exponentFactor
    ) internal pure returns (uint256) {
        if (floatValue < FLOAT_PRECISION) {
            return 0;
        }
        if (exponentFactor == FLOAT_PRECISION) {
            return floatValue;
        }
        uint256 weiValue = PRBMathUD60x18.pow(
            floatToWei(floatValue),
            floatToWei(exponentFactor)
        );
        return weiToFloat(weiValue);
    }
