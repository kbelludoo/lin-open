// SPDX-License-Identifier: GPL-2.0-or-later
// Excerpt of gmx-io/gmx-synthetics contracts/utils/Calc.sol
// commit a85ea3491c19c93bb4b5a002d9b358fb769b7849
// function boundMagnitude (internal pure)
// License of Calc.sol in-tree is BUSL-1.1; Change Date 2026-08-31 elapsed.

    // this method assumes that min is less than max
    function boundMagnitude(int256 value, uint256 min, uint256 max) internal pure returns (int256) {
        uint256 magnitude = value.abs();

        if (magnitude < min) {
            magnitude = min;
        }

        if (magnitude > max) {
            magnitude = max;
        }

        int256 sign = value == 0 ? int256(1) : value / value.abs().toInt256();

        return magnitude.toInt256() * sign;
    }
