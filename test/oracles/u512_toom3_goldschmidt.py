#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Toom-3 256x256->512 + Goldschmidt 512/256.

Toom-3: 86-bit 3-way split, five eval products via 64x64->128,
Bodrato interpolation of <=180-bit coeffs, B-adic sum at 2^86.
Not 16-bit schoolbook, not Karatsuba 2-way, not CRT/Mersenne.

Goldschmidt: normalize d so Y in [2^255,2^256); F=2^257-Y
(implemented as t=2^256-Y then X,Y += (X,Y)*t >> 256);
eight Toom-3 256x256 iterations, then 512-bit ge so r<d.
Not restoring of n, not Barrett mu=2^512/d, not Knuth D, not Hensel.

Python int only for <=90-bit eval limbs, 64x64->128, and
<=180-bit interpolation. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8
MASK86 = (1 << 86) - 1


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


def split3(a: list[int]) -> tuple[int, int, int]:
    a0 = (a[0] & MASK64) | ((a[1] & 0x3FFFFF) << 64)
    a1 = ((a[1] >> 22) | ((a[2] & ((1 << 44) - 1)) << 42)) & MASK86
    a2 = (a[2] >> 44) | ((a[3] & MASK64) << 20)
    return a0, a1, a2


def add_shifted(dst: list[int], src: int, bitoff: int) -> None:
    if src == 0:
        return
    sg, val = (1, src) if src > 0 else (-1, -src)
    limbs = []
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
        raise RuntimeError("toom3 underflow")


def toom3(a: list[int], b: list[int]) -> list[int]:
    a0, a1, a2 = split3(a)
    b0, b1, b2 = split3(b)
    v0, vinf = mul_small(a0, b0), mul_small(a2, b2)
    v1 = mul_small(a0 + a1 + a2, b0 + b1 + b2)
    vm1 = mul_small(a0 - a1 + a2, b0 - b1 + b2)
    v2 = mul_small(a0 + 2 * a1 + 4 * a2, b0 + 2 * b1 + 4 * b2)
    c0, c4 = v0, vinf
    c2 = (v1 + vm1) // 2 - c0 - c4
    odd = (v1 - vm1) // 2
    c3 = ((v2 - c0 - 4 * c2 - 16 * c4) // 2 - odd) // 3
    c1 = odd - c3
    r = [0] * 9
    add_shifted(r, c0, 0)
    add_shifted(r, c1, 86)
    add_shifted(r, c2, 172)
    add_shifted(r, c3, 258)
    add_shifted(r, c4, 344)
    if r[8]:
        raise RuntimeError("toom3 leftover")
    return r[:N512]


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


def shl_limbs(x: list[int], s: int) -> list[int]:
    if s == 0:
        return list(x)
    nw, rb = s // 64, s % 64
    out = [0] * (len(x) + nw + 1)
    for i, v in enumerate(x):
        t = (v & MASK64) << rb
        out[i + nw] |= t & MASK64
        out[i + nw + 1] |= t >> 64
    return out


def chunk256(x: list[int], k: int) -> list[int]:
    return zcopy(x[k * N : k * N + N], N)


def mul_wide_256(x: list[int], t: list[int]) -> list[int]:
    """x (any limbs) * t (256-bit) via Toom-3 on each 256-bit chunk."""
    t = zcopy(t, N)
    nch = (len(x) + N - 1) // N
    acc = [0] * (len(x) + N + 4)
    for k in range(nch):
        pk = toom3(chunk256(x, k), t)
        carry = 0
        for i, v in enumerate(pk):
            j = k * N + i
            tot = acc[j] + v + carry
            acc[j] = tot & MASK64
            carry = tot >> 64
        j = k * N + len(pk)
        while carry:
            tot = acc[j] + carry
            acc[j] = tot & MASK64
            carry = tot >> 64
            j += 1
    return acc


def goldschmidt_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    # bit-length of 256-bit d via limbs (no 512-bit python)
    hi = 3
    while hi > 0 and d[hi] == 0:
        hi -= 1
    top = d[hi]
    s = 64 * (3 - hi) + (64 - top.bit_length() if top else 64)
    y = zcopy(shl_limbs(d, s), N)
    x = shl_limbs(n, s)
    two256 = [0] * N + [1]
    for _ in range(8):
        t = sub_n(two256, y + [0])  # 2^256 - Y, 5 limbs possible
        t = zcopy(t, N)
        yt = toom3(y, t)
        ysum = add_n(y, yt[N:])
        if any(ysum[N:]):
            y = [0] * N  # Y reached 2^256 (1.0); stop
            xt = mul_wide_256(x, t)
            x = add_n(x, xt[N:])
            break
        y = zcopy(ysum, N)
        xt = mul_wide_256(x, t)
        x = add_n(x, xt[N:])
    while len(x) > 1 and x[-1] == 0:
        x.pop()
    # Y=UMAX makes t=1 and (Y*t)>>256=0, so X += X>>256 can set bit 512
    # even when true q fits. Clamp; ge corrections then either land on
    # q<=UMAX or inc256-overflow to -2.
    q = zcopy(x[N:], N)
    if any(v != 0 for v in x[N + N :]):
        q = [MASK64] * N
    qd = toom3(q, d)
    dext = d + [0] * N
    corr = 0
    while not ge_limbs(n, qd):
        if not dec256(q):
            return -2, zq, zr
        qd = sub_n(qd, dext)
        corr += 1
        if corr > 16:
            return -2, zq, zr
    nd = add_n(qd, dext)
    while ge_limbs(n, nd):
        if not inc256(q):
            return -2, zq, zr
        qd = zcopy(nd, N512)
        nd = add_n(qd, dext)
        corr += 1
        if corr > 16:
            return -2, zq, zr
    r = zcopy(sub_n(n, qd), N)
    return 1, q, r


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = toom3(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, toom3(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = goldschmidt_div(n, d)
    if st2 == 1 and not identity512(n, q, d, r):
        return -2, q, r, n
    return st2, q, r, n


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
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 toom3 vs python\n")
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
            sys.stderr.write("FAIL toom3 reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS toom3_goldschmidt q*d+r==n ge512 toom3_prod goldschmidt\n")
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
    sys.stderr.write(f"BATCH_N={nvec} TOOM3_GOLDSCHMIDT_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_toom3_goldschmidt.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
