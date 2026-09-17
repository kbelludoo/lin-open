// Independent Go oracle for go-ethereum memoryGasCost (Yellow Paper Cmem).
// Mirrors v1.16.9 uint64 wrap of total-last and ErrGasUintOverflow above
// 0x1FFFFFFFE0. Not linked into the LIN compiler TCB. Algorithm: LGPL-3.0.
package main

import (
	"fmt"
	"math"
	"os"
	"strconv"
)

const (
	memoryGas = 3
	quadDiv   = 512
	memCap    = uint64(0x1FFFFFFFE0)
)

func toWordSize(size uint64) uint64 {
	if size > math.MaxUint64-31 {
		return math.MaxUint64/32 + 1
	}
	return (size + 31) / 32
}

func gethFee(newSize, curLen, last uint64) (uint64, bool) {
	if newSize == 0 {
		return 0, false
	}
	if newSize > memCap {
		return 0, true
	}
	words := toWordSize(newSize)
	rounded := words * 32
	if rounded <= curLen {
		return 0, false
	}
	square := words * words
	total := words*memoryGas + square/quadDiv
	return total - last, false
}

func selftest() int {
	v, ov := gethFee(32, 0, 0)
	if ov || v != 3 {
		return 1
	}
	v, ov = gethFee(1024, 0, 0)
	if ov || v != 98 {
		return 2
	}
	v, ov = gethFee(33, 32, 3)
	if ov || v != 3 {
		return 3
	}
	v, ov = gethFee(64, 0, 999)
	wantWrap := uint64(6)
	wantWrap -= 999
	if ov || v != wantWrap {
		return 4
	}
	_, ov = gethFee(memCap+1, 0, 0)
	if !ov {
		return 5
	}
	if toWordSize(33) != 2 {
		return 6
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_memorygas_go selftest|fee s l last|words s")
		os.Exit(2)
	}
	if os.Args[1] == "selftest" {
		rc := selftest()
		if rc == 0 {
			fmt.Println("PASS")
			os.Exit(0)
		}
		fmt.Printf("FAIL %d\n", rc)
		os.Exit(1)
	}
	if os.Args[1] == "fee" && len(os.Args) >= 5 {
		s, _ := strconv.ParseUint(os.Args[2], 10, 64)
		l, _ := strconv.ParseUint(os.Args[3], 10, 64)
		last, _ := strconv.ParseUint(os.Args[4], 10, 64)
		v, ov := gethFee(s, l, last)
		if ov {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
		return
	}
	if os.Args[1] == "words" && len(os.Args) >= 3 {
		s, _ := strconv.ParseUint(os.Args[2], 10, 64)
		fmt.Println(toWordSize(s))
		return
	}
	fmt.Fprintln(os.Stderr, "unknown op")
	os.Exit(2)
}
