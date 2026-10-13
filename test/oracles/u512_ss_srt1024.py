#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schönhage–Strassen 256x256->512 + SRT radix-1024 512/256.

SS: negacyclic Fermat FFT over F7=2^128+1, length-32, 16-bit digits
padded to 32. Weight ψ=2^4 (ψ^32≡-1), cyclic twiddle ω=2^8 (shift
butterflies, 2^128≡-1 fold). Not FNT over F6=2^64+1 (ω=16, length-32
cyclic), not NTT over p=998244353, not Toom-3..10, not RNS, not Comba.

SRT radix-1024: normalize D into [2^255,2^256); 10 bits of n per step;
quotient digits {-512..512} from thresholds ±D/2, ±3D/2, …, ±1023D/2
(Robertson); remainder may be negative; 512-bit ge corrections so r<d.
Not SRT radix-4..512, not restoring of n, not Newton-Raphson, not
Goldschmidt, not Barrett, not Knuth D, not Burnikel-Ziegler, not Hensel
mod 2^256. Python int only for 129-bit F7-fold, 128x128 pointwise, and
2^k twiddle shifts. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512, NW, FN = 4, 8, 16, 32
F7 = (1 << 128) + 1
MASK128 = (1 << 128) - 1
MAX_C = 16 * 65535 * 65535


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


def red(x: int) -> int:
    """x mod F7 in [0, F7) by 2^128 ≡ -1."""
    if x < 0:
        y = -red(-x)
        return y + F7 if y < 0 else y
    while x >= F7:
        x = (x & MASK128) - (x >> 128)
        if x < 0:
            x += F7
    return x


def mul_pow2(x: int, k: int) -> int:
    k %= 256
    x = red(x)
    if k == 0:
        return x
    if k < 128:
        return red(x << k)
    return red(-(x << (k - 128)))


def ss_fft(a: list[int], invert: bool) -> None:
    n = FN
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
        sh = 8 * (n // length)
        wlen_shift = (256 - sh) if invert else sh
        half = length // 2
        for i in range(0, n, length):
            w_shift = 0
            for k in range(half):
                u = a[i + k]
                v = mul_pow2(a[i + k + half], w_shift)
                a[i + k] = red(u + v)
                a[i + k + half] = red(u - v)
                w_shift = (w_shift + wlen_shift) % 256
        length <<= 1
    if invert:
        for i in range(n):
            a[i] = mul_pow2(a[i], 251)


def limbs_to_u16(x: list[int], nd: int) -> list[int]:
    out = [0] * nd
    for i, v in enumerate(x):
        v &= MASK64
        for k in range(4):
            j = 4 * i + k
            if j >= nd:
                break
            out[j] = (v >> (16 * k)) & 65535
    return out


def u16_to_limbs(ds: list[int], nlimbs: int) -> list[int]:
    out = [0] * nlimbs
    for i, v in enumerate(ds):
        li, sh = divmod(i, 4)
        if li >= nlimbs:
            break
        out[li] |= (v & 65535) << (16 * sh)
    return out


def ss_mul(a: list[int], b: list[int]) -> list[int]:
    A = limbs_to_u16(zcopy(a, N), 16) + [0] * 16
    B = limbs_to_u16(zcopy(b, N), 16) + [0] * 16
    Aw = [mul_pow2(A[i], 4 * i) for i in range(FN)]
    Bw = [mul_pow2(B[i], 4 * i) for i in range(FN)]
    ss_fft(Aw, False)
    ss_fft(Bw, False)
    C = [red(Aw[i] * Bw[i]) for i in range(FN)]
    ss_fft(C, True)
    Cu = [mul_pow2(C[i], (256 - 4 * i) % 256) for i in range(FN)]
    acc, out16 = 0, [0] * FN
    for i in range(FN):
        if Cu[i] > MAX_C:
            raise RuntimeError("ss coeff wrap")
        acc += Cu[i]
        out16[i] = acc & 65535
        acc >>= 16
    if acc:
        raise RuntimeError("ss leftover")
    return u16_to_limbs(out16, N512)


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


def shl10(x: list[int]) -> list[int]:
    out, c = [0] * len(x), 0
    for i, v in enumerate(x):
        t = ((v & MASK64) << 10) | c
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


def odd_thresholds(d: list[int]) -> list[list[int]]:
    half = shr1_u(d)
    odd, acc = [half], half
    for _ in range(511):
        acc = add_tc(acc, d)
        odd.append(acc)
    return odd


def select_q1024(t: list[int], odd: list[list[int]]) -> int:
    mag, sign = (neg_tc(t), -1) if is_neg(t) else (t, 1)
    lo, hi, found = 0, 511, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if ge_limbs(mag, odd[mid]):
            found = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return 0 if found < 0 else (found + 1) * sign


def kmul_d(qdig: int, d: list[int]) -> list[int]:
    a = abs(qdig)
    p = [0] * len(d)
    acc = list(d)
    while a:
        if a & 1:
            p = add_tc(p, acc)
        a >>= 1
        if a:
            acc = shl1(acc)
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


def srt1024_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
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
    while (top + 1) % 10:
        top += 1
    odd = odd_thresholds(dn)
    p, qacc = [0] * NW, [0] * NW
    while top >= 0:
        bits = 0
        for k in range(10):
            bits = (bits << 1) | getbit(nn, top - k)
        t = shl10(p)
        t[0] |= bits
        qdig = select_q1024(t, odd)
        p = sub_tc(t, kmul_d(qdig, dn))
        qacc = shl10(qacc)
        if qdig > 0:
            qacc = add_tc(qacc, [qdig] + [0] * (NW - 1))
        elif qdig < 0:
            qacc = sub_tc(qacc, [-qdig] + [0] * (NW - 1))
        top -= 10
    if is_neg(qacc) or any(qacc[N:]):
        return -2, zq, zr
    q = zcopy(qacc, N)
    qd = ss_mul(q, d)
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
    qd = ss_mul(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, ss_mul(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = srt1024_div(n, d)
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
        sys.stderr.write("FAIL max^2 ss vs python\n")
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
            sys.stderr.write("FAIL ss reconstruct\n")
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
    sys.stdout.write("SELFTEST_PASS ss_srt1024 q*d+r==n ge512 ss_prod srt1024\n")
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
    sys.stderr.write(f"BATCH_N={nvec} SS_SRT1024_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_ss_srt1024.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
