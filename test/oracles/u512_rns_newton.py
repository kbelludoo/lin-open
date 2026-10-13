#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RNS 256x256->512 + Newton-Raphson reciprocal 512/256.

RNS: 17 pairwise coprime 32-bit primes (product 544 bits > 2^512),
reduce each operand mod m_i, pointwise 32x32->64, Garner mixed-radix
CRT into 64-bit limbs. Not schoolbook, not Karatsuba, not Toom-3..10,
not NTT, not FNT, not Comba, not CRT/Mersenne (2^256 and 2^256-1).

Newton-Raphson: seed v=2^(512-bitlen(d)); ten iterations
v := 2v - ((d*v*v)>>512) with 64x64->128 products; q=(n*v)>>512;
512-bit ge so r<d. Not Goldschmidt (no dual N,D iterate), not Hensel
mod 2^256, not Barrett mu from sparse 2^512, not SRT, not restoring
of n, not Knuth D, not Burnikel-Ziegler. Python int only for 32-bit
residues, 32-bit egcd, and 64x64->128. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512, NW = 4, 8, 10
MASK32 = 0xFFFFFFFF
MODS = (
    4294967291, 4294967279, 4294967231, 4294967197, 4294967189,
    4294967161, 4294967143, 4294967111, 4294967087, 4294967029,
    4294966997, 4294966981, 4294966943, 4294966927, 4294966909,
    4294966877, 4294966829,
)
NM = 17


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


def sub_as(a: list[int], b: list[int]) -> tuple[list[int], int]:
    n = max(len(a), len(b))
    out, br = [0] * n, 0
    for i in range(n):
        av, bv = a[i] if i < len(a) else 0, b[i] if i < len(b) else 0
        t = av - bv - br
        if t < 0:
            out[i] = t + (1 << 64)
            br = 1
        else:
            out[i] = t
            br = 0
    return out, br


def egcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x, y = egcd(b, a % b)
    return g, y, x - (a // b) * y


def invmod(a: int, m: int) -> int:
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise RuntimeError("no inv")
    return x % m


def mod_u256(w: list[int], m: int) -> int:
    r32 = (1 << 32) % m
    r64 = (r32 * r32) % m
    acc = 0
    for i in range(3, -1, -1):
        lo, hi = w[i] & MASK32, w[i] >> 32
        acc = (acc * r64 + (hi * r32 + lo) % m) % m
    return acc


def add_mul_small(dst: list[int], src: list[int], k: int) -> None:
    carry = 0
    for i, v in enumerate(src):
        lo, hi = mul64(v, k)
        t = dst[i] + lo + carry
        dst[i] = t & MASK64
        carry = hi + (t >> 64)
    i = len(src)
    while carry:
        t = dst[i] + carry
        dst[i] = t & MASK64
        carry = t >> 64
        i += 1


def rns_mul(a: list[int], b: list[int]) -> list[int]:
    aa, bb = zcopy(a, N), zcopy(b, N)
    rr = [0] * NM
    for i, m in enumerate(MODS):
        rr[i] = (mod_u256(aa, m) * mod_u256(bb, m)) % m
    u = [0] * NM
    u[0] = rr[0]
    for i in range(1, NM):
        acc, prod, m = rr[i], 1, MODS[i]
        for j in range(i):
            acc = (acc - u[j] * prod) % m
            prod = (prod * MODS[j]) % m
        u[i] = (acc * invmod(prod, m)) % m
    x, M = [0] * 9, [1] + [0] * 8
    for i in range(NM):
        add_mul_small(x, M, u[i])
        if i < NM - 1:
            nxt = [0] * 9
            add_mul_small(nxt, M, MODS[i])
            M = nxt
    if x[8]:
        raise RuntimeError("rns leftover")
    return x[:N512]


def mul_limbs(a: list[int], b: list[int]) -> list[int]:
    out = [0] * (len(a) + len(b) + 1)
    for i, av in enumerate(a):
        carry = 0
        for j, bv in enumerate(b):
            lo, hi = mul64(av, bv)
            t = out[i + j] + lo + carry
            out[i + j] = t & MASK64
            carry = hi + (t >> 64)
        k = i + len(b)
        while carry:
            t = out[k] + carry
            out[k] = t & MASK64
            carry = t >> 64
            k += 1
    return out


def shl1(x: list[int]) -> list[int]:
    out, c = [0] * (len(x) + 1), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 1) | c
        out[i] = t & MASK64
        c = t >> 64
    out[len(x)] = c
    return out


def shl_bits(x: list[int], s: int, nout: int) -> list[int]:
    if s == 0:
        return zcopy(x, nout)
    nw, rb = divmod(s, 64)
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


def newton_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    bl = 256 - clz256(d)
    v = shl_bits([1], 512 - bl, NW)
    for _ in range(10):
        tsh = mul_limbs(mul_limbs(d, v), v)[8:]
        nv, br = sub_as(shl1(v), tsh)
        v = [0] * NW if br else zcopy(nv, NW)
    qacc = mul_limbs(n, v)[8:16]
    if any(qacc[N:]):
        return -2, zq, zr
    q = zcopy(qacc, N)
    qd = rns_mul(q, d)
    dext = d + [0] * N
    corr = 0
    while not ge_limbs(n, qd):
        if not dec_u256(q):
            return -2, zq, zr
        qd = sub_n(qd, dext)
        corr += 1
        if corr > 512:
            return -2, zq, zr
    nd = add_n(qd, dext)
    while ge_limbs(n, nd):
        if not inc_u256(q):
            return -2, zq, zr
        qd = zcopy(nd, N512)
        nd = add_n(qd, dext)
        corr += 1
        if corr > 512:
            return -2, zq, zr
    r = zcopy(sub_n(n, qd), N)
    return 1, q, r


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = rns_mul(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, rns_mul(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = newton_div(n, d)
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
        sys.stderr.write("FAIL max^2 rns vs python\n")
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
            sys.stderr.write("FAIL rns reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS rns_newton q*d+r==n ge512 rns_prod newton\n")
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
    sys.stderr.write(f"BATCH_N={nvec} RNS_NEWTON_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_rns_newton.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
