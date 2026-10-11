// Independent Go oracle for go-ethereum memoryCopierGas / gasKeccak256.
// Mirrors pinned v1.16.9: word gas is per_word*((size+31)/32).
// CopyGas=3, Keccak256WordGas=6. Not linked into the LIN compiler TCB.
// Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	copyGas    = 3
	keccakWord = 6
)

func gethMore(keccak bool, size, memgas uint64) (uint64, bool) {
	words := (size + 31) / 32
	per := uint64(copyGas)
	if keccak {
		per = keccakWord
	}
	more := per * words
	sum := memgas + more
	if sum < memgas {
		return 0, false
	}
	return sum, true
}

func linCopy(size int64) int64 {
	if size < 0 {
		return 0
	}
	return int64(copyGas) * ((size + 31) / 32)
}

func linKeccak(size int64) int64 {
	if size < 0 {
		return 0
	}
	return int64(keccakWord) * ((size + 31) / 32)
}

func linWith(kind, memgas, size int64) int64 {
	if kind < 0 || memgas < 0 || size < 0 {
		return 0
	}
	more := linCopy(size)
	if kind != 0 {
		more = linKeccak(size)
	}
	s := memgas + more
	if uint64(s) < uint64(memgas) {
		return 0
	}
	return s
}

func selftest() int {
	v, ok := gethMore(false, 32, 0)
	if !ok || v != 3 {
		return 1
	}
	v, ok = gethMore(true, 1, 0)
	if !ok || v != 6 {
		return 2
	}
	if linCopy(33) != 6 {
		return 3
	}
	if linCopy(-1) != 0 {
		return 4
	}
	if linKeccak(33) != 12 {
		return 5
	}
	if linWith(0, 100, 32) != 103 {
		return 6
	}
	if linCopy(49152) != 4608 {
		return 7
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_copygas_go selftest|copy|keccak|geth-copy|geth-keccak size")
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
	case "copy":
		fmt.Println(linCopy(size))
	case "keccak":
		fmt.Println(linKeccak(size))
	case "geth-copy":
		v, ok := gethMore(false, uint64(size), 0)
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
	case "geth-keccak":
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
