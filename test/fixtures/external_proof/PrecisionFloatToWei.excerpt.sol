    uint256 public constant FLOAT_PRECISION = 10 ** 30;
    uint256 public constant WEI_PRECISION = 10 ** 18;
    uint256 public constant FLOAT_TO_WEI_DIVISOR = 10 ** 12;

    function floatToWei(uint256 value) internal pure returns (uint256) {
        return value / FLOAT_TO_WEI_DIVISOR;
    }
