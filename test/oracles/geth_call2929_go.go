// Independent Go oracle for go-ethereum gasCallEIP2929.
// Mirrors pinned v1.16.9: cold 2500 before EIP-150 63/64, then add-back.
// Cmem and CallStipend omitted. Not linked into the LIN compiler TCB.
// Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	warm      = 100
	surcharge = 2500
	valueGas  = 9000
	newAcct   = 25000
)

func okNonneg(v int64) bool { return v >= 0 }
func okFlag(v int64) bool   { return v == 0 || v == 1 }

func linSurcharge(isCold int64) int64 {
	if !okFlag(isCold) {
		return 0
	}
	if isCold == 1 {
		return surcharge
	}
	return 0
}

func linExtra(transfers, newA, memoryGas int64) int64 {
	if !okFlag(transfers) || !okFlag(newA) || !okNonneg(memoryGas) {
		return 0
	}
	g := memoryGas
	if transfers == 1 {
		s := g + valueGas
		if uint64(s) < uint64(g) {
			return 0
		}
		g = s
		if newA == 1 {
			s2 := g + newAcct
			if uint64(s2) < uint64(g) {
				return 0
			}
			g = s2
		}
	}
	return g
}

func linForward(available, base, requested int64) int64 {
	if !okNonneg(available) || !okNonneg(base) || !okNonneg(requested) {
		return 0
	}
	if uint64(available) < uint64(base) {
		return 0
	}
	left := available - base
	cap := left - (left / 64)
	if requested < cap {
		return requested
	}
	return cap
}

func linOk(available, requested, memoryGas, transfers, newA, isCold int64) bool {
	if !okNonneg(available) || !okNonneg(requested) || !okNonneg(memoryGas) {
		return false
	}
	if !okFlag(transfers) || !okFlag(newA) || !okFlag(isCold) {
		return false
	}
	cold := linSurcharge(isCold)
	if uint64(available) < uint64(cold) {
		return false
	}
	avail2 := available - cold
	ex := linExtra(transfers, newA, memoryGas)
	return uint64(avail2) >= uint64(ex)
}

func linDynamic(available, requested, memoryGas, transfers, newA, isCold int64) int64 {
	if !linOk(available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	cold := linSurcharge(isCold)
	avail2 := available - cold
	ex := linExtra(transfers, newA, memoryGas)
	f := linForward(avail2, ex, requested)
	s := ex + f
	if uint64(s) < uint64(ex) {
		return 0
	}
	out := s + cold
	if uint64(out) < uint64(s) {
		return 0
	}
	return out
}

func linTotal(available, requested, memoryGas, transfers, newA, isCold int64) int64 {
	if !linOk(available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	d := linDynamic(available, requested, memoryGas, transfers, newA, isCold)
	s := warm + d
	if uint64(s) < uint64(d) {
		return 0
	}
	return s
}

func selftest() int {
	if linDynamic(64000, 1000000, 0, 0, 0, 0) != 63000 {
		return 1
	}
	if linDynamic(64000, 1000000, 0, 0, 0, 1) != 63040 {
		return 2
	}
	if linTotal(64000, 1000, 0, 0, 0, 1) != 3600 {
		return 3
	}
	if linDynamic(100000, 1000000, 0, 1, 1, 1) != 99008 {
		return 4
	}
	if linDynamic(2499, 0, 0, 0, 0, 1) != 0 {
		return 5
	}
	return 0
}

func ai(i int) int64 {
	n, _ := strconv.ParseInt(os.Args[i], 10, 64)
	return n
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_call2929_go selftest|dynamic a r m x n c|total a r m x n c")
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
	if len(os.Args) < 8 {
		os.Exit(2)
	}
	switch os.Args[1] {
	case "dynamic":
		fmt.Println(linDynamic(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	case "total":
		fmt.Println(linTotal(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	default:
		os.Exit(2)
	}
}
