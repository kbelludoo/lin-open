#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Karatsuba 256x256->512 + Barrett 512/256. 128-bit split, 64x64->128
only. mu=floor(2^512/d) from sparse 2^512; q=(n*mu)>>512 + 512-bit ge.
Not schoolbook, CRT, restoring-of-n, Knuth D, or Hensel. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N = 4
N512 = 8
N1024 = 16

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
    return x[0] == 1 and all(v == 0 for v in x[1:])

def ge_limbs(a: list[int], b: list[int]) -> bool:
    n = max(len(a), len(b))
    for j in range(n - 1, -1, -1):
        av = a[j] if j < len(a) else 0
        bv = b[j] if j < len(b) else 0
        if av > bv:
            return True
        if av < bv:
            return False
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

def add_into(dst: list[int], src: list[int], shift: int) -> None:
    carry = 0
    for i, v in enumerate(src):
        j = i + shift
        t = dst[j] + (v & MASK64) + carry
        dst[j] = t & MASK64
        carry = t >> 64
    k = shift + len(src)
    while carry:
        t = dst[k] + carry
        dst[k] = t & MASK64
        carry = t >> 64
        k += 1

def sub_from(dst: list[int], src: list[int], shift: int) -> None:
    borrow = 0
    for i in range(len(dst) - shift):
        sv = src[i] if i < len(src) else 0
        t = dst[i + shift] - sv - borrow
        if t < 0:
            dst[i + shift] = t + (1 << 64)
            borrow = 1
        else:
            dst[i + shift] = t
            borrow = 0
    if borrow:
        raise RuntimeError("karatsuba underflow")

def karatsuba256(a: list[int], b: list[int]) -> list[int]:
    z0 = mul128(a[0], a[1], b[0], b[1])
    z2 = mul128(a[2], a[3], b[2], b[3])
    sa0, c = addc(a[0], a[2], 0)
    sa1, sa2 = addc(a[1], a[3], c)
    sb0, c = addc(b[0], b[2], 0)
    sb1, sb2 = addc(b[1], b[3], c)
    z1f = mul128(sa0, sa1, sb0, sb1) + [0, 0]
    if sa2:
        add_into(z1f, [sb0, sb1, sb2], 2)
    if sb2:
        add_into(z1f, [sa0, sa1], 2)
    sub_from(z1f, z0, 0)
    sub_from(z1f, z2, 0)
    r = [0] * 9
    add_into(r, z0, 0)
    add_into(r, z1f, 2)
    add_into(r, z2, 4)
    if r[8]:
        raise RuntimeError("karatsuba leftover")
    return r[:N512]

def shl1(rem: list[int]) -> list[int]:
    out, carry = [0] * len(rem), 0
    for i, v in enumerate(rem):
        t = ((v & MASK64) << 1) | carry
        out[i] = t & MASK64
        carry = (v >> 63) & 1
    return out

def sub_n(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, borrow = [0] * n, 0
    for i in range(n):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
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

def mu_recip(d: list[int]) -> list[int]:
    rem = [1, 0, 0, 0, 0]
    mu = [0] * N512
    dext = d + [0]
    for i in range(511, -1, -1):
        rem = shl1(rem)
        if ge_limbs(rem, dext):
            rem = sub_n(rem, dext)
            mu[i >> 6] |= 1 << (i & 63)
    return mu

def mul512(a: list[int], b: list[int]) -> list[int]:
    p = [0] * N1024
    for i in range(N512):
        carry = 0
        for j in range(N512):
            t = p[i + j] + (a[i] & MASK64) * (b[j] & MASK64) + carry
            p[i + j] = t & MASK64
            carry = t >> 64
        k = i + N512
        while k < N1024 and carry:
            t = p[k] + carry
            p[k] = t & MASK64
            carry = t >> 64
            k += 1
        if carry:
            raise RuntimeError("mul512 leftover")
    return p

def add512(a: list[int], b: list[int]) -> tuple[list[int], int]:
    out, carry = [0] * N512, 0
    for i in range(N512):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) + (bv & MASK64) + carry
        out[i] = t & MASK64
        carry = t >> 64
    return out, carry

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
            borrow = 0
            return True
    return False

def barrett_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    mu = mu_recip(d)
    prod = mul512(n, mu)
    if any(prod[12:]):
        return -2, zq, zr
    q = zcopy(prod[8:12], N)
    qd = karatsuba256(q, d)
    dext = d + [0] * N
    if ge_limbs(n, qd):
        r = sub_n(n, qd)
        corr = 0
        while ge_limbs(r, dext):
            r = sub_n(r, dext)
            if not inc256(q):
                return -2, zq, zr
            corr += 1
            if corr > 3:
                return -2, zq, zr
        return 1, q, zcopy(r, N)
    mag = sub_n(qd, n)
    corr = 0
    while True:
        if not dec256(q):
            return -2, zq, zr
        if ge_limbs(dext, mag):
            r = sub_n(dext, mag)
            return 1, q, zcopy(r, N)
        mag = sub_n(mag, dext)
        corr += 1
        if corr > 3:
            return -2, zq, zr

def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = karatsuba256(q, d)
    s, c = add512(qd, r)
    if c:
        return False
    dext = d + [0] * N
    rext = r + [0] * N
    return s == n and not ge_limbs(rext, dext)

def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, karatsuba256(a, b)

def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    st, n = mul256(a, b)
    st2, q, r = barrett_div(n, d)
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
    a, b, d = le256(7), le256(9), le256(2)
    st, q, rem, n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if n[0] != 1 or n[4] != MASK64 - 1 or n[7] != MASK64:
        sys.stderr.write("FAIL max^2 karatsuba limbs\n")
        fail = 1
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 karatsuba vs python\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(1 << 255), le256(2), le256(3))
    fail |= expect_st(st, 1, "2^255*2/3")
    if q != [0x5555555555555555] * N or rem[0] != 1:
        sys.stderr.write("FAIL 2^255*2/3 pattern\n")
        fail = 1
    if not identity512(n, q, le256(3), rem):
        sys.stderr.write("FAIL identity 2^255*2/3\n")
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
            sys.stderr.write("FAIL karatsuba reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS karatsuba_barrett q*d+r==n ge512 karatsuba_prod barrett\n")
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
            sys.stdout.write(("1" if ge_limbs(A, B) else "0") + "\n")
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
    sys.stderr.write(f"BATCH_N={nvec} KARATSUBA_BARRETT_CONSENSUS\n")
    return 0

def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_karatsuba_barrett.py --self-test | --batch\n")
    return 2

if __name__ == "__main__":
    sys.exit(main())
