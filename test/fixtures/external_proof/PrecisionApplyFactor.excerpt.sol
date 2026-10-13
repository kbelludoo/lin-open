// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt only. Upstream: gmx-io/gmx-synthetics
//   contracts/utils/Precision.sol
//   commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
//   git blob 047143722beaf6adceac3fc2ef1817f054dfe00a
// BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later.
// LIN clone uses FLOAT prime = 1e6. This excerpt pins FLOAT_PRECISION = 10 ** 30.
// applyExponentFactor identity when exponentFactor == FLOAT_PRECISION is the
// skip used by the LIN clone; the PRBMath pow path is not claimed.

    uint256 public constant FLOAT_PRECISION = 10 ** 30;
    uint256 public constant FLOAT_PRECISION_SQRT = 10 ** 15;

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
        // `PRBMathUD60x18.pow` doesn't work for `x` less than one
        if (floatValue < FLOAT_PRECISION) {
            return 0;
        }

        if (exponentFactor == FLOAT_PRECISION) {
            return floatValue;
        }

        // `PRBMathUD60x18.pow` accepts 2 fixed point numbers 60x18
        // we need to convert float (30 decimals) to 60x18 (18 decimals) and then back to 30 decimals
        uint256 weiValue = PRBMathUD60x18.pow(
            floatToWei(floatValue),
            floatToWei(exponentFactor)
        );

        return weiToFloat(weiValue);
    }
