// Copyright 2015 The go-ethereum Authors
// This file is part of the go-ethereum library.
//
// The go-ethereum library is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// The go-ethereum library is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with the go-ethereum library. If not, see <http://www.gnu.org/licenses/>.

package params

// Excerpt of gas constants used by IntrinsicGas. Full file is upstream params/protocol_params.go
const (
	MaxGasLimit          uint64 = 0x7fffffffffffffff // Maximum the gas limit (2^63-1).
	MaxTxGas uint64 = 1 << 24 // Maximum transaction gas limit after eip-7825 (16,777,216).
	CallNewAccountGas     uint64 = 25000 // Paid for CALL when the destination address didn't exist prior.
	TxGas                 uint64 = 21000 // Per transaction not creating a contract. NOTE: Not payable on data of calls between transactions.
	TxGasContractCreation uint64 = 53000 // Per transaction that creates a contract. NOTE: Not payable on data of calls between transactions.
	TxDataZeroGas         uint64 = 4     // Per byte of data attached to a transaction that equals zero. NOTE: Not payable on data of calls between transactions.
	InitCodeWordGas  uint64 = 2  // Once per word of the init code when creating a contract.
	TxDataNonZeroGasFrontier  uint64 = 68    // Per byte of data attached to a transaction that is not equal to zero. NOTE: Not payable on data of calls between transactions.
	TxDataNonZeroGasEIP2028   uint64 = 16    // Per byte of non zero data attached to a transaction after EIP 2028 (part in Istanbul)
	TxAccessListAddressGas    uint64 = 2400  // Per address specified in EIP 2930 access list
	TxAccessListStorageKeyGas uint64 = 1900  // Per storage key specified in EIP 2930 access list
)

