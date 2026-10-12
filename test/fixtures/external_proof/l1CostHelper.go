func l1CostHelper(gasWithOverhead, l1BaseFee, scalar *big.Int) *big.Int {
	fee := new(big.Int).Set(gasWithOverhead)
	fee.Mul(fee, l1BaseFee).Mul(fee, scalar).Div(fee, oneMillion)
	return fee
}
