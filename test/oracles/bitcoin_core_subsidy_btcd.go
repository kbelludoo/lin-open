// Replica of btcsuite/btcd CalcBlockSubsidy (ISC) for an independent Go oracle.
// Upstream: github.com/btcsuite/btcd blockchain/validate.go @ v0.24.2
// commit cc26860b40265e1332cca8748c5dbaf3c81cc094
// Not linked into the LIN TCB.
package main

import (
	"fmt"
	"os"
	"strconv"
)

const baseSubsidy int64 = 50 * 100000000

func calcBlockSubsidy(height int32, interval int32) int64 {
	if interval == 0 {
		return baseSubsidy
	}
	return baseSubsidy >> uint(height/interval)
}

func main() {
	if len(os.Args) < 2 {
		os.Exit(2)
	}
	h64, err := strconv.ParseInt(os.Args[1], 10, 32)
	if err != nil {
		os.Exit(2)
	}
	fmt.Println(calcBlockSubsidy(int32(h64), 210000))
}
