#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Solinas NTT 256x256->512 + Granlund–Montgomery magic 512/256.

NTT: 16-bit digits, length-32, Solinas prime p=2^64-2^32+1 (not 998244353),
ω=2^18 (primitive 32nd root). Butterflies reduce with 2^64≡2^32-1, not
generic field code. Not Fermat SS (F7), not FNT (2^64+1), not IEEE-754 FFT,
not NTT p=998244353, not Toom-2x7, not RNS, not Comba, not Karatsuba.

Granlund–Montgomery: magic M=⌈2^p/d⌉ from nc=2^512-1-((2^512-1)%d), p>512
until 2^p%d <= 2^p-nc; add-indicator when M>=2^512; q=mulhi(M,n)>>s (plus n
when add). Shift p depends on d, not Barrett μ=⌊2^512/d⌋ / ⌊2^768/d⌋ /
⌊2^1024/d⌋. Not SRT, not Newton, not Jebelean, not Montgomery REDC, not
Hensel-of-n, not restoring of n. Python int for magic search, twiddles, and
64x64→128 Solinas products. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8
P = (1 << 64) - (1 << 32) + 1
OMEGA = 262144
INV32 = pow(32, P - 2, P)
NBITS = 512


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


def limbs_u(v: list[int]) -> int:
    x = 0
    for i, limb in enumerate(v):
        x |= (limb & MASK64) << (64 * i)
    return x


def le_limbs(v: int, n: int) -> list[int]:
    return [(int(v) >> (64 * i)) & MASK64 for i in range(n)]


def le256(v: int) -> list[int]:
    return le_limbs(v, N)


def solinas_reduce(x: int) -> int:
    if x < 0:
        raise RuntimeError("solinas neg")
    while x >= (1 << 64):
        lo = x & MASK64
        hi = x >> 64
        x = lo + (hi << 32) - hi
    while x >= P:
        x -= P
    return x


def mulmod(a: int, b: int) -> int:
    return solinas_reduce(a * b)


def ntt(a: list[int], invert: bool) -> None:
    n = 32
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    length = 2
    while length <= n:
        wlen = pow(OMEGA, n // length, P)
        if invert:
            wlen = pow(wlen, P - 2, P)
        half = length // 2
        for i in range(0, n, length):
            w = 1
            for k in range(half):
                u = a[i + k]
                v = mulmod(a[i + k + half], w)
                s = u + v
                d = u - v
                a[i + k] = s - P if s >= P else s
                a[i + k + half] = d + P if d < 0 else d
                w = mulmod(w, wlen)
        length <<= 1
    if invert:
        for i in range(n):
            a[i] = mulmod(a[i], INV32)


def digits16(a: list[int]) -> list[int]:
    src = zcopy(a, N)
    d = [0] * 32
    for i in range(16):
        lo, sh = divmod(16 * i, 64)
        d[i] = (src[lo] >> sh) & 65535
    return d


def ntt_mul(a: list[int], b: list[int]) -> list[int]:
    fa, fb = digits16(a), digits16(b)
    ntt(fa, False)
    ntt(fb, False)
    fc = [mulmod(fa[i], fb[i]) for i in range(32)]
    ntt(fc, True)
    acc, outv = 0, 0
    for i in range(32):
        if fc[i] > 68_717_379_600:
            raise RuntimeError("solinas coeff wrap")
        acc += fc[i]
        outv |= (acc & 65535) << (16 * i)
        acc >>= 16
    if acc:
        raise RuntimeError("solinas leftover")
    return le_limbs(outv, N512)


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


def add_n(a: list[int], b: list[int]) -> list[int]:
    n = max(len(a), len(b))
    out, carry = [0] * (n + 1), 0
    for i in range(n):
        av = a[i] if i < len(a) else 0
        bv = b[i] if i < len(b) else 0
        t = (av & MASK64) + (bv & MASK64) + carry
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


def shr_limbs(x: list[int], s: int) -> list[int]:
    if s == 0:
        return list(x)
    w, b = divmod(s, 64)
    out = [0] * len(x)
    for i in range(len(x) - w):
        v = x[i + w] >> b
        if b and i + w + 1 < len(x):
            v |= (x[i + w + 1] << (64 - b)) & MASK64
        out[i] = v & MASK64
    return out


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


def magicgu(d: int) -> tuple[int, int, int]:
    two_n = 1 << NBITS
    nc = (two_n - 1) - ((two_n - 1) % d)
    p = NBITS
    while True:
        p += 1
        rp = (1 << p) % d
        if rp <= ((1 << p) - nc):
            break
        if p > NBITS + d.bit_length() + 4:
            raise RuntimeError("gm search")
    rp = (1 << p) % d
    m = (1 << p) // d if rp == 0 else ((1 << p) + d - rp) // d
    s = p - NBITS
    add = 0
    if m >= two_n:
        m -= two_n
        add = 1
    return m, s, add


def gm_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    zq, zr = [0] * N, [0] * N
    n, d = zcopy(n, N512), zcopy(d, N)
    if is_zero(d):
        return -1, zq, zr
    if is_one(d):
        if any(n[N:]):
            return -2, zq, zr
        return 1, zcopy(n, N), zr
    if ge_limbs(n[N:], d):
        return -2, zq, zr
    dv = limbs_u(d)
    mag, s, add = magicgu(dv)
    ml = le_limbs(mag, 9)
    prod = mul_nm(n, ml)
    qh = prod[N512:]
    if add:
        qh = add_n(qh, n)
    qh = shr_limbs(qh, s)
    if any(qh[N:]):
        return -2, zq, zr
    q = zcopy(qh, N)
    qd = ntt_mul(q, d)
    dext = d + [0] * N
    corr = 0
    while not ge_limbs(n, qd):
        if not dec_u256(q):
            return -2, zq, zr
        qd = sub_n(qd, dext)
        corr += 1
        if corr > 4:
            return -2, zq, zr
    nd = add_n(qd, dext)
    while ge_limbs(n, nd):
        if not inc_u256(q):
            return -2, zq, zr
        qd = zcopy(nd, N512)
        nd = add_n(qd, dext)
        corr += 1
        if corr > 4:
            return -2, zq, zr
    r = zcopy(sub_n(n, qd), N)
    return 1, q, r


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = ntt_mul(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, ntt_mul(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = gm_div(n, d)
    if st2 == 1 and not identity512(n, q, d, r):
        return -2, q, r, n
    return st2, q, r, n


def expect_st(st: int, want: int, msg: str) -> int:
    if st != want:
        sys.stderr.write(f"FAIL {msg} status={st} want={want}\n")
        return 1
    return 0


def selftest() -> int:
    fail = 0
    if pow(OMEGA, 32, P) != 1 or pow(OMEGA, 16, P) == 1:
        sys.stderr.write("FAIL solinas omega\n")
        fail = 1
    if solinas_reduce((P - 1) * (P - 1)) != ((P - 1) * (P - 1)) % P:
        sys.stderr.write("FAIL solinas reduce\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 solinas vs python\n")
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
            sys.stderr.write("FAIL solinas reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS solinas_gm q*d+r==n ge512 solinas_prod gm_magic\n")
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
    sys.stderr.write(f"BATCH_N={nvec} SOLINAS_GM_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_solinas_gm.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
