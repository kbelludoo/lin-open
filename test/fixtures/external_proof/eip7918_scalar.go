// Pointer-free Go subset of EIP-7918 scaled excess.
// Eligible for src/lin_from_go.lin (no pointers, selectors, slices, or heap).
// Geth calcExcessBlobGas(*types.Header) is REJ_GO_POINTER / REJ_GO_SELECTOR.
package eip7918scalar

func ScaledExcess(used uint64, max uint64, target uint64) uint64 {
	if max == 0 {
		return 0
	}
	return used * (max - target) / max
}

func CancunExcess(parentExcess uint64, parentUsed uint64, targetGas uint64) uint64 {
	if parentExcess > ^uint64(0)-parentUsed {
		return 0
	}
	s := parentExcess + parentUsed
	if s < targetGas {
		return 0
	}
	return s - targetGas
}
