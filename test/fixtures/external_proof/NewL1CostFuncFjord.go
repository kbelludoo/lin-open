func NewL1CostFuncFjord(l1BaseFee, l1BlobBaseFee, baseFeeScalar, blobFeeScalar *big.Int) l1CostFunc {
	return func(costData RollupCostData) (fee, calldataGasUsed *big.Int) {
		// Fjord L1 cost function:
		// l1FeeScaled = baseFeeScalar*l1BaseFee*16 + blobFeeScalar*l1BlobBaseFee
		// estimatedSize = max(minTransactionSize, intercept + fastlzCoef*fastlzSize)
		// l1Cost = estimatedSize * l1FeeScaled / 1e12

		scaledL1BaseFee := new(big.Int).Mul(baseFeeScalar, l1BaseFee)
		calldataCostPerByte := new(big.Int).Mul(scaledL1BaseFee, sixteen)
		blobCostPerByte := new(big.Int).Mul(blobFeeScalar, l1BlobBaseFee)
		l1FeeScaled := new(big.Int).Add(calldataCostPerByte, blobCostPerByte)
		estimatedSize := costData.estimatedDASizeScaled()
		l1CostScaled := new(big.Int).Mul(estimatedSize, l1FeeScaled)
		l1Cost := new(big.Int).Div(l1CostScaled, fjordDivisor)

		calldataGasUsed = new(big.Int).Mul(estimatedSize, new(big.Int).SetUint64(params.TxDataNonZeroGasEIP2028))
		calldataGasUsed.Div(calldataGasUsed, big.NewInt(1e6))

		return l1Cost, calldataGasUsed
	}
}
