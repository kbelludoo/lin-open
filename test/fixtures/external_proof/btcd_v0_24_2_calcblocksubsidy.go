func CalcBlockSubsidy(height int32, chainParams *chaincfg.Params) int64 {
	if chainParams.SubsidyReductionInterval == 0 {
		return baseSubsidy
	}

	// Equivalent to: baseSubsidy / 2^(height/subsidyHalvingInterval)
	return baseSubsidy >> uint(height/chainParams.SubsidyReductionInterval)
}
