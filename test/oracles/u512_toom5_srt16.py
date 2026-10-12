#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Toom-5 256x256->512 + SRT radix-16 512/256.

Toom-5: 52-bit 5-way split, nine eval products via 64x64->128,
Newton interpolation of <=120-bit coeffs, B-adic sum at 2^52.
Not schoolbook, not Karatsuba 2-way, not Toom-3, not Toom-4, not
NTT, not FNT, not Comba, not CRT/Mersenne.

SRT radix-16: normalize D into [2^255,2^256); 4 bits of n per step;
quotient digits {-8..8} from thresholds ±D/2, ±3D/2, …, ±15D/2
(Robertson); remainder may be negative; 512-bit ge corrections so r<d.
Not SRT radix-4, not SRT radix-8, not restoring of n, not non-restoring,
not Barrett, not Knuth D, not Goldschmidt, not Burnikel-Ziegler.
Python int only for <=60-bit Toom eval, 64x64->128, and <=120-bit
interpolation. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512, NW = 4, 8, 12
MASK52 = (1 << 52) - 1


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


def split52(w: list[int]) -> list[int]:
    w0, w1, w2, w3 = w[0] & MASK64, w[1] & MASK64, w[2] & MASK64, w[3] & MASK64
    return [
        w0 & MASK52,
        (w0 >> 52) | ((w1 & ((1 << 40) - 1)) << 12),
        (w1 >> 40) | ((w2 & ((1 << 28) - 1)) << 24),
        (w2 >> 28) | ((w3 & ((1 << 16) - 1)) << 36),
        w3 >> 16,
    ]


def eval4(w: list[int], t: int) -> int:
    return w[0] + t * (w[1] + t * (w[2] + t * (w[3] + t * w[4])))


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
        raise RuntimeError("toom5 underflow")


def toom5(a: list[int], b: list[int]) -> list[int]:
    aa, bb = split52(zcopy(a, N)), split52(zcopy(b, N))
    pts = (0, 1, -1, 2, -2, 3, -3, 4)
    prods = [mul_small(eval4(aa, t), eval4(bb, t)) for t in pts]
    pinf = mul_small(aa[4], bb[4])
    ys = [p - pinf * (t ** 8) for t, p in zip(pts, prods)]
    xs, n = list(pts), 8
    dd = [list(ys)]
    for j in range(1, n):
        row = []
        for i in range(n - j):
            den = xs[i + j] - xs[i]
            num = dd[j - 1][i + 1] - dd[j - 1][i]
            q, r = divmod(num, den)
            if r:
                raise RuntimeError("inexact toom5 dd")
            row.append(q)
        dd.append(row)
    newton = [dd[j][0] for j in range(n)]
    poly = [newton[7]]
    for i in range(6, -1, -1):
        shifted, scaled = [0] + poly, [-xs[i] * v for v in poly] + [0]
        poly = [shifted[j] + scaled[j] for j in range(len(shifted))]
        poly[0] += newton[i]
    while len(poly) < 8:
        poly.append(0)
    r = [0] * 12
    for i, c in enumerate(poly[:8] + [pinf]):
        add_shifted(r, c, 52 * i)
    if any(r[8:]):
        raise RuntimeError("toom5 leftover")
    return r[:N512]


