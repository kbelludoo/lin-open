// Independent Go oracle for go-ethereum makeGasLog / LOG0-LOG4.
// Mirrors pinned v1.16.9: exec = 375 + n*375 + size*8.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	logGas   = 375
	topicGas = 375
	dataGas  = 8
)

func gethExec(n, size, memgas uint64) (uint64, bool) {
	if n > ^uint64(0)/uint64(topicGas) {
		return 0, false
	}
	topics := n * uint64(topicGas)
	if size > ^uint64(0)/uint64(dataGas) {
		return 0, false
	}
	data := size * uint64(dataGas)
	base := uint64(logGas) + topics
	if base < uint64(logGas) {
		return 0, false
	}
	sum := base + data
	if sum < base {
		return 0, false
	}
	out := memgas + sum
	if out < memgas {
		return 0, false
	}
	return out, true
}

func linExec(n, size int64) int64 {
	if n < 0 || n > 4 || size < 0 {
		return 0
	}
	if uint64(size) > 1152921504606846975 {
		return 0
	}
	data := size * int64(dataGas)
	base := int64(logGas) + n*int64(topicGas)
	s := base + data
	if uint64(s) < uint64(base) {
		return 0
	}
	return s
}

func linWith(memgas, n, size int64) int64 {
	if memgas < 0 {
		return 0
	}
	more := linExec(n, size)
	if more == 0 && (n < 0 || n > 4 || size < 0) {
		return 0
	}
	if more == 0 && size > 0 {
		return 0
	}
	s := memgas + more
	if uint64(s) < uint64(memgas) {
		return 0
	}
	return s
}

func selftest() int {
	v, ok := gethExec(3, 32, 0)
	if !ok || v != 1756 {
		return 1
	}
	v, ok = gethExec(0, 0, 0)
	if !ok || v != 375 {
		return 2
	}
	if linExec(0, 1) != 383 {
		return 3
	}
	if linExec(-1, 0) != 0 {
		return 4
	}
	if linExec(5, 0) != 0 {
		return 5
	}
	if linWith(100, 3, 32) != 1856 {
		return 6
	}
	if linExec(4, 1024) != 10067 {
		return 7
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_gaslog_go selftest|exec n size|geth-exec n size")
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
	if len(os.Args) < 4 {
		os.Exit(2)
	}
	n, _ := strconv.ParseInt(os.Args[2], 10, 64)
	size, _ := strconv.ParseInt(os.Args[3], 10, 64)
	switch os.Args[1] {
	case "exec":
		fmt.Println(linExec(n, size))
	case "geth-exec":
		v, ok := gethExec(uint64(n), uint64(size), 0)
		if !ok {
			fmt.Println("OVERFLOW")
			return
		}
		fmt.Println(v)
	default:
		os.Exit(2)
	}
}
