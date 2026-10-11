// makeSelfdestructGasFn can create the selfdestruct dynamic gas function for EIP-2929 and EIP-3529
func makeSelfdestructGasFn(refundsEnabled bool) gasFunc {
	gasFunc := func(evm *EVM, contract *Contract, stack *Stack, mem *Memory, memorySize uint64) (uint64, error) {
		var (
			gas     uint64
			address = common.Address(stack.peek().Bytes20())
		)
		if !evm.StateDB.AddressInAccessList(address) {
			// If the caller cannot afford the cost, this change will be rolled back
			evm.StateDB.AddAddressToAccessList(address)
			gas = params.ColdAccountAccessCostEIP2929
		}
		// if empty and transfers value
		if evm.StateDB.Empty(address) && evm.StateDB.GetBalance(contract.Address()).Sign() != 0 {
			gas += params.CreateBySelfdestructGas
		}
		if refundsEnabled && !evm.StateDB.HasSelfDestructed(contract.Address()) {
			evm.StateDB.AddRefund(params.SelfdestructRefundGas)
		}
		return gas, nil
	}
	return gasFunc
}
