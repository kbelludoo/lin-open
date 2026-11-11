uint256 public constant FLOAT_PRECISION = 10 ** 30;
    uint256 public constant FLOAT_PRECISION_SQRT = 10 ** 15;

    uint256 public constant WEI_PRECISION = 10 ** 18;
    uint256 public constant BASIS_POINTS_DIVISOR = 10000;

    uint256 public constant FLOAT_TO_WEI_DIVISOR = 10 ** 12;

    /**
     * Applies the given factor to the given value and returns the result.
     *
     * @param value The value to apply the factor to.
     * @param factor The factor to apply.
     * @return The result of applying the factor to the value.
     */
    function mulDiv(uint256 value, uint256 numerator, uint256 denominator, bool roundUpMagnitude) internal pure returns (uint256) {
        if (roundUpMagnitude) {
            return Math.mulDiv(value, numerator, denominator, Math.Rounding.Up);
        }

        return Math.mulDiv(value, numerator, denominator);
    }
