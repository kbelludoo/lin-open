// gasUsed returns the amount of gas used up by the state transition.
func (st *stateTransition) gasUsed() uint64 {
	return st.initialGas - st.gasRemaining
}
