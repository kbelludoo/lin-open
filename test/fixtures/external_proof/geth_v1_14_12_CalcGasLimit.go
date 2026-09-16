// Copyright 2015 The go-ethereum Authors
// This file is part of the go-ethereum library.
// Licensed under the GNU Lesser General Public License v3.0.
//
// Pinned excerpt of ethereum/go-ethereum v1.14.12
//   tag commit 293a300d64be3d9a1c2cc92c26fcff4089deadcd
//   path  core/block_validator.go  (CalcGasLimit only)
// Full file sha256 d191d2a0f8b5f32cfc8f3c57f71a9859b3bba43572d187c85e450fc63ce0f8bd
// git blob     59783a040730e0be0e273bb24ec3ea4d59fcaef3
//
// This excerpt is provenance for the published algorithm, not a Geth build.

func CalcGasLimit(parentGasLimit, desiredLimit uint64) uint64 {
	delta := parentGasLimit/params.GasLimitBoundDivisor - 1
	limit := parentGasLimit
	if desiredLimit < params.MinGasLimit {
		desiredLimit = params.MinGasLimit
	}
	// If we're outside our allowed gas range, we try to hone towards them
	if limit < desiredLimit {
		limit = parentGasLimit + delta
		if limit > desiredLimit {
			limit = desiredLimit
		}
		return limit
	}
	if limit > desiredLimit {
		limit = parentGasLimit - delta
		if limit < desiredLimit {
			limit = desiredLimit
		}
	}
	return limit
}
