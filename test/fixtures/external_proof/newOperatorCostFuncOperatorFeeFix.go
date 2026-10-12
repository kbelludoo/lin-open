func newOperatorCostFuncOperatorFeeFix(operatorFeeScalar *big.Int, operatorFeeConstant *big.Int) operatorCostFunc {
	return func(gas uint64) *uint256.Int {
		fee := new(big.Int).SetUint64(gas)
		fee = fee.Mul(fee, operatorFeeScalar)
		fee = fee.Mul(fee, oneHundred)
		fee = fee.Add(fee, operatorFeeConstant)

		feeU256, overflow := uint256.FromBig(fee)
		if overflow {
			// This should never happen, as (u64.max * u32.max * 100) + u64.max fits in 103 bits
			panic("overflow in operator cost calculation")
		}

		return feeU256
	}
}
