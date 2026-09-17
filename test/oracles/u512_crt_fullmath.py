#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Uniswap v3 FullMath algorithm for 256x256->512 mulDiv.

CRT product: prod0 = (a*b) mod 2^256 (wrapping 4xuint64 schoolbook);
mm = (a*b) mod (2^256-1) via rotate-and-add in the Mersenne ring
(2^256 ≡ 1, so doubling is a 256-bit rotate — not schoolbook);
prod1 = mm - prod0 - [mm < prod0]. Then a*b = prod1·2^256 + prod0.

Division: remainder = mulmod(a,b,d) by add-and-double; subtract from
the product; factor 2^k out of d; Newton–Raphson inverse of the odd
denominator mod 2^256 (Hensel, 4→256 bits); q = prod0_adj * inv.

Not restoring bit-serial (LIN) and not Knuth D. Python int is used
only for 64×64→128 products and bit tests; never as a 512-bit value.

EXPERIMENTAL: FullMath *algorithm* off-chain. Not the EVM mulmod opcode,
not solc assembly, not a deployed pool.
"""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N = 4
N512 = 8
TWO = [2, 0, 0, 0]
ONE = [1, 0, 0, 0]
ZERO = [0, 0, 0, 0]


def parse_be(s: str, nbytes: int) -> list[int]:
    t = s.strip()
    if t.startswith(("0x", "0X")):
        t = t[2:]
    t = t.zfill(nbytes * 2)
    be = bytes.fromhex(t[-nbytes * 2 :])
    le = bytes(reversed(be))
    n = nbytes // 8
    return [int.from_bytes(le[8 * i : 8 * i + 8], "little") for i in range(n)]


def be_hex(limbs: list[int], n: int) -> str:
    raw = bytearray(n * 8)
    for i in range(n):
        raw[8 * i : 8 * i + 8] = int(limbs[i] & MASK64).to_bytes(8, "little")
    return bytes(reversed(raw)).hex()


def zcopy(x: list[int] | None = None) -> list[int]:
    return list(x) if x is not None else [0] * N


def is_zero(x: list[int]) -> bool:
    return all(v == 0 for v in x)


def is_umax(x: list[int]) -> bool:
    return all(v == MASK64 for v in x)


def ge256(a: list[int], b: list[int]) -> bool:
    for j in range(len(a) - 1, -1, -1):
        if a[j] > b[j]:
            return True
        if a[j] < b[j]:
            return False
    return True


ge_limbs = ge256


def add256(a: list[int], b: list[int]) -> tuple[list[int], int]:
    out, carry = [0] * N, 0
    for i in range(N):
        t = a[i] + b[i] + carry
        out[i] = t & MASK64
        carry = t >> 64
    return out, carry


def sub256(a: list[int], b: list[int]) -> tuple[list[int], int]:
    out, borrow = [0] * N, 0
    for i in range(N):
        t = a[i] - b[i] - borrow
        if t < 0:
            out[i] = t + (1 << 64)
            borrow = 1
        else:
            out[i] = t
            borrow = 0
    return out, borrow


def mul_lo256(a: list[int], b: list[int]) -> list[int]:
    n = [0] * N
    for i in range(N):
        carry = 0
        for j in range(N - i):
            t = n[i + j] + a[i] * b[j] + carry
            n[i + j] = t & MASK64
            carry = t >> 64
    return n


def reduce_m2(a: list[int]) -> list[int]:
    return zcopy(ZERO) if is_umax(a) else zcopy(a)


def rotl1_m2(a: list[int]) -> list[int]:
    a = reduce_m2(a)
    if is_zero(a):
        return zcopy(ZERO)
    out, carry = [0] * N, 0
    for i in range(N):
        t = (a[i] << 1) | carry
        out[i] = t & MASK64
        carry = t >> 64
    if carry:
        out[0] |= 1
    return reduce_m2(out)


def add_m2(a: list[int], b: list[int]) -> list[int]:
    s, c = add256(reduce_m2(a), reduce_m2(b))
    if c:
        s, _ = add256(s, ONE)
    return reduce_m2(s)


def mulmod_m2(a: list[int], b: list[int]) -> list[int]:
    a, b = reduce_m2(a), reduce_m2(b)
    r = zcopy(ZERO)
    for i in range(255, -1, -1):
        r = rotl1_m2(r)
        if (a[i >> 6] >> (i & 63)) & 1:
            r = add_m2(r, b)
    return r


def crt_mul(a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
    prod0 = mul_lo256(a, b)
    mm = mulmod_m2(a, b)
    if ge256(mm, prod0):
        prod1, _ = sub256(mm, prod0)
    else:
        t, _ = sub256(mm, prod0)
        prod1, _ = sub256(t, ONE)
    return prod0, prod1


def shl1(a: list[int]) -> tuple[list[int], int]:
    out, carry = [0] * N, 0
    for i in range(N):
        t = (a[i] << 1) | carry
        out[i] = t & MASK64
        carry = t >> 64
    return out, carry


def addmod(a: list[int], b: list[int], m: list[int]) -> list[int]:
    s, c = add256(a, b)
    if c:
        s, _ = sub256(s, m)
        return s
    if ge256(s, m):
        s, _ = sub256(s, m)
    return s


def rem256(n: list[int], d: list[int]) -> list[int]:
    r = zcopy(ZERO)
    for i in range(255, -1, -1):
        r, c = shl1(r)
        r[0] |= (n[i >> 6] >> (i & 63)) & 1
        if c or ge256(r, d):
            r, _ = sub256(r, d)
    return r


def mulmod(a: list[int], b: list[int], m: list[int]) -> list[int]:
    bb = rem256(b, m)
    r = zcopy(ZERO)
    for i in range(255, -1, -1):
        r = addmod(r, r, m)
        if (a[i >> 6] >> (i & 63)) & 1:
            r = addmod(r, bb, m)
    return r


def ctz256(x: list[int]) -> int:
    n = 0
    for i in range(N):
        if x[i]:
            v, c = x[i], 0
            while (v & 1) == 0:
                v >>= 1
                c += 1
            return n + c
        n += 64
    return 256


def shr256(a: list[int], s: int) -> list[int]:
    if s <= 0:
        return zcopy(a)
    if s >= 256:
        return zcopy(ZERO)
    w, b = divmod(s, 64)
    out = [0] * N
    for i in range(N):
        src = i + w
        if src < N:
            out[i] = a[src] >> b
        if b and src + 1 < N:
            out[i] |= (a[src + 1] << (64 - b)) & MASK64
    return out


def shl256(a: list[int], s: int) -> list[int]:
    if s <= 0:
        return zcopy(a)
    if s >= 256:
        return zcopy(ZERO)
    w, b = divmod(s, 64)
    out = [0] * N
    for i in range(N):
        dst = i + w
        if dst < N:
            out[dst] |= (a[i] << b) & MASK64
        if b and dst + 1 < N:
            out[dst + 1] |= a[i] >> (64 - b)
    return out


def or256(a: list[int], b: list[int]) -> list[int]:
    return [a[i] | b[i] for i in range(N)]


def newton_inv(d: list[int]) -> list[int]:
    inv = mul_lo256([3, 0, 0, 0], d)
    inv[0] ^= 2
    for _ in range(6):
        t = mul_lo256(d, inv)
        t, _ = sub256(TWO, t)
        inv = mul_lo256(inv, t)
    return inv


def identity512(p0: list[int], p1: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd0, qd1 = crt_mul(q, d)
    s0, c = add256(qd0, r)
    s1, c2 = add256(qd1, [c, 0, 0, 0])
    if c2:
        return False
    dext = d + [0] * N
    rext = r + [0] * N
    return s0 == p0 and s1 == p1 and not ge256(rext, dext)


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    p0, p1 = crt_mul(a, b)
    return 1, p0 + p1


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    zq, zr = zcopy(ZERO), zcopy(ZERO)
    p0, p1 = crt_mul(a, b)
    n = p0 + p1
    if is_zero(d):
        return -1, zq, zr, n
    if not ge256(d, p1) or d == p1:
        return -2, zq, zr, n
    rem = mulmod(a, b, d)
    adj1 = zcopy(p1)
    if not ge256(p0, rem):
        adj1, _ = sub256(adj1, ONE)
    adj0, _ = sub256(p0, rem)
    k = ctz256(d)
    d_odd = shr256(d, k)
    if k == 0:
        adj = adj0
    else:
        adj = or256(shr256(adj0, k), shl256(adj1, 256 - k))
    q = mul_lo256(adj, newton_inv(d_odd))
    if not identity512(p0, p1, q, d, rem):
        return -2, q, rem, n
    return 1, q, rem, n


def le256(v: int) -> list[int]:
    x, out = int(v), [0] * N
    for i in range(N):
        out[i] = x & MASK64
        x >>= 64
    return out


def limbs_u(v: list[int]) -> int:
    x = 0
    for i, limb in enumerate(v):
        x |= (limb & MASK64) << (64 * i)
    return x


def expect_st(st: int, want: int, msg: str) -> int:
    if st != want:
        sys.stderr.write(f"FAIL {msg} status={st} want={want}\n")
        return 1
    return 0


def selftest() -> int:
    fail = 0
    a, b, d = le256(7), le256(9), le256(2)
    st, q, rem, _n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if n[0] != 1 or n[4] != MASK64 - 1 or n[7] != MASK64:
        sys.stderr.write("FAIL max^2 CRT limbs\n")
        fail = 1
    if limbs_u(n[:N]) + (limbs_u(n[N:]) << 256) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 CRT vs python\n")
        fail = 1
    inv = newton_inv(le256(3))
    if (3 * limbs_u(inv)) & UMAX != 1:
        sys.stderr.write("FAIL newton 3*inv==1\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(1 << 255), le256(2), le256(3))
    fail |= expect_st(st, 1, "2^255*2/3")
    if q != [0x5555555555555555] * N or rem[0] != 1:
        sys.stderr.write("FAIL 2^255*2/3 pattern\n")
        fail = 1
    p0, p1 = n[:N], n[N:]
    if not identity512(p0, p1, q, le256(3), rem):
        sys.stderr.write("FAIL identity 2^255*2/3\n")
        fail = 1
    fail |= expect_st(muldiv256(le256(1), le256(1), le256(0))[0], -1, "d=0")
    fail |= expect_st(muldiv256(le256(1 << 255), le256(2), le256(1))[0], -2, "q overflow")
    st, q, rem, _n = muldiv256(le256(997000), le256(20000), le256(10997000))
    fail |= expect_st(st, 1, "getAmountOut")
    if limbs_u(q) != 1813:
        sys.stderr.write("FAIL 1813\n")
        fail = 1
    st, q, rem, _n = muldiv256(le256(2), le256(1 << 255), [MASK64] * N)
    fail |= expect_st(st, 1, "wrap-borrow")
    if q[0] != 1 or rem[0] != 1:
        sys.stderr.write("FAIL wrap-borrow words\n")
        fail = 1
    A, B = [0] * N512, [MASK64] * N + [0] * N
    A[4] = 1
    if not ge256(A, B) or ge256(B, A) or not ge256(A, A):
        sys.stderr.write("FAIL ge512\n")
        fail = 1
    rng = 0xC0FFEE
    for _ in range(64):
        rng = (rng * 6364136223846793005 + 1) & ((1 << 64) - 1)
        xa = (rng * 0x9E3779B97F4A7C15) & UMAX
        xb = (rng * 0xBF58476D1CE4E5B9) & UMAX
        xd = (rng * 0x94D049BB133111EB) & UMAX or 1
        st, q, rem, nn = muldiv256(le256(xa), le256(xb), le256(xd))
        prod = xa * xb
        p0, p1 = nn[:N], nn[N:]
        if limbs_u(p0) + (limbs_u(p1) << 256) != prod:
            sys.stderr.write("FAIL CRT reconstruct\n")
            fail = 1
            break
        qq, rr = divmod(prod, xd)
        if qq > UMAX:
            if st != -2:
                sys.stderr.write("FAIL random overflow\n")
                fail = 1
                break
            continue
        if st != 1 or limbs_u(q) != qq or limbs_u(rem) != rr:
            sys.stderr.write(f"FAIL random {xa} {xb} {xd}\n")
            fail = 1
            break
        if not identity512(p0, p1, q, le256(xd), rem):
            sys.stderr.write("FAIL random identity\n")
            fail = 1
            break
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS crt_fullmath q*d+r==n ge512 crt_prod newton\n")
    return 0


def run_batch() -> int:
    nvec = 0
    for line in sys.stdin:
        parts = line.split()
        if len(parts) < 3:
            continue
        op, ha, hb = parts[0], parts[1], parts[2]
        if op == "GE":
            A, B = parse_be(ha, 64), parse_be(hb, 64)
            sys.stdout.write(("1" if ge256(A, B) else "0") + "\n")
        elif op == "MUL":
            a, b = parse_be(ha, 32), parse_be(hb, 32)
            st, n = mul256(a, b)
            sys.stdout.write(f"{st} {be_hex(n[:N], N)} {be_hex(n[N:], N)}\n")
        elif op == "MULDIV":
            if len(parts) < 4:
                return 1
            a, b, d = parse_be(ha, 32), parse_be(hb, 32), parse_be(parts[3], 32)
            st, q, rem, _n = muldiv256(a, b, d)
            sys.stdout.write(f"{st} {be_hex(q, N)} {be_hex(rem, N)}\n")
        else:
            sys.stderr.write(f"unknown op {op}\n")
            return 1
        nvec += 1
    sys.stderr.write(f"BATCH_N={nvec} CRT_FULLMATH_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_crt_fullmath.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
