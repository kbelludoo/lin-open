// Independent Go oracle for FloorDataGas (EIP-7623).
// Copies the pinned Geth v1.16.9 formula with z/nz as arguments (no []byte).
// Not linked into the LIN TCB. Algorithm: LGPL-3.0 go-ethereum.
package main

import (
	"fmt"
	"math"
	"os"
	"strconv"
)

const (
	txGas               uint64 = 21000
	txTokenPerNonZero   uint64 = 4
	txCostFloorPerToken uint64 = 10
)

func floorDataGas(z, nz uint64) (uint64, bool) {
	tokens := nz*txTokenPerNonZero + z
	if (math.MaxUint64-txGas)/txCostFloorPerToken < tokens {
		return 0, false
	}
	return txGas + tokens*txCostFloorPerToken, true
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "selftest" {
		v, ok := floorDataGas(0, 0)
		if !ok || v != 21000 {
			fmt.Println("FAIL empty")
			os.Exit(1)
		}
		v, ok = floorDataGas(1, 0)
		if !ok || v != 21010 {
			fmt.Println("FAIL 1z")
			os.Exit(1)
		}
		v, ok = floorDataGas(0, 1)
		if !ok || v != 21040 {
			fmt.Println("FAIL 1nz")
			os.Exit(1)
		}
		v, ok = floorDataGas(0, 4611686018427387904)
		if !ok || v != 21000 {
			fmt.Println("FAIL wrap")
			os.Exit(1)
		}
		fmt.Println("PASS")
		return
	}
	if len(os.Args) != 3 {
		fmt.Fprintf(os.Stderr, "usage: geth_floordata_go z nz | selftest\n")
		os.Exit(2)
	}
	z, err1 := strconv.ParseUint(os.Args[1], 10, 64)
	nz, err2 := strconv.ParseUint(os.Args[2], 10, 64)
	if err1 != nil || err2 != nil {
		fmt.Fprintf(os.Stderr, "bad args\n")
		os.Exit(2)
	}
	v, ok := floorDataGas(z, nz)
	if !ok {
		fmt.Println("0")
		return
	}
	fmt.Println(v)
}