def add_tc(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, carry = [0] * n, 0
    for i in range(n):
        av, bv = a[i] if i < len(a) else 0, b[i] if i < len(b) else 0
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


def shl1(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 1) | c
        out[i] = t & MASK64
        c = t >> 64
    return out


def shl2(x: list[int]) -> list[int]:
    return shl1(shl1(x))


def shl3(x: list[int]) -> list[int]:
    return shl1(shl2(x))


def shl4(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 4) | c
        out[i] = t & MASK64
        c = t >> 64
    return out


def shr1_u(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i in range(len(x) - 1, -1, -1):
        t = x[i] & MASK64
        out[i] = (t >> 1) | (c << 63)
        c = t & 1
    return out


def shl_bits(x: list[int], s: int, nout: int) -> list[int]:
    if s == 0:
        return zcopy(x, nout)
    nw, rb = s // 64, s % 64
    out = [0] * nout
    for i, v in enumerate(x):
        t = (v & MASK64) << rb
        j = i + nw
        if j < nout:
            out[j] |= t & MASK64
        if rb and j + 1 < nout:
            out[j + 1] |= t >> 64
    return out


def clz256(d: list[int]) -> int:
    for i in range(3, -1, -1):
        if d[i]:
            return 64 * (3 - i) + (64 - d[i].bit_length())
    return 256


def getbit(x: list[int], pos: int) -> int:
    if pos < 0:
        return 0
    li, b = divmod(pos, 64)
    if li >= len(x):
        return 0
    return (x[li] >> b) & 1


def select_q16(t: list[int], d: list[int]) -> int:
    half = shr1_u(d)
    odd = [half]
    acc = half
    for _ in range(7):
        acc = add_tc(acc, d)
        odd.append(acc)
    mag, sign = (neg_tc(t), -1) if is_neg(t) else (t, 1)
    for i in range(7, -1, -1):
        if ge_limbs(mag, odd[i]):
            return (i + 1) * sign
    return 0


def kmul_d(qdig: int, d: list[int]) -> list[int]:
    a = abs(qdig)
    if a == 0:
        p = [0] * len(d)
    elif a == 1:
        p = list(d)
    elif a == 2:
        p = shl1(d)
    elif a == 3:
        p = add_tc(shl1(d), d)
    elif a == 4:
        p = shl2(d)
    elif a == 5:
        p = add_tc(shl2(d), d)
    elif a == 6:
        p = add_tc(shl2(d), shl1(d))
    elif a == 7:
        p = sub_tc(shl3(d), d)
    else:
        p = shl3(d)
    return neg_tc(p) if qdig < 0 else p


def inc_u256(q: list[int]) -> bool:
    carry = 1
    for i in range(N):
        t = q[i] + carry
        q[i] = t & MASK64
        carry = t >> 64
        if carry == 0:
            return True
    return False


def dec_u256(q: list[int]) -> bool:
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


def add_n(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, carry = [0] * (n + 1), 0
    for i in range(n):
        av, bv = a[i] if i < len(a) else 0, b[i] if i < len(b) else 0
        t = av + bv + carry
        out[i] = t & MASK64
        carry = t >> 64
    out[n] = carry
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


def srt16_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    lz = clz256(d)
    dn = shl_bits(d, lz, NW)
    nn = shl_bits(n, lz, NW)
    top = 511 + lz
    while (top + 1) % 4:
        top += 1
    p, qacc = [0] * NW, [0] * NW
    while top >= 0:
        bits = ((getbit(nn, top) << 3) | (getbit(nn, top - 1) << 2)
                | (getbit(nn, top - 2) << 1) | getbit(nn, top - 3))
        t = shl4(p)
        t[0] |= bits
        qdig = select_q16(t, dn)
        p = sub_tc(t, kmul_d(qdig, dn))
        qacc = shl4(qacc)
        if qdig > 0:
            qacc = add_tc(qacc, [qdig] + [0] * (NW - 1))
        elif qdig < 0:
            qacc = sub_tc(qacc, [-qdig] + [0] * (NW - 1))
        top -= 4
    if is_neg(qacc) or any(qacc[N:]):
        return -2, zq, zr
    q = zcopy(qacc, N)
    qd = toom5(q, d)
    dext = d + [0] * N
    corr = 0
    while not ge_limbs(n, qd):
        if not dec_u256(q):
            return -2, zq, zr
        qd = sub_n(qd, dext)
        corr += 1
        if corr > 16:
            return -2, zq, zr
    nd = add_n(qd, dext)
    while ge_limbs(n, nd):
        if not inc_u256(q):
            return -2, zq, zr
        qd = zcopy(nd, N512)
        nd = add_n(qd, dext)
        corr += 1
        if corr > 16:
            return -2, zq, zr
    r = zcopy(sub_n(n, qd), N)
    return 1, q, r


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = toom5(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, toom5(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = srt16_div(n, d)
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
        sys.stderr.write("FAIL max^2 toom5 vs python\n")
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
            sys.stderr.write("FAIL toom5 reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS toom5_srt16 q*d+r==n ge512 toom5_prod srt16\n")
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
    sys.stderr.write(f"BATCH_N={nvec} TOOM5_SRT16_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_toom5_srt16.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
