// Independent Go oracle for go-ethereum gasExpEIP158 / ExpByteEIP158=50.
// Mirrors pinned v1.16.9: gas = 10 + expByteLen*50.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	expGas     = 10
	expByte    = 50
	maxByteLen = 256
	maxBitLen  = 2048
)

func gethExp(n uint64) (uint64, bool) {
	prod := n * uint64(expByte)
	out := uint64(expGas) + prod
	if out < prod {
		return 0, false
	}
	return out, true
}

func linByteLen(bitLen int64) int64 {
	if bitLen < 0 || bitLen > maxBitLen {
		return 0
	}
	return (bitLen + 7) / 8
}

func linExp(n int64) int64 {
	if n < 0 || n > maxByteLen {
		return 0
	}
	prod := n * int64(expByte)
	s := int64(expGas) + prod
	if uint64(s) < uint64(prod) {
		return 0
	}
	return s
}

func linFromBitlen(bitLen int64) int64 {
	if bitLen < 0 || bitLen > maxBitLen {
		return 0
	}
	n := linByteLen(bitLen)
	if bitLen > 0 && n == 0 {
		return 0
	}
	return linExp(n)
}

func selftest() int {
	v, ok := gethExp(32)
	if !ok || v != 1610 {
		return 1
	}
	v, ok = gethExp(0)
	if !ok || v != 10 {
		return 2
	}
	if linFromBitlen(9) != 110 {
		return 3
	}
	if linFromBitlen(-1) != 0 {
		return 4
	}
	if linExp(257) != 0 {
		return 5
	}
	if linExp(256) != 12810 {
		return 6
	}
	if linByteLen(256) != 32 {
		return 7
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_gasexp_go selftest|exp n|from-bitlen bitLen|geth-exp n")
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
	if len(os.Args) < 3 {
		os.Exit(2)
	}
	n, _ := strconv.ParseInt(os.Args[2], 10, 64)
	switch os.Args[1] {
	case "exp":
		fmt.Println(linExp(n))
	case "from-bitlen":
		fmt.Println(linFromBitlen(n))
	case "geth-exp":
		v, ok := gethExp(uint64(n))
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
	default:
		os.Exit(2)
	}
}
