#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Toom-4 256x256->512 + Burnikel-Ziegler 512/256.

Toom-4: 64-bit 4-way split, seven eval products via 64x64->128,
Newton interpolation of <=140-bit coeffs, B-adic sum at 2^64.
Not 16-bit schoolbook, not Karatsuba 2-way, not Toom-3, not NTT,
not Comba, not CRT/Mersenne.

Burnikel-Ziegler: recursive D2n/1n of 8xu64 / 4xu64 (then 4/2, 2/1).
D3n/2n high-half quotient, at most two remainder add-backs, 512-bit ge
so r<d. Not restoring of n, not non-restoring, not SRT, not Barrett mu,
not Knuth D (digit q̂), not Goldschmidt, not Hensel. Python int only for
<=70-bit Toom eval, 64x64->128, <=140-bit interpolation, and 128/64 at
the BZ 2-by-1 leaf. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8


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


def zcopy(x: list[int], n: int) -> list[int]:
    out = [0] * n
    for i in range(min(n, len(x))):
        out[i] = x[i] & MASK64
    return out


def ge_limbs(a: list[int], b: list[int]) -> bool:
    n = max(len(a), len(b))
    for j in range(n - 1, -1, -1):
        av = a[j] if j < len(a) else 0
        bv = b[j] if j < len(b) else 0
        if av != bv:
            return av > bv
    return True


def cmp_limbs(a: list[int], b: list[int]) -> int:
    n = max(len(a), len(b))
    for j in range(n - 1, -1, -1):
        av = a[j] if j < len(a) else 0
        bv = b[j] if j < len(b) else 0
        if av != bv:
            return 1 if av > bv else -1
    return 0


def mul64(a: int, b: int) -> tuple[int, int]:
    t = (a & MASK64) * (b & MASK64)
    return t & MASK64, t >> 64


def addc(a: int, b: int, c: int) -> tuple[int, int]:
    t = (a & MASK64) + (b & MASK64) + c
    return t & MASK64, t >> 64


def mul128(a0: int, a1: int, b0: int, b1: int) -> list[int]:
    p00l, p00h = mul64(a0, b0)
    p01l, p01h = mul64(a0, b1)
    p10l, p10h = mul64(a1, b0)
    p11l, p11h = mul64(a1, b1)
    r1, c1 = addc(p00h, p01l, p10l)
    s, c2 = addc(p01h, p10h, p11l)
    r2, c3 = addc(s, c1, 0)
    return [p00l, r1, r2, (p11h + c2 + c3) & MASK64]


def mul_small(x: int, y: int) -> int:
    sg = 1
    if x < 0:
        sg, x = -sg, -x
    if y < 0:
        sg, y = -sg, -y
    r = mul128(x & MASK64, x >> 64, y & MASK64, y >> 64)
    return sg * (r[0] | (r[1] << 64) | (r[2] << 128) | (r[3] << 192))


def eval3(w: list[int], t: int) -> int:
    return w[0] + t * (w[1] + t * (w[2] + t * w[3]))


def add_shifted(dst: list[int], src: int, bitoff: int) -> None:
    if src == 0:
        return
    sg, val = (1, src) if src >= 0 else (-1, -src)
    limbs: list[int] = []
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
    if sg == 1:
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
        return
    borrow = 0
    for i in range(len(dst) - w):
        sv = limbs[i] if i < len(limbs) else 0
        t = dst[i + w] - sv - borrow
        if t < 0:
            dst[i + w] = t + (1 << 64)
            borrow = 1
        else:
            dst[i + w] = t
            borrow = 0
    if borrow:
        raise RuntimeError("toom4 underflow")


def toom4(a: list[int], b: list[int]) -> list[int]:
    aa, bb = zcopy(a, N), zcopy(b, N)
    pts = (0, 1, -1, 2, -2, 3)
    prods = [mul_small(eval3(aa, t), eval3(bb, t)) for t in pts]
    pinf = mul_small(aa[3], bb[3])
    ys = [p - pinf * (t ** 6) for t, p in zip(pts, prods)]
    xs, n = list(pts), 6
    dd = [list(ys)]
    for j in range(1, n):
        row = []
        for i in range(n - j):
            den = xs[i + j] - xs[i]
            num = dd[j - 1][i + 1] - dd[j - 1][i]
            q, r = divmod(num, den)
            if r:
                raise RuntimeError("inexact toom4 dd")
            row.append(q)
        dd.append(row)
    newton = [dd[j][0] for j in range(n)]
    poly = [newton[5]]
    for i in range(4, -1, -1):
        shifted, scaled = [0] + poly, [-xs[i] * v for v in poly] + [0]
        poly = [shifted[j] + scaled[j] for j in range(len(shifted))]
        poly[0] += newton[i]
    while len(poly) < 6:
        poly.append(0)
    r = [0] * 10
    for i, c in enumerate(poly[:6] + [pinf]):
        add_shifted(r, c, 64 * i)
    if any(r[8:]):
        raise RuntimeError("toom4 leftover")
    return r[:N512]


