// Independent Go oracle for op-geth newL1CostFuncEcotone / Bedrock / operator.
// Mirrors pinned v1.101702.3 rollup_cost.go with explicit integer args.
// FastLZ / StateDB omitted. Not linked into the LIN compiler TCB.
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

func calldata(zeroes, ones int64) int64 {
	if !okNonneg(zeroes) || !okNonneg(ones) {
		return 0
	}
	z := muldiv(zeroes, 4, 1)
	n := muldiv(ones, 16, 1)
	if (z == 0 && zeroes != 0) || (n == 0 && ones != 0) {
		return 0
	}
	s := z + n
	if uint64(s) < uint64(z) {
		return 0
	}
	return s
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

func ecoFee(z, o, bf, bb, bs, bbs int64) int64 {
	cg := calldata(z, o)
	inn := inner(bf, bb, bs, bbs)
	if cg == 0 && (z != 0 || o != 0) {
		return 0
	}
	if inn == 0 && (bf != 0 || bb != 0) && (bs != 0 || bbs != 0) {
		return 0
	}
	return muldiv(cg, inn, 16000000)
}

func ecoNoblob(z, o, bf, bs int64) int64 { return ecoFee(z, o, bf, 0, bs, 0) }

func ecoVs(z, o, bf, bb, bs, bbs int64) int64 {
	full := ecoFee(z, o, bf, bb, bs, bbs)
	drop := ecoNoblob(z, o, bf, bs)
	if uint64(full) < uint64(drop) {
		return 0
	}
	return full - drop
}

func bedrock(z, o, overhead, bf, scalar, regolith int64) int64 {
	if !okNonneg(overhead) || !okNonneg(bf) || !okNonneg(scalar) {
		return 0
	}
	if regolith != 0 && regolith != 1 {
		return 0
	}
	cg := calldata(z, o)
	if regolith == 0 {
		pad := muldiv(68, 16, 1)
		t := cg + pad
		if uint64(t) < uint64(cg) {
			return 0
		}
		cg = t
	}
	g := cg + overhead
	if uint64(g) < uint64(cg) {
		return 0
	}
	tmp := muldiv(g, bf, 1)
	if tmp == 0 && g != 0 && bf != 0 {
		return 0
	}
	return muldiv(tmp, scalar, 1000000)
}

func opIsthmus(gas, scalar, constant int64) int64 {
	if !okNonneg(gas) || !okNonneg(scalar) || !okNonneg(constant) {
		return 0
	}
	q := muldiv(gas, scalar, 1000000)
	s := q + constant
	if uint64(s) < uint64(q) {
		return 0
	}
	return s
}

func opJovian(gas, scalar, constant int64) int64 {
	if !okNonneg(gas) || !okNonneg(scalar) || !okNonneg(constant) {
		return 0
	}
	p := muldiv(gas, scalar, 1)
	if p == 0 && gas != 0 && scalar != 0 {
		return 0
	}
	p2 := muldiv(p, 100, 1)
	if p2 == 0 && p != 0 {
		return 0
	}
	s := p2 + constant
	if uint64(s) < uint64(p2) {
		return 0
	}
	return s
}

func selftest() int {
	if calldata(0, 30) != 480 {
		return 1
	}
	if ecoFee(0, 30, 1000000000, 10000000, 2, 3) != 960900 {
		return 2
	}
	if ecoNoblob(0, 30, 1000000000, 2) != 960000 {
		return 3
	}
	if bedrock(0, 30, 50, 1000000000, 7000000, 0) != 11326000000000 {
		return 4
	}
	if opIsthmus(1618, 1439103868, 1256417826609331460) != 1256417826611659930 {
		return 5
	}
	if opJovian(1618, 1439103868, 1256417826609331460) != 1256650673615173860 {
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
		fmt.Fprintln(os.Stderr, "usage: opgeth_ecotone_go selftest|fee|noblob|vs|bedrock|isthmus|jovian")
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
	case "fee":
		fmt.Println(ecoFee(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	case "noblob":
		fmt.Println(ecoNoblob(ai(2), ai(3), ai(4), ai(5)))
	case "vs":
		fmt.Println(ecoVs(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	case "bedrock":
		fmt.Println(bedrock(ai(2), ai(3), ai(4), ai(5), ai(6), ai(7)))
	case "isthmus":
		fmt.Println(opIsthmus(ai(2), ai(3), ai(4)))
	case "jovian":
		fmt.Println(opJovian(ai(2), ai(3), ai(4)))
	default:
		os.Exit(2)
	}
}
