#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NTT 256x256->512 + SRT radix-4 512/256.

NTT: base-256, length-64, prime 998244353=119*2^23+1, ω=3^{(p-1)/64}.
Convolution coeffs <= 32*255^2 = 2080800 << p so INTT is the integer
product. Not 16-bit schoolbook, not Karatsuba, not Toom-3, not CRT/Mersenne.

SRT radix-4: normalize D into [2^255,2^256); 2 bits of n per step; quotient
digits {-2,-1,0,1,2} from thresholds ±D/2, ±3D/2 on the already-shifted
remainder (Robertson); remainder may be negative; 512-bit ge corrections
so r<d. Not restoring of n, not Barrett μ, not Knuth D, not Goldschmidt,
not Hensel. Python int only for 32-bit modular butterflies and 64-bit
limb add/shift. EXPERIMENTAL."""
from __future__ import annotations

import sys

MASK64 = 0xFFFFFFFFFFFFFFFF
UMAX = (1 << 256) - 1
N, N512, NW = 4, 8, 12
MOD = 998244353
OMEGA = pow(3, (MOD - 1) // 64, MOD)
INV64 = pow(64, MOD - 2, MOD)


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


def ntt(a: list[int], invert: bool) -> None:
    n = 64
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
        wlen = pow(OMEGA, n // length, MOD)
        if invert:
            wlen = pow(wlen, MOD - 2, MOD)
        half = length // 2
        for i in range(0, n, length):
            w = 1
            for k in range(half):
                u = a[i + k]
                v = a[i + k + half] * w % MOD
                a[i + k] = (u + v) % MOD
                a[i + k + half] = (u - v) % MOD
                w = w * wlen % MOD
        length <<= 1
    if invert:
        for i in range(n):
            a[i] = a[i] * INV64 % MOD


def limbs_to_bytes(x: list[int], nbytes: int) -> list[int]:
    raw = bytearray(nbytes)
    for i, v in enumerate(x):
        off = 8 * i
        if off >= nbytes:
            break
        chunk = int(v & MASK64).to_bytes(8, "little")
        take = min(8, nbytes - off)
        raw[off : off + take] = chunk[:take]
    return list(raw)


def bytes_to_limbs(bs: list[int], nlimbs: int) -> list[int]:
    raw = bytes(bs) + bytes(max(0, nlimbs * 8 - len(bs)))
    return [int.from_bytes(raw[8 * i : 8 * i + 8], "little") for i in range(nlimbs)]


def ntt_mul(a: list[int], b: list[int]) -> list[int]:
    A = limbs_to_bytes(zcopy(a, N), 32) + [0] * 32
    B = limbs_to_bytes(zcopy(b, N), 32) + [0] * 32
    ntt(A, False)
    ntt(B, False)
    C = [A[i] * B[i] % MOD for i in range(64)]
    ntt(C, True)
    acc, outb = 0, [0] * 64
    for i in range(64):
        if C[i] > 2_080_800:
            raise RuntimeError("ntt coeff wrap")
        acc += C[i]
        outb[i] = acc & 255
        acc >>= 8
    if acc:
        raise RuntimeError("ntt leftover")
    return bytes_to_limbs(outb, N512)


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


def select_q(t: list[int], d: list[int]) -> int:
    half = shr1_u(d)
    three = add_tc(d, half)
    if is_neg(t):
        nt = neg_tc(t)
        if ge_limbs(nt, three):
            return -2
        if ge_limbs(nt, half):
            return -1
        return 0
    if ge_limbs(t, three):
        return 2
    if ge_limbs(t, half):
        return 1
    return 0


def kmul_d(qdig: int, d: list[int]) -> list[int]:
    if qdig == 0:
        return [0] * len(d)
    if qdig == 1:
        return list(d)
    if qdig == 2:
        return shl1(d)
    if qdig == -1:
        return neg_tc(d)
    return neg_tc(shl1(d))


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


def srt4_div(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
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
    if (top + 1) & 1:
        top += 1
    p, qacc = [0] * NW, [0] * NW
    while top >= 0:
        bits = (getbit(nn, top) << 1) | getbit(nn, top - 1)
        t = shl2(p)
        t[0] |= bits
        qdig = select_q(t, dn)
        p = sub_tc(t, kmul_d(qdig, dn))
        qacc = shl2(qacc)
        if qdig > 0:
            qacc = add_tc(qacc, [qdig] + [0] * (NW - 1))
        elif qdig < 0:
            qacc = sub_tc(qacc, [-qdig] + [0] * (NW - 1))
        top -= 2
    if is_neg(qacc) or any(qacc[N:]):
        if any(qacc[N:]) and not is_neg(qacc):
            return -2, zq, zr
        if is_neg(qacc):
            return -2, zq, zr
    q = zcopy(qacc, N)
    qd = ntt_mul(q, d)
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
    qd = ntt_mul(zcopy(q, N), zcopy(d, N))
    s = add_n(qd, zcopy(r, N512))
    if any(s[N512:]):
        return False
    return zcopy(s, N512) == zcopy(n, N512) and not ge_limbs(zcopy(r, N512), zcopy(d, N512))


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    return 1, ntt_mul(zcopy(a, N), zcopy(b, N))


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    _st, n = mul256(a, b)
    st2, q, r = srt4_div(n, d)
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
    if pow(OMEGA, 64, MOD) != 1 or pow(OMEGA, 32, MOD) == 1:
        sys.stderr.write("FAIL ntt omega\n")
        fail = 1
    st, q, rem, n = muldiv256(le256(7), le256(9), le256(2))
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    st, n = mul256([MASK64] * N, [MASK64] * N)
    fail |= expect_st(st, 1, "max*max")
    if limbs_u(n) != UMAX * UMAX:
        sys.stderr.write("FAIL max^2 ntt vs python\n")
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
            sys.stderr.write("FAIL ntt reconstruct\n")
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
            sys.stderr.write(f"FAIL random {xa} {xb} {xd} st={st} q={limbs_u(q)} want={qq}\n")
            fail = 1
            break
        if not identity512(nn, q, le256(xd), rem):
            sys.stderr.write("FAIL random identity\n")
            fail = 1
            break
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS ntt_srt q*d+r==n ge512 ntt_prod srt4\n")
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
    sys.stderr.write(f"BATCH_N={nvec} NTT_SRT_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_ntt_srt.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
