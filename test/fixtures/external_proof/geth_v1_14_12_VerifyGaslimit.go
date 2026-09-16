// Copyright 2021 The go-ethereum Authors
// This file is part of the go-ethereum library.
// Licensed under the GNU Lesser General Public License v3.0.
//
// Pinned excerpt of ethereum/go-ethereum v1.14.12
//   tag commit 293a300d64be3d9a1c2cc92c26fcff4089deadcd
//   path  consensus/misc/gaslimit.go  (VerifyGaslimit only)
// Full file sha256 27c36df89ad62c42ed0f3aca81c976363a1397f940c009bf12363f55368f6666
// git blob     dfcabd9a802c4341dbc25ba96d76b4ccc6e550b5

func VerifyGaslimit(parentGasLimit, headerGasLimit uint64) error {
	diff := int64(parentGasLimit) - int64(headerGasLimit)
	if diff < 0 {
		diff *= -1
	}
	limit := parentGasLimit / params.GasLimitBoundDivisor
	if uint64(diff) >= limit {
		return fmt.Errorf("invalid gas limit: have %d, want %d +-= %d", headerGasLimit, parentGasLimit, limit-1)
	}
	if headerGasLimit < params.MinGasLimit {
		return fmt.Errorf("invalid gas limit below %d", params.MinGasLimit)
	}
	return nil
}
