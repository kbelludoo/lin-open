// Independent Go oracle for go-ethereum makeSelfdestructGasFn / EIP-3529.
// Mirrors pinned v1.16.9: cold 2600, create 25000, refund 24000, account-check 2500.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	cold      = 2600
	create    = 25000
	refundAmt = 24000
	warm      = 100
	staticGas = 5000
)

func okFlag(v int64) bool { return v == 0 || v == 1 }

func linAccountCheck(isCold int64) int64 {
	if !okFlag(isCold) {
		return 0
	}
	if isCold == 1 {
		return cold - warm
	}
	return 0
}

func linGas(isCold, targetEmpty, hasValue int64) int64 {
	if !okFlag(isCold) || !okFlag(targetEmpty) || !okFlag(hasValue) {
		return 0
	}
	gas := int64(0)
	if isCold == 1 {
		gas += cold
	}
	if targetEmpty == 1 && hasValue == 1 {
		gas += create
	}
	return gas
}

func linRefund(refundsEnabled, already int64) int64 {
	if !okFlag(refundsEnabled) || !okFlag(already) {
		return 0
	}
	if refundsEnabled == 0 || already == 1 {
		return 0
	}
	return refundAmt
}

func linTotal(isCold, targetEmpty, hasValue int64) int64 {
	if !okFlag(isCold) || !okFlag(targetEmpty) || !okFlag(hasValue) {
		return 0
	}
	return staticGas + linGas(isCold, targetEmpty, hasValue)
}

func selftest() int {
	if linAccountCheck(1) != 2500 {
		return 1
	}
	if linGas(1, 1, 1) != 27600 {
		return 2
	}
	if linRefund(0, 0) != 0 {
		return 3
	}
	if linRefund(1, 0) != 24000 {
		return 4
	}
	if linTotal(0, 0, 0) != 5000 {
		return 5
	}
	if linGas(-1, 0, 0) != 0 {
		return 6
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_selfdestruct_go selftest|gas c e v|refund en dest|check c|total c e v")
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
	if os.Args[1] == "check" && len(os.Args) >= 3 {
		n, _ := strconv.ParseInt(os.Args[2], 10, 64)
		fmt.Println(linAccountCheck(n))
		return
	}
	if os.Args[1] == "refund" && len(os.Args) >= 4 {
		a, _ := strconv.ParseInt(os.Args[2], 10, 64)
		b, _ := strconv.ParseInt(os.Args[3], 10, 64)
		fmt.Println(linRefund(a, b))
		return
	}
	if len(os.Args) < 5 {
		os.Exit(2)
	}
	a, _ := strconv.ParseInt(os.Args[2], 10, 64)
	b, _ := strconv.ParseInt(os.Args[3], 10, 64)
	c, _ := strconv.ParseInt(os.Args[4], 10, 64)
	switch os.Args[1] {
	case "gas":
		fmt.Println(linGas(a, b, c))
	case "total":
		fmt.Println(linTotal(a, b, c))
	default:
		os.Exit(2)
	}
}
