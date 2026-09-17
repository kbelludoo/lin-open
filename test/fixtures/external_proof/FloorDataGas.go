// FloorDataGas computes the minimum gas required for a transaction based on its data tokens (EIP-7623).
func FloorDataGas(data []byte) (uint64, error) {
	var (
		z      = uint64(bytes.Count(data, []byte{0}))
		nz     = uint64(len(data)) - z
		tokens = nz*params.TxTokenPerNonZeroByte + z
	)
	// Check for overflow
	if (math.MaxUint64-params.TxGas)/params.TxCostFloorPerToken < tokens {
		return 0, ErrGasUintOverflow
	}
	// Minimum gas required for a transaction based on its data tokens (EIP-7623).
	return params.TxGas + tokens*params.TxCostFloorPerToken, nil
}

