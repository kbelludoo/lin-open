// Independent Go oracle for go-ethereum callGas (EIP-150 63/64).
// Mirrors pinned v1.16.9 uint64 wrap; *uint256.Int is (cost, costHi).
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

func gethCallGas(eip150 bool, available, base, cost, costHi uint64) (uint64, bool) {
	if eip150 {
		available = available - base
		gas := available - available/64
		if costHi != 0 || gas < cost {
			return gas, true
		}
	}
	if costHi != 0 {
		return 0, false
	}
	return cost, true
}

func linCallGas(eip150, available, base, cost, costHi int64) int64 {
	if eip150 < 0 || available < 0 || base < 0 || cost < 0 || costHi < 0 {
		return 0
	}
	if eip150 != 0 {
		if uint64(available) < uint64(base) {
			return 0
		}
		rem := available - base
		gas := rem - rem/64
		if costHi != 0 {
			return gas
		}
		if uint64(gas) < uint64(cost) {
			return gas
		}
		return cost
	}
	if costHi != 0 {
		return 0
	}
	return cost
}

func selftest() int {
	v, ok := gethCallGas(true, 64000, 0, 64000, 0)
	if !ok || v != 63000 {
		return 1
	}
	v, ok = gethCallGas(true, 64000, 700, 1000, 0)
	if !ok || v != 1000 {
		return 2
	}
	v, ok = gethCallGas(false, 1000, 0, 1000, 1)
	if ok {
		return 3
	}
	v, ok = gethCallGas(true, 10, 20, 5, 0)
	if !ok || v != 5 {
		return 4
	}
	if linCallGas(1, 64000, 0, 64000, 0) != 63000 {
		return 5
	}
	if linCallGas(1, 10, 20, 5, 0) != 0 {
		return 6
	}
	if linCallGas(1, 21000, 0, 21000, 0) != 20672 {
		return 7
	}
	if linCallGas(1, 1000, 0, 0, 1) != 985 {
		return 8
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_callgas_go selftest|call|geth-call eip av base cost hi")
		os.Exit(2)
	}
	if os.Args[1] == "selftest" {
		if rc := selftest(); rc != 0 {
			fmt.Printf("FAIL %d\n", rc)
			os.Exit(1)
		}
		fmt.Println("PASS")
		return
	}
	if len(os.Args) < 7 {
		os.Exit(2)
	}
	eip, _ := strconv.ParseInt(os.Args[2], 10, 64)
	av, _ := strconv.ParseUint(os.Args[3], 10, 64)
	base, _ := strconv.ParseUint(os.Args[4], 10, 64)
	cost, _ := strconv.ParseUint(os.Args[5], 10, 64)
	hi, _ := strconv.ParseUint(os.Args[6], 10, 64)
	if os.Args[1] == "call" {
		fmt.Println(linCallGas(eip, int64(av), int64(base), int64(cost), int64(hi)))
		return
	}
	if os.Args[1] == "geth-call" {
		v, ok := gethCallGas(eip != 0, av, base, cost, hi)
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
		return
	}
	os.Exit(2)
}
