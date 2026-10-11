// Independent Go math/big oracle (not TCB). Same language family as geth.
// FullMath width (512-bit product), not CRT/mulmod. Remainder identity q*d+r==n.
package main

import (
	"bufio"
	"fmt"
	"io"
	"math/big"
	"os"
	"strings"
)

var umax = new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 256), big.NewInt(1))

func parseHex(s string) *big.Int {
	s = strings.TrimPrefix(strings.TrimPrefix(s, "0x"), "0X")
	if s == "" {
		return big.NewInt(0)
	}
	n := new(big.Int)
	if _, ok := n.SetString(s, 16); !ok {
		fmt.Fprintf(os.Stderr, "bad hex %s\n", s)
		os.Exit(1)
	}
	return n
}

func hex32(n *big.Int) string {
	if n.Sign() < 0 {
		fmt.Fprintln(os.Stderr, "negative")
		os.Exit(1)
	}
	s := n.Text(16)
	if len(s) > 64 {
		s = s[len(s)-64:]
	}
	return strings.Repeat("0", 64-len(s)) + s
}

func muldiv(a, b, d *big.Int) (int, *big.Int, *big.Int) {
	z := big.NewInt(0)
	if d.Sign() == 0 {
		return -1, z, z
	}
	n := new(big.Int).Mul(a, b)
	q := new(big.Int)
	r := new(big.Int)
	q.QuoRem(n, d, r)
	if q.Cmp(umax) > 0 {
		return -2, big.NewInt(0), big.NewInt(0)
	}
	chk := new(big.Int).Add(new(big.Int).Mul(q, d), r)
	if chk.Cmp(n) != 0 || r.Cmp(d) >= 0 {
		fmt.Fprintln(os.Stderr, "FAIL remainder identity")
		os.Exit(1)
	}
	return 1, q, r
}

func selftest() int {
	st, q, r := muldiv(big.NewInt(7), big.NewInt(9), big.NewInt(2))
	if st != 1 || q.Cmp(big.NewInt(31)) != 0 || r.Cmp(big.NewInt(1)) != 0 {
		fmt.Fprintln(os.Stderr, "FAIL 7*9/2")
		return 1
	}
	n := new(big.Int).Mul(umax, umax)
	lo := new(big.Int).And(n, umax)
	hi := new(big.Int).Rsh(n, 256)
	if lo.Cmp(big.NewInt(1)) != 0 || hi.Cmp(new(big.Int).Sub(umax, big.NewInt(1))) != 0 {
		fmt.Fprintln(os.Stderr, "FAIL max^2")
		return 1
	}
	a := new(big.Int).Lsh(big.NewInt(1), 255)
	st, q, r = muldiv(a, big.NewInt(2), big.NewInt(3))
	wantQ, _ := new(big.Int).SetString("5555555555555555555555555555555555555555555555555555555555555555", 16)
	if st != 1 || r.Cmp(big.NewInt(1)) != 0 || q.Cmp(wantQ) != 0 {
		fmt.Fprintln(os.Stderr, "FAIL 2^255*2/3")
		return 1
	}
	if st0, _, _ := muldiv(big.NewInt(1), big.NewInt(1), big.NewInt(0)); st0 != -1 {
		fmt.Fprintln(os.Stderr, "FAIL d=0")
		return 1
	}
	if st2, _, _ := muldiv(a, big.NewInt(2), big.NewInt(1)); st2 != -2 {
		fmt.Fprintln(os.Stderr, "FAIL q overflow")
		return 1
	}
	st, q, _ = muldiv(big.NewInt(997000), big.NewInt(20000), big.NewInt(10997000))
	if st != 1 || q.Cmp(big.NewInt(1813)) != 0 {
		fmt.Fprintln(os.Stderr, "FAIL 1813")
		return 1
	}
	two256 := new(big.Int).Lsh(big.NewInt(1), 256)
	if two256.Cmp(umax) < 0 || umax.Cmp(two256) >= 0 {
		fmt.Fprintln(os.Stderr, "FAIL ge512")
		return 1
	}
	fmt.Println("SELFTEST_PASS go_math_big q*d+r==n ge512")
	return 0
}

func batch(in io.Reader) int {
	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	nvec := 0
	for sc.Scan() {
		t := strings.TrimSpace(sc.Text())
		if t == "" {
			continue
		}
		p := strings.Fields(t)
		switch p[0] {
		case "MUL":
			a, b := parseHex(p[1]), parseHex(p[2])
			n := new(big.Int).Mul(a, b)
			lo := new(big.Int).And(n, umax)
			hi := new(big.Int).Rsh(n, 256)
			fmt.Printf("1 %s %s\n", hex32(lo), hex32(hi))
		case "MULDIV":
			st, q, r := muldiv(parseHex(p[1]), parseHex(p[2]), parseHex(p[3]))
			fmt.Printf("%d %s %s\n", st, hex32(q), hex32(r))
		case "GE":
			a, b := parseHex(p[1]), parseHex(p[2])
			if a.Cmp(b) >= 0 {
				fmt.Println("1")
			} else {
				fmt.Println("0")
			}
		default:
			fmt.Fprintf(os.Stderr, "unknown op %s\n", p[0])
			return 1
		}
		nvec++
	}
	if err := sc.Err(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Fprintf(os.Stderr, "BATCH_N=%d GO_BIGINT_CONSENSUS\n", nvec)
	return 0
}

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "--self-test" {
		os.Exit(selftest())
	}
	if len(os.Args) >= 2 && os.Args[1] == "--batch" {
		os.Exit(batch(os.Stdin))
	}
	fmt.Fprintln(os.Stderr, "usage: u512_go_oracle --self-test | --batch")
	os.Exit(2)
}
