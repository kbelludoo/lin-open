// Independent Go oracle for go-ethereum gasCreateEip3860 / gasCreate2Eip3860.
// Mirrors pinned v1.16.9: size>MaxInitCodeSize is overflow; surcharge is
// word_gas*((size+31)/32). CREATE2 adds Keccak256WordGas. Not linked into
// the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	maxInit     = 49152
	wordGas     = 2
	keccakWord  = 6
)

func gethMore(create2 bool, size, memgas uint64) (uint64, bool) {
	if size > maxInit {
		return 0, false
	}
	words := (size + 31) / 32
	per := uint64(wordGas)
	if create2 {
		per = wordGas + keccakWord
	}
	more := per * words
	sum := memgas + more
	if sum < memgas {
		return 0, false
	}
	return sum, true
}

func linCreate(size int64) int64 {
	if size < 0 || size > maxInit {
		return 0
	}
	return int64(wordGas) * ((size + 31) / 32)
}

func linCreate2(size int64) int64 {
	if size < 0 || size > maxInit {
		return 0
	}
	return int64(wordGas+keccakWord) * ((size + 31) / 32)
}

func linWith(kind, memgas, size int64) int64 {
	if kind < 0 || memgas < 0 || size < 0 || size > maxInit {
		return 0
	}
	more := linCreate(size)
	if kind != 0 {
		more = linCreate2(size)
	}
	s := memgas + more
	if uint64(s) < uint64(memgas) {
		return 0
	}
	return s
}

func selftest() int {
	v, ok := gethMore(false, 32, 0)
	if !ok || v != 2 {
		return 1
	}
	v, ok = gethMore(true, 1, 0)
	if !ok || v != 8 {
		return 2
	}
	_, ok = gethMore(false, 49153, 0)
	if ok {
		return 3
	}
	if linCreate(49152) != 3072 {
		return 4
	}
	if linCreate(49153) != 0 {
		return 5
	}
	if linCreate2(33) != 16 {
		return 6
	}
	if linWith(0, 100, 32) != 102 {
		return 7
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_create3860_go selftest|create|create2|geth-create|geth-create2 size")
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
	size, _ := strconv.ParseInt(os.Args[2], 10, 64)
	switch os.Args[1] {
	case "create":
		fmt.Println(linCreate(size))
	case "create2":
		fmt.Println(linCreate2(size))
	case "geth-create":
		v, ok := gethMore(false, uint64(size), 0)
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
	case "geth-create2":
		v, ok := gethMore(true, uint64(size), 0)
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
	default:
		os.Exit(2)
	}
}
