// Independent Go oracle for go-ethereum gasExtCodeCopyEIP2929.
// Mirrors pinned v1.16.9: CopyGas=3 words + cold-warm 2500. Cmem omitted.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	copyGas   = 3
	warm      = 100
	surcharge = 2500
)

func okSize(v int64) bool { return v >= 0 }
func okFlag(v int64) bool { return v == 0 || v == 1 }

func linWords(size int64) int64 {
	if !okSize(size) {
		return 0
	}
	return (size + 31) / 32
}

func linCopy(size int64) int64 {
	if !okSize(size) {
		return 0
	}
	return copyGas * linWords(size)
}

func linSurcharge(isCold int64) int64 {
	if !okFlag(isCold) {
		return 0
	}
	if isCold == 1 {
		return surcharge
	}
	return 0
}

func linDynamic(size, isCold int64) int64 {
	if !okSize(size) || !okFlag(isCold) {
		return 0
	}
	copy := linCopy(size)
	extra := linSurcharge(isCold)
	s := copy + extra
	if uint64(s) < uint64(copy) {
		return 0
	}
	return s
}

func linTotal(size, isCold int64) int64 {
	if !okSize(size) || !okFlag(isCold) {
		return 0
	}
	d := linDynamic(size, isCold)
	s := warm + d
	if uint64(s) < uint64(d) {
		return 0
	}
	return s
}

func selftest() int {
	if linCopy(33) != 6 {
		return 1
	}
	if linDynamic(0, 1) != 2500 {
		return 2
	}
	if linDynamic(1024, 1) != 2596 {
		return 3
	}
	if linTotal(0, 0) != 100 {
		return 4
	}
	if linTotal(0, 1) != 2600 {
		return 5
	}
	if linDynamic(-1, 0) != 0 {
		return 6
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_extcodecopy_go selftest|copy s|surcharge c|dynamic s c|total s c")
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
	if os.Args[1] == "copy" && len(os.Args) >= 3 {
		n, _ := strconv.ParseInt(os.Args[2], 10, 64)
		fmt.Println(linCopy(n))
		return
	}
	if os.Args[1] == "surcharge" && len(os.Args) >= 3 {
		n, _ := strconv.ParseInt(os.Args[2], 10, 64)
		fmt.Println(linSurcharge(n))
		return
	}
	if len(os.Args) < 4 {
		os.Exit(2)
	}
	a, _ := strconv.ParseInt(os.Args[2], 10, 64)
	b, _ := strconv.ParseInt(os.Args[3], 10, 64)
	switch os.Args[1] {
	case "dynamic":
		fmt.Println(linDynamic(a, b))
	case "total":
		fmt.Println(linTotal(a, b))
	default:
		os.Exit(2)
	}
}
