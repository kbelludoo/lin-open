#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comba 256x256->512 + non-restoring 512/256.

Comba: column-oriented product. For output limb k the inner sum is
all a[i]*b[k-i] into one running accumulator, then one write + carry.
Not row-major 16-bit schoolbook, not Karatsuba, not Toom-3, not NTT,
not CRT/Mersenne.

Non-restoring: remainder is two's-complement and may be negative;
each step shifts, then subtracts D if rem>=0 else adds D; q-bit is the
post-op sign; one final restore so r in [0,d). Not restoring-of-n
(no immediate add-back), not SRT radix-4 digits {-2..2}, not Barrett
mu, not Knuth D, not Goldschmidt, not Hensel. Python int only for
64x64->128 Comba products and 64-bit limb add/shift. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512, NW = 4, 8, 9


def parse_be(s: str, nbytes: int) -> list[int]:
    t = s.strip()[2:] if s.strip().startswith(("0x", "0X")) else s.strip()
    t = t.zfill(nbytes * 2)
    le = bytes(reversed(bytes.fromhex(t[-nbytes * 2 :])))
    return [int.from_bytes(le[8 * i : 8 * i + 8], "little") for i in range(nbytes // 8)]


def be_hex(limbs: list[int], n: int) -> str:
    raw = bytearray(n * 8)
    for i in range(n):
        raw[8 * i : 8 * i + 8] = int(limbs[i] & MASK64).to_bytes(8, "little")
    return bytes(reversed(raw)).hex()


def zcopy(x: list[int], n: int | None = None) -> list[int]:
    if n is None:
        return list(x)
    out = [0] * n
    for i in range(min(n, len(x))):
        out[i] = x[i] & MASK64
    return out


def is_zero(x: list[int]) -> bool:
    return all(v == 0 for v in x)


def le256(v: int) -> list[int]:
    return [(int(v) >> (64 * i)) & MASK64 for i in range(N)]


def limbs_u(x: list[int]) -> int:
    v = 0
    for i, w in enumerate(x):
        v |= (w & MASK64) << (64 * i)
    return v


def ge_limbs(a: list[int], b: list[int]) -> bool:
    n = max(len(a), len(b))
    for j in range(n - 1, -1, -1):
        av = a[j] if j < len(a) else 0
        bv = b[j] if j < len(b) else 0
        if av != bv:
            return av > bv
    return True


def comba_mul(a: list[int], b: list[int], nout: int) -> tuple[int, list[int]]:
    """Column Comba. Acc holds only 64x64 products + column carry."""
    aa, bb = zcopy(a, N), zcopy(b, N)
    out, acc = [0] * nout, 0
    for k in range(nout):
        i0 = 0 if k < N else k - (N - 1)
        i1 = k if k < N else (N - 1)
        for i in range(i0, i1 + 1):
            j = k - i
            if 0 <= j < N:
                acc += (aa[i] & MASK64) * (bb[j] & MASK64)
        out[k] = acc & MASK64
        acc >>= 64
    if acc:
        return -2, out
    return 1, out


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return comba_mul(a, b, N512)


def add_tc(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, carry = [0] * n, 0
    for i in range(n):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) + (bv & MASK64) + carry
        out[i] = t & MASK64
        carry = t >> 64
    return out


def neg_tc(a: list[int]) -> list[int]:
    out, carry = [0] * len(a), 1
    for i, v in enumerate(a):
        t = (v ^ MASK64) + carry
        out[i] = t & MASK64
        carry = t >> 64
    return out


def sub_tc(a: list[int], b: list[int]) -> list[int]:
    return add_tc(a, neg_tc(zcopy(b, len(a))))


def is_neg(x: list[int]) -> bool:
    return (x[-1] >> 63) != 0


def shl1_insert(x: list[int], bit: int) -> list[int]:
    out, c = [0] * len(x), bit & 1
    for i, v in enumerate(x):
        t = ((v & MASK64) << 1) | c
        out[i] = t & MASK64
        c = t >> 64
    return out


def nr_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    dd = zcopy(d, N)
    if is_zero(dd):
        return -1, [0] * N, [0] * N
    nn = zcopy(n, N512)
    rem = [0] * NW
    q = [0] * N512
    dext = zcopy(dd, NW)
    for bit in range(511, -1, -1):
        inbit = (nn[bit >> 6] >> (bit & 63)) & 1
        rem = shl1_insert(rem, inbit)
        rem = sub_tc(rem, dext) if not is_neg(rem) else add_tc(rem, dext)
        if not is_neg(rem):
            q[bit >> 6] |= 1 << (bit & 63)
    if is_neg(rem):
        rem = add_tc(rem, dext)
    if any(q[N:]) or any(rem[N:]):
        return -2, [0] * N, [0] * N
    qq = zcopy(q, N)
    rr = zcopy(rem, N)
    if ge_limbs(rr, dd):
        return -2, [0] * N, [0] * N
    return 1, qq, rr


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    st, prod = mul256(q, d)
    if st != 1:
        return False
    acc = 0
    out = [0] * N512
    for i in range(N512):
        rv = r[i] if i < len(r) else 0
        t = (prod[i] & MASK64) + (rv & MASK64) + acc
        out[i] = t & MASK64
        acc = t >> 64
    if acc:
        return False
    if out != zcopy(n, N512):
        return False
    return not ge_limbs(zcopy(r, N), zcopy(d, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    st, n = mul256(a, b)
    if st != 1:
        return st, [0] * N, [0] * N, n
    st, q, rem = nr_div(n, d)
    return st, q, rem, n


def expect_st(got: int, want: int, tag: str) -> int:
    if got != want:
        sys.stderr.write(f"FAIL {tag} st={got} want={want}\n")
        return 1
    return 0


def selftest() -> int:
    fail = 0
    st, n = mul256(le256(7), le256(9))
    fail |= expect_st(st, 1, "7*9")
    if n[0] != 63 or any(n[1:]):
        sys.stderr.write("FAIL 7*9 words\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 comba vs python\n")
        fail = 1
    st, q, rem, n = muldiv256([MASK64] * N, [MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max/max")
    if q != [MASK64] * N or rem[0] != 0 or any(rem[1:]):
        sys.stderr.write("FAIL max^2/max words\n")
        fail = 1
    fail |= expect_st(muldiv256([MASK64] * N, [MASK64] * N, le256(UMAX - 1))[0], -2, "max^2/(max-1)")
    st, q, rem, n = muldiv256(le256(1 << 255), le256(2), le256(3))
    fail |= expect_st(st, 1, "2^255*2/3")
    if q != [0x5555555555555555] * N or rem[0] != 1:
        sys.stderr.write("FAIL 2^255*2/3 pattern\n")
        fail = 1
    fail |= expect_st(muldiv256(le256(1), le256(1), le256(0))[0], -1, "d=0")
    fail |= expect_st(muldiv256(le256(1 << 255), le256(2), le256(1))[0], -2, "q overflow")
    st, q, rem, n = muldiv256(le256(997000), le256(20000), le256(10997000))
    fail |= expect_st(st, 1, "getAmountOut")
    if limbs_u(q) != 1813:
        sys.stderr.write("FAIL 1813\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(2), le256(1 << 255), [MASK64] * N)
    fail |= expect_st(st, 1, "wrap-borrow")
    if q[0] != 1 or rem[0] != 1:
        sys.stderr.write("FAIL wrap-borrow words\n")
        fail = 1
    if not identity512(n, q, [MASK64] * N, rem):
        sys.stderr.write("FAIL wrap-borrow identity\n")
        fail = 1
    A, B = [0] * N512, [MASK64] * N + [0] * N
    A[4] = 1
    if not ge_limbs(A, B) or ge_limbs(B, A) or not ge_limbs(A, A):
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
        if limbs_u(nn) != prod:
            sys.stderr.write("FAIL comba reconstruct\n")
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
            sys.stderr.write(f"FAIL random {xa} {xb} {xd} st={st} q={limbs_u(q)} want={qq}\n")
            fail = 1
            break
        if not identity512(nn, q, le256(xd), rem):
            sys.stderr.write("FAIL random identity\n")
            fail = 1
            break
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS comba_nr q*d+r==n ge512 comba_prod nrdiv\n")
    return 0


def run_batch() -> int:
    nvec = 0
    for line in sys.stdin:
        parts = line.split()
        if len(parts) < 3:
            continue
        op, ha, hb = parts[0], parts[1], parts[2]
        if op == "GE":
            sys.stdout.write(("1" if ge_limbs(parse_be(ha, 64), parse_be(hb, 64)) else "0") + "\n")
        elif op == "MUL":
            st, n = mul256(parse_be(ha, 32), parse_be(hb, 32))
            sys.stdout.write(f"{st} {be_hex(n[:N], N)} {be_hex(n[N:], N)}\n")
        elif op == "MULDIV":
            if len(parts) < 4:
                return 1
            st, q, rem, _n = muldiv256(parse_be(ha, 32), parse_be(hb, 32), parse_be(parts[3], 32))
            sys.stdout.write(f"{st} {be_hex(q, N)} {be_hex(rem, N)}\n")
        else:
            sys.stderr.write(f"unknown op {op}\n")
            return 1
        nvec += 1
    sys.stderr.write(f"BATCH_N={nvec} COMBA_NR_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_comba_nr.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
