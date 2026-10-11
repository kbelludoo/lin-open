// Independent Go oracle for go-ethereum makeGasSStoreFunc / EIP-3529.
// Mirrors pinned v1.16.9: sentry 2300, set 20000, reset-cold 2900, warm 100.
// Not linked into the LIN compiler TCB. Algorithm license: LGPL-3.0.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const (
	sentry    = 2300
	setGas    = 20000
	resetGas  = 5000
	cold      = 2100
	warm      = 100
	accessKey = 1900
	clear2200 = 15000
)

func clear3529() int64 { return int64(resetGas - cold + accessKey) }

func linSload(isWarm int64) int64 {
	if isWarm == 1 {
		return warm
	}
	if isWarm == 0 {
		return cold
	}
	return 0
}

func linGas(orig, curr, val, isWarm, gasLeft int64) int64 {
	if orig < 0 || orig > 3 || curr < 0 || curr > 3 || val < 0 || val > 3 {
		return 0
	}
	if isWarm != 0 && isWarm != 1 {
		return 0
	}
	if gasLeft <= sentry {
		return 0
	}
	cost := int64(0)
	if isWarm == 0 {
		cost = cold
	}
	if curr == val {
		return cost + warm
	}
	if orig == curr {
		if orig == 0 {
			return cost + setGas
		}
		return cost + (resetGas - cold)
	}
	return cost + warm
}

func linRefund(orig, curr, val, gasLeft, sched int64) int64 {
	if orig < 0 || orig > 3 || curr < 0 || curr > 3 || val < 0 || val > 3 {
		return 0
	}
	if sched != clear2200 && sched != clear3529() {
		return 0
	}
	if gasLeft <= sentry {
		return 0
	}
	if curr == val {
		return 0
	}
	if orig == curr {
		if orig == 0 {
			return 0
		}
		if val == 0 {
			return sched
		}
		return 0
	}
	r := int64(0)
	if orig != 0 {
		if curr == 0 {
			r -= sched
		} else if val == 0 {
			r += sched
		}
	}
	if orig == val {
		if orig == 0 {
			r += setGas - warm
		} else {
			r += (resetGas - cold) - warm
		}
	}
	return r
}

func selftest() int {
	if clear3529() != 4800 {
		return 1
	}
	if linGas(0, 0, 1, 1, 100000) != 20000 {
		return 2
	}
	if linGas(1, 1, 0, 1, 100000) != 2900 {
		return 3
	}
	if linRefund(1, 0, 1, 100000, 4800) != -2000 {
		return 4
	}
	if linRefund(0, 1, 0, 100000, 4800) != 19900 {
		return 5
	}
	if linSload(0) != 2100 {
		return 6
	}
	if linGas(0, 0, 1, 1, 2300) != 0 {
		return 7
	}
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: geth_sstore_go selftest|gas o c v w gl|refund o c v gl sched|sload w")
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
	if os.Args[1] == "sload" && len(os.Args) >= 3 {
		n, _ := strconv.ParseInt(os.Args[2], 10, 64)
		fmt.Println(linSload(n))
		return
	}
	if len(os.Args) < 7 {
		os.Exit(2)
	}
	a, _ := strconv.ParseInt(os.Args[2], 10, 64)
	b, _ := strconv.ParseInt(os.Args[3], 10, 64)
	c, _ := strconv.ParseInt(os.Args[4], 10, 64)
	d, _ := strconv.ParseInt(os.Args[5], 10, 64)
	e, _ := strconv.ParseInt(os.Args[6], 10, 64)
	switch os.Args[1] {
	case "gas":
		fmt.Println(linGas(a, b, c, d, e))
	case "refund":
		fmt.Println(linRefund(a, b, c, d, e))
	default:
		os.Exit(2)
	}
}
