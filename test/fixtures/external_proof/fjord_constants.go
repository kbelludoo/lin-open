	fjordDivisor   = big.NewInt(1_000_000_000_000)
	sixteen        = big.NewInt(16)

	L1CostIntercept  = big.NewInt(-42_585_600)
	L1CostFastlzCoef = big.NewInt(836_500)

	MinTransactionSize       = big.NewInt(100)
	MinTransactionSizeScaled = new(big.Int).Mul(MinTransactionSize, big.NewInt(1e6))
