    function toFactor(uint256 value, uint256 divisor, bool roundUpMagnitude) internal pure returns (uint256) {
        if (value == 0) { return 0; }

        if (roundUpMagnitude) {
            return Math.mulDiv(value, FLOAT_PRECISION, divisor, Math.Rounding.Up);
        }

        return Math.mulDiv(value, FLOAT_PRECISION, divisor);
    }

    function toFactor(uint256 value, uint256 divisor) internal pure returns (uint256) {
        return toFactor(value, divisor, false);
    }
