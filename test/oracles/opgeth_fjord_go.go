// Independent Go oracle for op-geth NewL1CostFuncFjord / estimatedDASizeScaled.
// Mirrors pinned v1.101702.3 rollup_cost.go with explicit FastLZ size.
// FlzCompressLen / StateDB omitted. Not linked into the LIN compiler TCB.
// Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"math/big"
	"os"
	"strconv"
)

func okNonneg(v int64) bool { return v >= 0 }

func muldiv(a, b, d int64) int64 {
	if a < 0 || b < 0 || d <= 0 {
		return 0
	}
	prod := new(big.Int).Mul(big.NewInt(a), big.NewInt(b))
	q := new(big.Int).Div(prod, big.NewInt(d))
	if !q.IsInt64() {
		return 0
	}
	return q.Int64()
}

func est(flz int64) int64 {
	if !okNonneg(flz) {
		return 0
	}
	raw := muldiv(836500, flz, 1)
	if raw == 0 && flz != 0 {
		return 0
	}
	if uint64(raw) < 42585600 {
		return 100000000
	}
	unclamped := raw - 42585600
	if uint64(unclamped) < 100000000 {
		return 100000000
	}
	return unclamped
}

func unclamped(flz int64) int64 {
	if !okNonneg(flz) {
		return 0
	}
	raw := muldiv(836500, flz, 1)
	if raw == 0 && flz != 0 {
		return 0
	}
	if uint64(raw) < 42585600 {
		return 0
	}
	return raw - 42585600
}

func inner(bf, bb, bs, bbs int64) int64 {
	if !okNonneg(bf) || !okNonneg(bb) || !okNonneg(bs) || !okNonneg(bbs) {
		return 0
	}
	a := muldiv(bf, 16, 1)
	if a == 0 && bf != 0 {
		return 0
	}
	a2 := muldiv(a, bs, 1)
	if a2 == 0 && a != 0 && bs != 0 {
		return 0
	}
	b := muldiv(bb, bbs, 1)
	if b == 0 && bb != 0 && bbs != 0 {
		return 0
	}
	s := a2 + b
	if uint64(s) < uint64(a2) {
		return 0
	}
	return s
}

func fjoFee(flz, bf, bb, bs, bbs int64) int64 {
	e := est(flz)
	inn := inner(bf, bb, bs, bbs)
	if e == 0 {
		return 0
	}
	if inn == 0 && (bf != 0 || bb != 0) && (bs != 0 || bbs != 0) {
		return 0
	}
	return muldiv(e, inn, 1000000000000)
}

func fjoGas(flz int64) int64 {
	e := est(flz)
	if e == 0 {
		return 0
	}
	return muldiv(e, 16, 1000000)
}

func fjoEco(z, o, bf, bb, bs, bbs int64) int64 {
	if !okNonneg(z) || !okNonneg(o) {
		return 0
	}
	return muldiv(z*4+o*16, inner(bf, bb, bs, bbs), 16000000)
}

func fjoVs(flz, z, o, bf, bb, bs, bbs int64) int64 {
	full := fjoFee(flz, bf, bb, bs, bbs)
	eco := fjoEco(z, o, bf, bb, bs, bbs)
	if uint64(full) < uint64(eco) {
		return 0
	}
	return full - eco
}

func selftest() int {
	if inner(1000000000, 10000000, 2, 3) != 32030000000 {
		return 1
	}
	if fjoFee(100, 1000000000, 10000000, 2, 3) != 3203000 {
		return 2
	}
	if fjoFee(235, 2000000, 3000000, 20, 15) != 105484 {
		return 3
	}
	if fjoGas(100) != 1600 || fjoEco(0, 30, 1000000000, 10000000, 2, 3) != 960900 {
		return 4
	}
	if unclamped(31) != 0 {
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
		fmt.Fprintln(os.Stderr, "usage: opgeth_fjord_go selftest|est|unclamped|fee|gas|eco|vs")
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
	switch os.Args[1] {
	case "est":
		fmt.Println(est(ai(2)))
	case "unclamped":
		fmt.Println(unclamped(ai(2)))
	case "fee":
		fmt.Println(fjoFee(ai(2), ai(3), ai(4), ai(5), ai(6)))
	case "gas":
		fmt.Println(fjoGas(ai(2)))
	case "eco":
		fmt.Println(fjoEco(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	case "vs":
		fmt.Println(fjoVs(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7), ai(8)))
	default:
		os.Exit(2)
	}
}
