var (
	gasCallEIP7702         = makeCallVariantGasCallEIP7702(gasCall)
	gasDelegateCallEIP7702 = makeCallVariantGasCallEIP7702(gasDelegateCall)
	gasStaticCallEIP7702   = makeCallVariantGasCallEIP7702(gasStaticCall)
	gasCallCodeEIP7702     = makeCallVariantGasCallEIP7702(gasCallCode)
)

func makeCallVariantGasCallEIP7702(oldCalculator gasFunc) gasFunc {
	return func(evm *EVM, contract *Contract, stack *Stack, mem *Memory, memorySize uint64) (uint64, error) {
		var (
			total uint64 // total dynamic gas used
			addr  = common.Address(stack.Back(1).Bytes20())
		)

		// Check slot presence in the access list
		if !evm.StateDB.AddressInAccessList(addr) {
			evm.StateDB.AddAddressToAccessList(addr)
			// The WarmStorageReadCostEIP2929 (100) is already deducted in the form of a constant cost, so
			// the cost to charge for cold access, if any, is Cold - Warm
			coldCost := params.ColdAccountAccessCostEIP2929 - params.WarmStorageReadCostEIP2929
			// Charge the remaining difference here already, to correctly calculate available
			// gas for call
			if !contract.UseGas(coldCost, evm.Config.Tracer, tracing.GasChangeCallStorageColdAccess) {
				return 0, ErrOutOfGas
			}
			total += coldCost
		}

		// Check if code is a delegation and if so, charge for resolution.
		if target, ok := types.ParseDelegation(evm.StateDB.GetCode(addr)); ok {
			var cost uint64
			if evm.StateDB.AddressInAccessList(target) {
				cost = params.WarmStorageReadCostEIP2929
			} else {
				evm.StateDB.AddAddressToAccessList(target)
				cost = params.ColdAccountAccessCostEIP2929
			}
			if !contract.UseGas(cost, evm.Config.Tracer, tracing.GasChangeCallStorageColdAccess) {
				return 0, ErrOutOfGas
			}
			total += cost
		}

		// Now call the old calculator, which takes into account
		// - create new account
		// - transfer value
		// - memory expansion
		// - 63/64ths rule
		old, err := oldCalculator(evm, contract, stack, mem, memorySize)
		if err != nil {
			return old, err
		}

		// Temporarily add the gas charge back to the contract and return value. By
		// adding it to the return, it will be charged outside of this function, as
		// part of the dynamic gas. This will ensure it is correctly reported to
		// tracers.
		contract.Gas += total

		var overflow bool
		if total, overflow = math.SafeAdd(old, total); overflow {
			return 0, ErrGasUintOverflow
		}
		return total, nil
	}
}