def mul_nn(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b))
    for i, av in enumerate(a):
        carry = 0
        for j, bv in enumerate(b):
            lo, hi = mul64(av, bv)
            t = out[i + j] + lo + carry
            out[i + j] = t & MASK64
            carry = hi + (t >> 64)
        k = i + len(b)
        while carry:
            if k >= len(out):
                out.append(0)
            t = out[k] + carry
            out[k] = t & MASK64
            carry = t >> 64
            k += 1
    return out


def add_nn(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, c = [0] * (n + 1), 0
    for i in range(n):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) + (bv & MASK64) + c
        out[i] = t & MASK64
        c = t >> 64
    out[n] = c
    return out


def sub_nn(a: list[int], b: list[int]) -> tuple[list[int], int]:
    n = max(len(a), len(b))
    out, br = [0] * n, 0
    for i in range(n):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) - (bv & MASK64) - br
        if t < 0:
            out[i] = t + (1 << 64)
            br = 1
        else:
            out[i] = t
            br = 0
    return out, br


def dec_n(q: list[int]) -> bool:
    br = 1
    for i in range(len(q)):
        t = q[i] - br
        if t < 0:
            q[i] = t + (1 << 64)
            br = 1
        else:
            q[i] = t
            return True
    return False


def d2n1n(a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
    n = len(b)
    a, b = zcopy(a, 2 * n), zcopy(b, n)
    if n == 1:
        q, r = divmod((a[1] << 64) | a[0], b[0])
        if q > MASK64:
            raise RuntimeError("bz q overflow n=1")
        return [q], [r]
    k = n // 2
    q1, s = d3n2n(a[k:4 * k], b)
    q0, r = d3n2n(a[0:k] + s, b)
    return q0 + q1, r


def d3n2n(a: list[int], b: list[int]) -> tuple[list[int], list[int]]:
    n = len(b) // 2
    a, b = zcopy(a, 3 * n), zcopy(b, 2 * n)
    a0, a1, a2 = a[0:n], a[n:2 * n], a[2 * n:3 * n]
    b0, b1 = b[0:n], b[n:2 * n]
    if cmp_limbs(a2, b1) < 0:
        qhat, rhat = d2n1n(a1 + a2, b1)
        rhat = zcopy(rhat, n)
    else:
        qhat = [MASK64] * n
        dif, br = sub_nn(a2, b1)
        if br:
            raise RuntimeError("bz A2<B1")
        sm = add_nn(a1, b1)
        rhat = zcopy(sm, n) + zcopy(add_nn(dif, [sm[n]]), n + 1)
    rnum = zcopy(a0, n) + zcopy(rhat, max(len(rhat), n))
    qb0 = mul_nn(qhat, b0)
    width = max(len(rnum), len(qb0), 2 * n + 2)
    r, br = sub_nn(zcopy(rnum, width), zcopy(qb0, width))
    g = 0
    while br:
        if not dec_n(qhat):
            raise RuntimeError("bz qhat underflow")
        sm = add_nn(r, b)
        r = zcopy(sm, width)
        br = 0 if sm[width] else 1
        g += 1
        if g > 4:
            raise RuntimeError("bz R corrections")
    return qhat, zcopy(r, 2 * n)


def nlz256(d: list[int]) -> int:
    for i in range(3, -1, -1):
        if d[i]:
            return 64 * (3 - i) + (64 - d[i].bit_length())
    return 256


def shl_n(x: list[int], s: int, nout: int) -> list[int]:
    if s == 0:
        return zcopy(x, nout)
    nw, rb = divmod(s, 64)
    out = [0] * nout
    for i, v in enumerate(x):
        t = (v & MASK64) << rb
        j = i + nw
        if j < nout:
            out[j] |= t & MASK64
        if j + 1 < nout:
            out[j + 1] |= t >> 64
    return out


def shr_n(x: list[int], s: int, nout: int) -> list[int]:
    if s == 0:
        return zcopy(x, nout)
    nw, rb = divmod(s, 64)
    out = [0] * nout
    for i, v in enumerate(x):
        j = i - nw
        if j >= 0:
            out[j] |= (v & MASK64) >> rb
        if rb and j - 1 >= 0:
            out[j - 1] |= ((v & MASK64) << (64 - rb)) & MASK64
    return out


def bz_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if all(v == 0 for v in d):
        return -1, zq, zr
    if cmp_limbs(n, d + [0] * N) < 0:
        return 1, zq, zcopy(n, N)
    if cmp_limbs(n, [0] * N + d) >= 0:
        return -2, zq, zr
    s = nlz256(d)
    q, r = d2n1n(shl_n(n, s, N512), shl_n(d, s, N))
    return 1, zcopy(q, N), zcopy(shr_n(r, s, N), N)


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = toom4(zcopy(q, N), zcopy(d, N))
    s = add_nn(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, toom4(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = bz_div(n, d)
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
        sys.stderr.write("FAIL max^2 toom4 vs python\n")
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
            sys.stderr.write("FAIL toom4 reconstruct\n")
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
        if not identity512(nn, q, le256(xd), rem):
            sys.stderr.write("FAIL random identity\n")
            fail = 1
            break
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS toom4_bz q*d+r==n ge512 toom4_prod bzdiv\n")
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
    sys.stderr.write(f"BATCH_N={nvec} TOOM4_BZ_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_toom4_bz.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
