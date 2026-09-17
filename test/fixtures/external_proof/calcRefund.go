// calcRefund computes refund counter, capped to a refund quotient.
func (st *stateTransition) calcRefund() uint64 {
	var refund uint64
	if !st.evm.ChainConfig().IsLondon(st.evm.Context.BlockNumber) {
		// Before EIP-3529: refunds were capped to gasUsed / 2
		refund = st.gasUsed() / params.RefundQuotient
	} else {
		// After EIP-3529: refunds are capped to gasUsed / 5
		refund = st.gasUsed() / params.RefundQuotientEIP3529
	}
	if refund > st.state.GetRefund() {
		refund = st.state.GetRefund()
	}
	if st.evm.Config.Tracer != nil && st.evm.Config.Tracer.OnGasChange != nil && refund > 0 {
		st.evm.Config.Tracer.OnGasChange(st.gasRemaining, st.gasRemaining+refund, tracing.GasChangeTxRefunds)
	}
	return refund
}
