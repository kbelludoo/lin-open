#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IEEE-754 binary64 FFT convolution 256x256->512 + Montgomery REDC 512/256.

FFT: 8-bit digits, length-64 Cooley-Tukey over complex binary64, round-to-nearest
carry in base 256. Not Fermat SS (F7), not FNT (2^64+1), not NTT, not Toom-2x7,
not RNS, not Comba, not Karatsuba.

Montgomery: R=2^512, N'=-m^{-1} mod R, t=REDC(n)=n R^{-1} mod m, r=REDC(t R2)
with R2=2^1024 mod m (sparse shift-sub, not of n). Even d via CRT with odd m.
Jebelean exact q of n-r (low-limb inverse, not Hensel-of-n, not Barrett, not
SRT, not Newton, not restoring of n). Python int for 8-bit FFT bins, 64x64->128,
and N' setup. EXPERIMENTAL."""
from __future__ import annotations

import math
import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8
RBITS = 512


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


def fft(a: list[complex], invert: bool = False) -> None:
    n = len(a)
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
        ang = math.tau / length * (-1 if invert else 1)
        wlen = complex(math.cos(ang), math.sin(ang))
        for i in range(0, n, length):
            w = 1 + 0j
            for k in range(length // 2):
                u = a[i + k]
                v = a[i + k + length // 2] * w
                a[i + k] = u + v
                a[i + k + length // 2] = u - v
                w *= wlen
        length <<= 1
    if invert:
        invn = 1.0 / n
        for i in range(n):
            a[i] *= invn


def digits8(a: list[int]) -> list[int]:
    src = zcopy(a, N)
    d = [0] * 64
    for i in range(32):
        lo, sh = divmod(8 * i, 64)
        d[i] = (src[lo] >> sh) & 255
    return d


def fft_mul(a: list[int], b: list[int]) -> list[int]:
    fa = [complex(x) for x in digits8(a)]
    fb = [complex(x) for x in digits8(b)]
    fft(fa)
    fft(fb)
    fc = [fa[i] * fb[i] for i in range(64)]
    fft(fc, invert=True)
    acc, carry = 0, 0
    for i in range(64):
        v = int(round(fc[i].real)) + carry
        if v < 0:
            raise RuntimeError("fft neg")
        acc |= (v & 255) << (8 * i)
        carry = v >> 8
    if carry:
        raise RuntimeError("fft leftover")
    return le_limbs(acc, N512)


def shl1(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 1) | c
        out[i] = t & MASK64
        c = t >> 64
    if c:
        out.append(c)
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


def add_limbs(a: list[int], b: list[int]) -> list[int]:
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


def inv64(a: int) -> int:
    if a & 1 == 0:
        raise RuntimeError("even inv")
    x = 1
    for _ in range(6):
        x = (x * (2 - a * x)) & MASK64
    return x


def nprime8(m: list[int]) -> list[int]:
    mv = limbs_u(zcopy(m, N))
    np = (-pow(mv, -1, 1 << RBITS)) % (1 << RBITS)
    return le_limbs(np, N512)


def pow2_mod(m: list[int], exp: int) -> list[int]:
    rem = [1, 0, 0, 0, 0]
    dext = zcopy(m, 5)
    for _ in range(exp):
        rem = shl1(rem)
        if len(rem) > 5:
            rem = rem[:5]
        if ge_limbs(rem, dext):
            rem = sub_n(rem, dext)
    return rem[:N]


def redc512(t: list[int], m: list[int], np: list[int]) -> list[int]:
    mw = mul_nm(zcopy(t, N512), zcopy(np, N512))[:N512]
    s = add_limbs(zcopy(t, N512), mul_nm(mw, zcopy(m, N)))
    hi = s[N512:]
    while len(hi) < N:
        hi.append(0)
    dext = zcopy(m, len(hi))
    if ge_limbs(hi, dext):
        hi = sub_n(hi, dext)
    if any(hi[N:]):
        raise RuntimeError("redc wide")
    return zcopy(hi, N)


def mont_mod_odd(n: list[int], m: list[int]) -> list[int]:
    if is_one(m):
        return [0] * N
    np = nprime8(m)
    t = redc512(zcopy(n, N512), m, np)
    r2 = pow2_mod(m, 1024)
    prod = mul_nm(t, r2)
    return redc512(zcopy(prod, N512), m, np)


def ctz_int(v: int) -> int:
    if v == 0:
        return 256
    s = 0
    while (v & 1) == 0:
        s += 1
        v >>= 1
    return s


def shr_limbs(x: list[int], s: int) -> list[int]:
    if s == 0:
        return zcopy(x)
    out = [0] * len(x)
    w, b = divmod(s, 64)
    for i in range(len(x) - w):
        v = x[i + w] >> b
        if b and i + w + 1 < len(x):
            v |= (x[i + w + 1] << (64 - b)) & MASK64
        out[i] = v & MASK64
    return out


def submul(acc: list[int], off: int, qi: int, dd: list[int]) -> None:
    cy = 0
    for j, dv in enumerate(dd):
        p = qi * (dv & MASK64) + cy
        t = acc[off + j] - (p & MASK64)
        if t < 0:
            acc[off + j] = t + (1 << 64)
            cy = (p >> 64) + 1
        else:
            acc[off + j] = t
            cy = p >> 64
    k = off + len(dd)
    while cy:
        if k >= len(acc):
            raise RuntimeError("jebelean cy")
        t = acc[k] - cy
        if t < 0:
            acc[k] = t + (1 << 64)
            cy = 1
            k += 1
        else:
            acc[k] = t
            cy = 0


def jebelean_q(nn: list[int], d: list[int]) -> list[int]:
    dv = limbs_u(zcopy(d, N))
    s = ctz_int(dv)
    acc = shr_limbs(zcopy(nn, N512), s)
    dd = shr_limbs(zcopy(d, N), s)
    inv = inv64(dd[0])
    q = [0] * N
    for i in range(N):
        qi = (acc[i] * inv) & MASK64
        q[i] = qi
        submul(acc, i, qi, dd)
    if any(acc):
        raise RuntimeError("jebelean leftover")
    return q


def inv_mod_2s(m: int, s: int) -> int:
    x = inv64(m & MASK64)
    mask = (1 << s) - 1
    if s <= 64:
        return x & mask
    x = (x * (2 - m * x)) & mask
    x = (x * (2 - m * x)) & mask
    x = (x * (2 - m * x)) & mask
    return x


def crt_even(n: list[int], d: list[int], s: int) -> list[int]:
    m = shr_limbs(d, s)
    r1 = mont_mod_odd(n, m)
    nv, mv = limbs_u(n), limbs_u(m)
    r0 = nv & ((1 << s) - 1)
    r1v = limbs_u(r1)
    inv = inv_mod_2s(mv, s)
    k = ((r0 - r1v) * inv) & ((1 << s) - 1)
    return le256(r1v + mv * k)


def montgomery_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
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
    s = ctz_int(dv)
    r = mont_mod_odd(n, d) if s == 0 else crt_even(n, d, s)
    if ge_limbs(zcopy(r, N512), zcopy(d, N512)):
        return -2, zq, zr
    nn, borrow = [0] * N512, 0
    re = zcopy(r, N512)
    for i in range(N512):
        t = n[i] - re[i] - borrow
        if t < 0:
            nn[i] = t + (1 << 64)
            borrow = 1
        else:
            nn[i] = t
            borrow = 0
    if borrow:
        return -2, zq, zr
    q = jebelean_q(nn, d)
    return 1, q, r


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
    qd = fft_mul(zcopy(q, N), zcopy(d, N))
    s, c = add512(qd, zcopy(r, N512))
    if c:
        return False
    dext = zcopy(d, N512)
    rext = zcopy(r, N512)
    return s == zcopy(n, N512) and not ge_limbs(rext, dext)


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, fft_mul(a, b)


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = montgomery_div(n, d)
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
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 fft vs python\n")
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
            sys.stderr.write("FAIL fft reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS fft_montgomery q*d+r==n ge512 fft_prod montgomery_redc jebelean_q\n")
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
    sys.stderr.write(f"BATCH_N={nvec} FFT_MONTGOMERY_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_fft_montgomery.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
