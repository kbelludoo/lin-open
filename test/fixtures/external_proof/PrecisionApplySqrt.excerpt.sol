// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/utils/Precision.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// blob 047143722beaf6adceac3fc2ef1817f054dfe00a

    uint256 public constant FLOAT_PRECISION = 10 ** 30;
    uint256 public constant FLOAT_PRECISION_SQRT = 10 ** 15;

    function applyFactor(uint256 value, uint256 factor) internal pure returns (uint256) {
        return mulDiv(value, factor, FLOAT_PRECISION);
    }

    function mulDiv(uint256 value, uint256 numerator, uint256 denominator, bool roundUpMagnitude) internal pure returns (uint256) {
        if (roundUpMagnitude) {
            return Math.mulDiv(value, numerator, denominator, Math.Rounding.Up);
        }

        return Math.mulDiv(value, numerator, denominator);
    }
