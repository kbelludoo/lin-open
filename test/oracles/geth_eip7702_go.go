// Independent Go oracle for go-ethereum makeCallVariantGasCallEIP7702.
// Mirrors pinned v1.16.9: Berlin 2500 + ParseDelegation 100/2600 before 63/64.
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
	cold               = 2600
	surcharge          = 2500
	valueGas           = 9000
	newAcct            = 25000
	designatorLen      = 23
)

func okNonneg(v int64) bool { return v >= 0 }
func okFlag(v int64) bool   { return v == 0 || v == 1 }
func okKind(k int64) bool   { return k >= 0 && k <= 3 }

func linParseOk(codeLen, prefixOk int64) int64 {
	if !okNonneg(codeLen) || !okFlag(prefixOk) {
		return 0
	}
	if codeLen == designatorLen && prefixOk == 1 {
		return 1
	}
	return 0
}

func linPrecharge(addrCold, isDel, targetCold int64) int64 {
	if !okFlag(addrCold) || !okFlag(isDel) || !okFlag(targetCold) {
		return 0
	}
	p := int64(0)
	if addrCold == 1 {
		p = surcharge
	}
	if isDel == 0 {
		return p
	}
	if targetCold == 1 {
		return p + cold
	}
	return p + warm
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
			return g + valueGas
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

func linOk(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold int64) bool {
	if !okKind(kind) || !okNonneg(available) || !okNonneg(requested) || !okNonneg(memoryGas) {
		return false
	}
	if !okFlag(transfers) || !okFlag(newA) || !okFlag(addrCold) || !okFlag(isDel) || !okFlag(targetCold) {
		return false
	}
	pre := linPrecharge(addrCold, isDel, targetCold)
	if uint64(available) < uint64(pre) {
		return false
	}
	return uint64(available-pre) >= uint64(linExtra(kind, transfers, newA, memoryGas))
}

func linDynamic(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold int64) int64 {
	if !linOk(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold) {
		return 0
	}
	pre := linPrecharge(addrCold, isDel, targetCold)
	avail2 := available - pre
	ex := linExtra(kind, transfers, newA, memoryGas)
	f := linForward(avail2, ex, requested)
	s := ex + f
	if uint64(s) < uint64(ex) {
		return 0
	}
	out := s + pre
	if uint64(out) < uint64(s) {
		return 0
	}
	return out
}

func linTotal(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold int64) int64 {
	if !linOk(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold) {
		return 0
	}
	d := linDynamic(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold)
	s := warm + d
	if uint64(s) < uint64(d) {
		return 0
	}
	return s
}

func linVs(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold int64) int64 {
	if !linOk(kind, available, requested, memoryGas, transfers, newA, addrCold, 0, 0) {
		return 0
	}
	if !linOk(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold) {
		return 0
	}
	return linDynamic(kind, available, requested, memoryGas, transfers, newA, addrCold, isDel, targetCold) -
		linDynamic(kind, available, requested, memoryGas, transfers, newA, addrCold, 0, 0)
}

func selftest() int {
	if linParseOk(23, 1) != 1 || linParseOk(23, 0) != 0 {
		return 1
	}
	if linDynamic(0, 64000, 1000000, 0, 0, 0, 0, 1, 0) != 63002 {
		return 2
	}
	if linVs(0, 64000, 1000000, 0, 0, 0, 0, 1, 1) != 41 {
		return 3
	}
	if linDynamic(0, 100000, 1000000, 0, 1, 1, 0, 1, 1) != 99010 {
		return 4
	}
	if linDynamic(0, 2599, 0, 0, 0, 0, 0, 1, 1) != 0 {
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
		fmt.Fprintln(os.Stderr, "usage: geth_eip7702_go selftest|dynamic k a r m x n c d t|total ...|vs ...")
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
	if len(os.Args) < 11 {
		os.Exit(2)
	}
	switch os.Args[1] {
	case "dynamic":
		fmt.Println(linDynamic(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8), ai(9), ai(10)))
	case "total":
		fmt.Println(linTotal(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8), ai(9), ai(10)))
	case "vs":
		fmt.Println(linVs(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8), ai(9), ai(10)))
	default:
		os.Exit(2)
	}
}
