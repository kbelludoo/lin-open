func bedrockCalldataGasUsed(costData RollupCostData) (calldataGasUsed *big.Int) {
	calldataGas := (costData.Zeroes * params.TxDataZeroGas) + (costData.Ones * params.TxDataNonZeroGasEIP2028)
	return new(big.Int).SetUint64(calldataGas)
}
