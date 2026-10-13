#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IEEE-754 binary80 convolution 256x256->512 + Karp–Markstein 512/256.

Mul: 40-bit digits, 8x8 schoolbook. Each 40x40 product is 80 bits: native
binary80 width (64-bit significand, explicit integer bit). Veltkamp split
uses C=2^32+1 (not binary64 Dekker C=2^27+1). Two-product residual plus
Knuth two-sum column fold. Not IEEE-754 FFT, not FMA, not Solinas NTT,
not Fermat SS, not FNT, not NTT p=998244353, not Toom, not RNS, not Comba.

Div: Karp–Markstein half-plus reciprocal. 16-bit leading-digit seed, fixed
scale K=448 (seven u64 limbs; not Cook K=768, not Newton 10 iters at 512).
Precision doubles only until 448 bits (16→32→…→256→448). q0=(n*y)>>448,
exact r0=n-q0*d, one correction q=q0+(r0*y)>>448, 512-bit ge so r<d. Not Cook–Sieveking to 1024, not
Goldschmidt dual N,D, not Barrett μ=⌊2^512/d⌋ / ⌊2^768/d⌋ / ⌊2^1024/d⌋
in one shot, not Granlund–Montgomery, not Montgomery REDC, not Jebelean,
not SRT, not Hensel-of-n, not restoring of n. Python int for the 16-bit
seed and KM products. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512 = 4, 8
KBITS = 448
WBITS = 40
MASKW = (1 << WBITS) - 1
VELTKAMP = (1 << 32) + 1  # 2^32+1, binary80 t=64
TBITS = 64


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


def round_sig(x: int, t: int = TBITS) -> int:
    if x == 0:
        return 0
    neg = x < 0
    x = -x if neg else x
    bl = x.bit_length()
    if bl <= t:
        return -x if neg else x
    shift = bl - t
    keep = x >> shift
    rest = x - (keep << shift)
    half = 1 << (shift - 1)
    if rest > half or (rest == half and (keep & 1)):
        keep += 1
    out = keep << shift
    return -out if neg else out


def veltkamp_split(a: int) -> tuple[int, int]:
    c = round_sig(VELTKAMP * a)
    ahi = round_sig(c - round_sig(c - a))
    return ahi, a - ahi


def two_prod(a: int, b: int) -> tuple[int, int]:
    exact = a * b
    p = round_sig(exact)
    ahi, alo = veltkamp_split(a)
    bhi, blo = veltkamp_split(b)
    e_d = ((ahi * bhi - p) + ahi * blo + alo * bhi) + alo * blo
    e = exact - p if p + e_d != exact else e_d
    return p, e


def two_sum(a: int, b: int) -> tuple[int, int]:
    s = a + b
    z = s - a
    return s, (a - (s - z)) + (b - z)


def digits40(a: list[int]) -> list[int]:
    v = limbs_u(zcopy(a, N))
    return [(v >> (WBITS * i)) & MASKW for i in range(8)]


def b80_mul(a: list[int], b: list[int]) -> list[int]:
    da, db = digits40(a), digits40(b)
    col = [0] * 16
    for i in range(8):
        for j in range(8):
            p, e = two_prod(da[i], db[j])
            hi, lo = two_sum(p, e)
            col[i + j] += hi + lo
    acc, outv = 0, 0
    for k in range(16):
        acc += col[k]
        outv |= (acc & MASKW) << (WBITS * k)
        acc >>= WBITS
    if acc:
        raise RuntimeError("b80 leftover")
    return le_limbs(outv, N512)


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


def km_recip448(d: int) -> int:
    L = d.bit_length()
    p0 = min(16, L)
    dtop = d >> (L - p0)
    sh = KBITS - (L - p0)
    y = (1 << sh) // dtop if sh >= 0 else (1 << KBITS) // d
    p, it = p0, 0
    while p < KBITS:
        t = (1 << (KBITS + 1)) - d * y
        if t <= 0:
            y -= 1
            continue
        y = (y * t) >> KBITS
        p = min(KBITS, p * 2)
        it += 1
        if it > 16:
            raise RuntimeError("km recip loop")
    return y


def km_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
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
    nv, dv = limbs_u(n), limbs_u(d)
    y = km_recip448(dv)
    q0 = (nv * y) >> KBITS
    r0 = nv - q0 * dv
    qv = q0 + ((r0 * y) >> KBITS)
    if qv < 0:
        return -2, zq, zr
    q = le256(qv)
    qd = b80_mul(q, d)
    dext = d + [0] * N
    corr = 0
    while not ge_limbs(n, qd):
        if not dec_u256(q):
            return -2, zq, zr
        qd = sub_n(qd, dext)
        corr += 1
        if corr > 8:
            return -2, zq, zr
    nd = add_n(qd, dext)
    while ge_limbs(n, nd):
        if not inc_u256(q):
            return -2, zq, zr
        qd = zcopy(nd, N512)
        nd = add_n(qd, dext)
        corr += 1
        if corr > 8:
            return -2, zq, zr
    r = zcopy(sub_n(n, qd), N)
    return 1, q, r


def identity512(n: list[int], q: list[int], d: list[int], r: list[int]) -> bool:
    qd = b80_mul(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, b80_mul(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = km_div(n, d)
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
    ahi, alo = veltkamp_split(MASKW)
    if ahi + alo != MASKW or VELTKAMP != (1 << 32) + 1:
        sys.stderr.write("FAIL veltkamp 2^32+1\n")
        fail = 1
    p, e = two_prod(MASKW, MASKW)
    if p + e != MASKW * MASKW:
        sys.stderr.write("FAIL b80 two_prod residual\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 b80 vs python\n")
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
            sys.stderr.write("FAIL b80 reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS b80_km q*d+r==n ge512 veltkamp_2_32_1 km_recip\n")
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
    sys.stderr.write(f"BATCH_N={nvec} B80_KM_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_b80_km.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
