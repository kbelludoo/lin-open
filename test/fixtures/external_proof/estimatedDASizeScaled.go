func (cd RollupCostData) estimatedDASizeScaled() *big.Int {
	fastLzSize := new(big.Int).SetUint64(cd.FastLzSize)
	estimatedSize := new(big.Int).Add(L1CostIntercept, new(big.Int).Mul(L1CostFastlzCoef, fastLzSize))

	if estimatedSize.Cmp(MinTransactionSizeScaled) < 0 {
		estimatedSize.Set(MinTransactionSizeScaled)
	}
	return estimatedSize
}
