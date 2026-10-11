// Independent Go oracle for go-ethereum CALLCODE/DELEGATECALL/STATICCALL EIP-2929.
// Mirrors pinned v1.16.9: shared Berlin 2500-before-63/64 wrapper; extras differ.
// Cmem and CallStipend omitted. Not linked into the LIN compiler TCB.
// Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	kindCall     int64 = 0
	kindCallCode int64 = 1
	kindDelegate int64 = 2
	kindStatic   int64 = 3
	warm               = 100
	surcharge          = 2500
	valueGas           = 9000
	newAcct            = 25000
)

func okNonneg(v int64) bool { return v >= 0 }
func okFlag(v int64) bool   { return v == 0 || v == 1 }
func okKind(k int64) bool   { return k >= 0 && k <= 3 }

func linSurcharge(isCold int64) int64 {
	if !okFlag(isCold) {
		return 0
	}
	if isCold == 1 {
		return surcharge
	}
	return 0
}

func linExtra(kind, transfers, newA, memoryGas int64) int64 {
	if !okKind(kind) || !okFlag(transfers) || !okFlag(newA) || !okNonneg(memoryGas) {
		return 0
	}
	g := memoryGas
	if kind == kindDelegate || kind == kindStatic {
		return g
	}
	if kind == kindCallCode {
		if transfers == 1 {
			s := g + valueGas
			if uint64(s) < uint64(g) {
				return 0
			}
			return s
		}
		return g
	}
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

func linOk(kind, available, requested, memoryGas, transfers, newA, isCold int64) bool {
	if !okKind(kind) || !okNonneg(available) || !okNonneg(requested) || !okNonneg(memoryGas) {
		return false
	}
	if !okFlag(transfers) || !okFlag(newA) || !okFlag(isCold) {
		return false
	}
	cold := linSurcharge(isCold)
	if uint64(available) < uint64(cold) {
		return false
	}
	return uint64(available-cold) >= uint64(linExtra(kind, transfers, newA, memoryGas))
}

func linDynamic(kind, available, requested, memoryGas, transfers, newA, isCold int64) int64 {
	if !linOk(kind, available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	cold := linSurcharge(isCold)
	avail2 := available - cold
	ex := linExtra(kind, transfers, newA, memoryGas)
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

func linTotal(kind, available, requested, memoryGas, transfers, newA, isCold int64) int64 {
	if !linOk(kind, available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	d := linDynamic(kind, available, requested, memoryGas, transfers, newA, isCold)
	s := warm + d
	if uint64(s) < uint64(d) {
		return 0
	}
	return s
}

func linVs(kind, available, requested, memoryGas, transfers, newA, isCold int64) int64 {
	if !linOk(kindCall, available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	if !linOk(kind, available, requested, memoryGas, transfers, newA, isCold) {
		return 0
	}
	return linDynamic(kindCall, available, requested, memoryGas, transfers, newA, isCold) -
		linDynamic(kind, available, requested, memoryGas, transfers, newA, isCold)
}

func selftest() int {
	if linExtra(kindCall, 1, 1, 0) != 34000 {
		return 1
	}
	if linExtra(kindCallCode, 1, 1, 0) != 9000 {
		return 2
	}
	if linDynamic(kindCallCode, 100000, 1000000, 0, 1, 1, 0) != 98579 {
		return 3
	}
	if linVs(kindCallCode, 100000, 1000000, 0, 1, 1, 0) != 390 {
		return 4
	}
	if linVs(kindStatic, 100000, 1000000, 0, 1, 1, 0) != 531 {
		return 5
	}
	if linDynamic(kindDelegate, 64000, 1000000, 0, 0, 0, 1) != 63040 {
		return 6
	}
	return 0
}

func ai(i int) int64 {
	n, _ := strconv.ParseInt(os.Args[i], 10, 64)
	return n
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_callcode2929_go selftest|dynamic k a r m x n c|total k a r m x n c|vs k a r m x n c")
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
	if len(os.Args) < 9 {
		os.Exit(2)
	}
	switch os.Args[1] {
	case "dynamic":
		fmt.Println(linDynamic(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8)))
	case "total":
		fmt.Println(linTotal(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8)))
	case "vs":
		fmt.Println(linVs(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8)))
	default:
		os.Exit(2)
	}
}
