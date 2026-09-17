// Independent Go oracle for go-ethereum calcRefund (EIP-3529).
// Mirrors v1.16.9 uint64 wrap of gasUsed = initial - remaining and
// min(used/quotient, stateRefund) with RefundQuotient=2 / EIP-3529=5.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	qPre    uint64 = 2
	qLondon uint64 = 5
)

func gethGasUsed(initial, remaining uint64) uint64 {
	return initial - remaining
}

func gethRefund(used, stateRefund uint64, london bool) uint64 {
	var refund uint64
	if !london {
		refund = used / qPre
	} else {
		refund = used / qLondon
	}
	if refund > stateRefund {
		refund = stateRefund
	}
	return refund
}

func selftest() int {
	if gethRefund(21000, 0, true) != 0 {
		return 1
	}
	if gethRefund(21000, 100000, true) != 4200 {
		return 2
	}
	if gethRefund(21000, 100000, false) != 10500 {
		return 3
	}
	if gethRefund(21000, 1000, true) != 1000 {
		return 4
	}
	if gethRefund(5, 100, true) != 1 {
		return 5
	}
	if gethRefund(4, 100, true) != 0 {
		return 6
	}
	if gethGasUsed(21000, 21001) != ^uint64(0) {
		return 7
	}
	if gethRefund(21000, 100000, true) != 4200 {
		return 8
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_calcrefund_go selftest|refund used state london|used initial remaining")
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
	if os.Args[1] == "refund" && len(os.Args) >= 5 {
		used, _ := strconv.ParseUint(os.Args[2], 10, 64)
		st, _ := strconv.ParseUint(os.Args[3], 10, 64)
		lon, _ := strconv.Atoi(os.Args[4])
		fmt.Println(gethRefund(used, st, lon != 0))
		return
	}
	if os.Args[1] == "used" && len(os.Args) >= 4 {
		ini, _ := strconv.ParseUint(os.Args[2], 10, 64)
		rem, _ := strconv.ParseUint(os.Args[3], 10, 64)
		fmt.Println(gethGasUsed(ini, rem))
		return
	}
	fmt.Fprintln(os.Stderr, "unknown op")
	os.Exit(2)
}
