func newL1CostFuncBedrockHelper(l1BaseFee, overhead, scalar *big.Int, isRegolith bool) l1CostFunc {
	return func(rollupCostData RollupCostData) (fee, gasUsed *big.Int) {
		if rollupCostData == (RollupCostData{}) {
			return nil, nil // Do not charge if there is no rollup cost-data (e.g. RPC call or deposit)
		}
		gas := rollupCostData.Zeroes * params.TxDataZeroGas
		if isRegolith {
			gas += rollupCostData.Ones * params.TxDataNonZeroGasEIP2028
		} else {
			gas += (rollupCostData.Ones + 68) * params.TxDataNonZeroGasEIP2028
		}
		gasWithOverhead := new(big.Int).SetUint64(gas)
		gasWithOverhead.Add(gasWithOverhead, overhead)
		l1Cost := l1CostHelper(gasWithOverhead, l1BaseFee, scalar)
		return l1Cost, gasWithOverhead
	}
}
