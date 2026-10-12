#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unbalanced Toom-Cook 3x7 256x256->512 + Barrett mu=floor(2^768/d) 512/256.

Toom-3x7: 37-bit digits; a as three 3-digit groups (111-bit) times b as
seven digits (259-bit pad). Nine eval products at {0,±1,±2,±3,4,inf},
Lagrange interpolation of the degree-8 Cauchy polynomial. Not balanced
Toom-3..10, not SS/FNT/NTT, not RNS, not Comba, not Karatsuba.

Barrett-768: mu=floor(2^768/d) from sparse 2^768 restoring; q=(n*mu)>>768
plus 512-bit ge so r<d. Not mu=floor(2^512/d), not SRT, not Newton, not
Goldschmidt, not Knuth D, not Hensel, not restoring of n. Python int only
for <=94-bit Toom eval, Lagrange over Q, and 64x64->128. EXPERIMENTAL."""
from __future__ import annotations

import sys
from fractions import Fraction

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8
MASK37 = (1 << 37) - 1
XS = (0, 1, -1, 2, -2, 3, -3, 4)


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


def is_one(x: list[int]) -> bool:
    return bool(x) and x[0] == 1 and all(v == 0 for v in x[1:])


def ge_limbs(a: list[int], b: list[int]) -> bool:
    n = max(len(a), len(b))
    for j in range(n - 1, -1, -1):
        av, bv = a[j] if j < len(a) else 0, b[j] if j < len(b) else 0
        if av != bv:
            return av > bv
    return True


def get_bits(limbs: list[int], bit: int, width: int) -> int:
    lo, sh = divmod(bit, 64)
    val = (limbs[lo] >> sh) if lo < len(limbs) else 0
    if sh + width > 64 and lo + 1 < len(limbs):
        val |= (limbs[lo + 1] & MASK64) << (64 - sh)
    if sh + width > 128 and lo + 2 < len(limbs):
        val |= (limbs[lo + 2] & MASK64) << (128 - sh)
    return val & ((1 << width) - 1)


def split7(a: list[int]) -> list[int]:
    src = zcopy(a, N)
    return [get_bits(src, 37 * i, 37) for i in range(7)]


def poly_times_xm(p: list[int], s: int) -> list[int]:
    out = [0] * (len(p) + 1)
    for i, v in enumerate(p):
        out[i] -= v * s
        out[i + 1] += v
    return out


def interpolate(xs: tuple[int, ...], ys: list[int]) -> list[int]:
    n = len(xs)
    c = [Fraction(0) for _ in range(n)]
    for i in range(n):
        num, den = [1], 1
        for j in range(n):
            if i == j:
                continue
            num = poly_times_xm(num, xs[j])
            den *= xs[i] - xs[j]
        for k, a in enumerate(num):
            c[k] += Fraction(a * ys[i], den)
    out = []
    for x in c:
        if x.denominator != 1:
            raise RuntimeError("toom37 interp")
        out.append(int(x))
    return out


def eval_a(a0: int, a1: int, a2: int, t: int) -> int:
    return a0 + a1 * t + a2 * t * t


def eval_b(bs: list[int], t: int) -> int:
    s = 0
    for b in reversed(bs):
        s = s * t + b
    return s


def toom37_group(ad: list[int], bd: list[int]) -> list[int]:
    a0, a1, a2 = ad[0], ad[1], ad[2]
    c8 = a2 * bd[6]
    qs = []
    for t in XS:
        p = eval_a(a0, a1, a2, t) * eval_b(bd, t)
        qs.append(p - c8 * (t ** 8))
    cs = interpolate(XS, qs)
    cs.append(c8)
    return cs


def add_shifted(dst: list[int], src: int, bitoff: int) -> None:
    if src == 0:
        return
    if src < 0:
        raise RuntimeError("toom37 neg coeff")
    limbs = []
    val = src
    while val:
        limbs.append(val & MASK64)
        val >>= 64
    w, b = bitoff // 64, bitoff % 64
    if b:
        sh = [0] * (len(limbs) + 1)
        for i, v in enumerate(limbs):
            sh[i] |= (v << b) & MASK64
            sh[i + 1] |= v >> (64 - b)
        limbs = sh
    carry = 0
    for i, v in enumerate(limbs):
        t = dst[i + w] + v + carry
        dst[i + w] = t & MASK64
        carry = t >> 64
    k = w + len(limbs)
    while carry:
        t = dst[k] + carry
        dst[k] = t & MASK64
        carry = t >> 64
        k += 1


def toom37_mul(a: list[int], b: list[int]) -> list[int]:
    ad, bd = split7(zcopy(a, N)), split7(zcopy(b, N))
    groups = (ad[0:3], ad[3:6], [ad[6], 0, 0])
    r = [0] * 9
    for g, off in zip(groups, (0, 111, 222)):
        for k, c in enumerate(toom37_group(g, bd)):
            add_shifted(r, c, off + 37 * k)
    if r[8]:
        raise RuntimeError("toom37 leftover")
    return r[:N512]


def shl1(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 1) | c
        out[i] = t & MASK64
        c = t >> 64
    return out


def sub_n(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, borrow = [0] * n, 0
    for i in range(n):
        av, bv = a[i] if i < len(a) else 0, b[i] if i < len(b) else 0
        t = av - bv - borrow
        if t < 0:
            out[i] = t + (1 << 64)
            borrow = 1
        else:
            out[i] = t
            borrow = 0
    if borrow:
        raise RuntimeError("unsigned sub underflow")
    return out


def mul_nm(a: list[int], b: list[int]) -> list[int]:
    na, nb = len(a), len(b)
    p = [0] * (na + nb)
    for i in range(na):
        carry = 0
        for j in range(nb):
            t = p[i + j] + (a[i] & MASK64) * (b[j] & MASK64) + carry
            p[i + j] = t & MASK64
            carry = t >> 64
        k = i + nb
        while k < len(p) and carry:
            t = p[k] + carry
            p[k] = t & MASK64
            carry = t >> 64
            k += 1
        if carry:
            raise RuntimeError("mul leftover")
    return p


def mu_recip768(d: list[int]) -> list[int]:
    rem = [1] + [0] * 5
    mu = [0] * 12
    dext = zcopy(d, 6)
    for i in range(767, -1, -1):
        rem = shl1(rem)
        if ge_limbs(rem, dext):
            rem = sub_n(rem, dext)
            mu[i >> 6] |= 1 << (i & 63)
    return mu


def inc256(q: list[int]) -> bool:
    carry = 1
    for i in range(N):
        t = q[i] + carry
        q[i] = t & MASK64
        carry = t >> 64
        if carry == 0:
            return True
    return False


def dec256(q: list[int]) -> bool:
    borrow = 1
    for i in range(N):
        t = q[i] - borrow
        if t < 0:
            q[i] = t + (1 << 64)
            borrow = 1
        else:
            q[i] = t
            return True
    return False


def barrett768_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    mu = mu_recip768(d)
    prod = mul_nm(n, mu)
    if any(prod[16:]):
        return -2, zq, zr
    q = zcopy(prod[12:16], N)
    qd = toom37_mul(q, d)
    dext = d + [0] * N
    if ge_limbs(n, qd):
        r = sub_n(n, qd)
        corr = 0
        while ge_limbs(r, dext):
            r = sub_n(r, dext)
            if not inc256(q):
                return -2, zq, zr
            corr += 1
            if corr > 8:
                return -2, zq, zr
        if any(r[N:]):
            return -2, zq, zr
        return 1, q, zcopy(r, N)
    mag = sub_n(qd, n)
    corr = 0
    while True:
        if not dec256(q):
            return -2, zq, zr
        if ge_limbs(dext, mag):
            r = sub_n(dext, mag)
            if any(r[N:]):
                return -2, zq, zr
            return 1, q, zcopy(r, N)
        mag = sub_n(mag, dext)
        corr += 1
        if corr > 8:
            return -2, zq, zr


def add512(a: list[int], b: list[int]) -> tuple[list[int], int]:
    out, carry = [0] * N512, 0
    for i in range(N512):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) + (bv & MASK64) + carry
        out[i] = t & MASK64
        carry = t >> 64
    return out, carry


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = toom37_mul(zcopy(q, N), zcopy(d, N))
    s, c = add512(qd, zcopy(r, N512))
    if c:
        return False
    dext = zcopy(d, N512)
    rext = zcopy(r, N512)
    return s == zcopy(n, N512) and not ge_limbs(rext, dext)


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, toom37_mul(a, b)


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = barrett768_div(n, d)
    if st2 == 1 and not identity512(n, q, d, r):
        return -2, q, r, n
    return st2, q, r, n


def le256(v: int) -> list[int]:
    return [(int(v) >> (64 * i)) & MASK64 for i in range(N)]


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
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 toom37 vs python\n")
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
            sys.stderr.write("FAIL toom37 reconstruct\n")
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
            sys.stderr.write(f"FAIL random {xa} {xb} {xd} st={st}\n")
            fail = 1
            break
        if not identity512(nn, q, le256(xd), rem):
            sys.stderr.write("FAIL random identity\n")
            fail = 1
            break
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS toom37_barrett768 q*d+r==n ge512 toom37_prod barrett768\n")
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
    sys.stderr.write(f"BATCH_N={nvec} TOOM37_BARRETT768_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_toom37_barrett768.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
