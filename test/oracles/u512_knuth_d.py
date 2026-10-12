#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Knuth Algorithm D (TAOCP Vol. 2 §4.3.1) for 512/256.

8 x uint32 = 256 bits, 16 x uint32 = 512 bits. Radix β = 2^32.
Schoolbook mul carry of acc+a*b fits exactly in uint64:
  (2^32-1) + (2^32-1)^2 + (2^32-1) = 2^64-1.

Division is normalized multi-limb long division with trial q̂ and
add-back — not restoring bit-serial (LIN / C11-16 / radix-2^8 /
radix-2^32 / rustc-64). Python int is used only for 32×32→64
products and the 64/32 trial q̂; never as a 512-bit value.

EXPERIMENTAL: FullMath width, not CRT/mulmod.
"""
from __future__ import annotations

import sys

MASK32 = 0xFFFFFFFF
BASE = 1 << 32
N256 = 8
N512 = 16


def parse_be(s: str, nbytes: int) -> list[int]:
    t = s.strip()
    if t.startswith(("0x", "0X")):
        t = t[2:]
    t = t.zfill(nbytes * 2)
    be = bytes.fromhex(t[-nbytes * 2 :])
    le = bytes(reversed(be))
    n = nbytes // 4
    out = [0] * n
    for i in range(n):
        out[i] = int.from_bytes(le[4 * i : 4 * i + 4], "little")
    return out


def be_hex(limbs: list[int], n: int) -> str:
    raw = bytearray(n * 4)
    for i in range(n):
        raw[4 * i : 4 * i + 4] = int(limbs[i] & MASK32).to_bytes(4, "little")
    return bytes(reversed(raw)).hex()


def is_zero(x: list[int]) -> bool:
    return all(v == 0 for v in x)


def ge_limbs(a: list[int], b: list[int]) -> bool:
    for j in range(len(a) - 1, -1, -1):
        if a[j] > b[j]:
            return True
        if a[j] < b[j]:
            return False
    return True


def nlz32(x: int) -> int:
    if x == 0:
        return 32
    n = 0
    if x <= 0x0000FFFF:
        n += 16
        x <<= 16
    if x <= 0x00FFFFFF:
        n += 8
        x <<= 8
    if x <= 0x0FFFFFFF:
        n += 4
        x <<= 4
    if x <= 0x3FFFFFFF:
        n += 2
        x <<= 2
    if x <= 0x7FFFFFFF:
        n += 1
    return n


def mul256(a: list[int], b: list[int]) -> tuple[int, list[int]]:
    n = [0] * N512
    leftover = 0
    for i in range(N256):
        carry = 0
        for j in range(N256):
            t = n[i + j] + a[i] * b[j] + carry
            n[i + j] = t & MASK32
            carry = t >> 32
        k = i + N256
        while k < N512 and carry:
            t = n[k] + carry
            n[k] = t & MASK32
            carry = t >> 32
            k += 1
        if carry:
            leftover = 1
    return (-2 if leftover else 1), n


def _shl(src: list[int], nwords: int, s: int, extra: bool) -> list[int]:
    out = [0] * (nwords + (1 if extra else 0))
    if s == 0:
        for i in range(nwords):
            out[i] = src[i]
        return out
    rs = 32 - s
    out[0] = (src[0] << s) & MASK32
    for i in range(1, nwords):
        out[i] = ((src[i] << s) | (src[i - 1] >> rs)) & MASK32
    if extra:
        out[nwords] = src[nwords - 1] >> rs
    return out


def _shr(src: list[int], m: int, s: int) -> list[int]:
    out = [0] * m
    if s == 0:
        for i in range(m):
            out[i] = src[i]
        return out
    rs = 32 - s
    for i in range(m - 1):
        out[i] = ((src[i] >> s) | (src[i + 1] << rs)) & MASK32
    out[m - 1] = src[m - 1] >> s
    return out


def knuth_d(u: list[int], v: list[int]) -> tuple[int, list[int], list[int]]:
    """Divide little-endian limbs u (n) by v (m>=1, v[-1]!=0). q has n-m+1 words."""
    n = len(u)
    m = len(v)
    q = [0] * (n - m + 1)
    if m == 1:
        k = 0
        for j in range(n - 1, -1, -1):
            t = k * BASE + u[j]
            qj = t // v[0]
            k = t - qj * v[0]
            q[j] = qj
        return 1, q, [k]
    s = nlz32(v[m - 1])
    vn = _shl(v, m, s, False)
    un = _shl(u, n, s, True)
    for j in range(n - m, -1, -1):
        tmp = un[j + m] * BASE + un[j + m - 1]
        qhat = tmp // vn[m - 1]
        rhat = tmp - qhat * vn[m - 1]
        while qhat >= BASE or qhat * vn[m - 2] > rhat * BASE + un[j + m - 2]:
            qhat -= 1
            rhat += vn[m - 1]
            if rhat >= BASE:
                break
        k = 0
        for i in range(m):
            p = qhat * vn[i]
            t = un[i + j] - k - (p & MASK32)
            un[i + j] = t & MASK32
            k = (p >> 32) - (t >> 32)
        t = un[j + m] - k
        un[j + m] = t & MASK32
        q[j] = qhat & MASK32
        if t < 0:
            q[j] -= 1
            k = 0
            for i in range(m):
                t = un[i + j] + vn[i] + k
                un[i + j] = t & MASK32
                k = t >> 32
            un[j + m] = (un[j + m] + k) & MASK32
    rem = _shr(un, m, s)
    return 1, q, rem


def div512(n: list[int], d: list[int]) -> tuple[int, list[int], list[int]]:
    q8 = [0] * N256
    r8 = [0] * N256
    if is_zero(d):
        return -1, q8, r8
    dext = d + [0] * N256
    if not ge_limbs(n, dext):
        return 1, q8, n[:N256]
    m = N256
    while m > 0 and d[m - 1] == 0:
        m -= 1
    nn = N512
    while nn > 0 and n[nn - 1] == 0:
        nn -= 1
    if nn == 0:
        return 1, q8, r8
    if nn < m:
        return 1, q8, n[:N256]
    st, q, rem = knuth_d(n[:nn], d[:m])
    if st != 1:
        return st, q8, r8
    if len(q) > N256:
        if any(w != 0 for w in q[N256:]):
            return -2, q8, r8
        q8 = q[:N256]
    else:
        q8[: len(q)] = q
    r8[: len(rem)] = rem
    return 1, q8, r8


def identity512(n: list[int], q: list[int], d: list[int], rem: list[int]) -> bool:
    st, qd = mul256(q, d)
    if st != 1:
        return False
    carry = 0
    for i in range(N512):
        ri = rem[i] if i < len(rem) else 0
        t = qd[i] + ri + carry
        qd[i] = t & MASK32
        carry = t >> 32
    if carry:
        return False
    if qd != n:
        return False
    dext = (d + [0] * N256)[:N512]
    rext = (list(rem) + [0] * N512)[:N512]
    return not ge_limbs(rext, dext)


def muldiv256(a: list[int], b: list[int], d: list[int]) -> tuple[int, list[int], list[int], list[int]]:
    st, n = mul256(a, b)
    zq, zr = [0] * N256, [0] * N256
    if st != 1:
        return st, zq, zr, n
    st, q, rem = div512(n, d)
    if st != 1:
        return st, q, rem, n
    if not identity512(n, q, d, rem):
        return -2, q, rem, n
    return 1, q, rem, n


def le256(v: int) -> list[int]:
    out = [0] * N256
    x = int(v)
    for i in range(N256):
        out[i] = x & MASK32
        x >>= 32
    return out


def limbs_u(v: list[int]) -> int:
    x = 0
    for i, limb in enumerate(v):
        x |= (limb & MASK32) << (32 * i)
    return x


def expect_st(st: int, want: int, msg: str) -> int:
    if st != want:
        sys.stderr.write(f"FAIL {msg} status={st} want={want}\n")
        return 1
    return 0


def selftest() -> int:
    fail = 0
    if MASK32 + MASK32 * MASK32 + MASK32 != (1 << 64) - 1:
        sys.stderr.write("FAIL carry does not fit u64\n")
        fail = 1
    a, b, d = le256(7), le256(9), le256(2)
    st, q, rem, _n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    a = [MASK32] * N256
    b = [MASK32] * N256
    st, n = mul256(a, b)
    fail |= expect_st(st, 1, "max*max")
    if n[0] != 1:
        sys.stderr.write("FAIL max^2 lo\n")
        fail = 1
    if n[8] != 0xFFFFFFFE or n[15] != MASK32:
        sys.stderr.write("FAIL max^2 hi limbs\n")
        fail = 1
    a = le256(1 << 255)
    b, d = le256(2), le256(3)
    st, q, rem, n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "2^255*2/3")
    if q != [0x55555555] * N256 or rem[0] != 1:
        sys.stderr.write("FAIL 2^255*2/3 pattern\n")
        fail = 1
    if not identity512(n, q, d, rem):
        sys.stderr.write("FAIL identity 2^255*2/3\n")
        fail = 1
    fail |= expect_st(muldiv256(le256(1), le256(1), le256(0))[0], -1, "d=0")
    fail |= expect_st(muldiv256(le256(1 << 255), le256(2), le256(1))[0], -2, "q overflow")
    st, q, rem, _n = muldiv256(le256(997000), le256(20000), le256(10997000))
    fail |= expect_st(st, 1, "getAmountOut")
    if limbs_u(q) != 1813:
        sys.stderr.write("FAIL 1813\n")
        fail = 1
    a, b, d = le256(2), le256(1 << 255), [MASK32] * N256
    st, q, rem, _n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "wrap-borrow")
    if q[0] != 1 or rem[0] != 1:
        sys.stderr.write("FAIL wrap-borrow words\n")
        fail = 1
    A = [0] * N512
    B = [MASK32] * N256 + [0] * N256
    A[8] = 1
    if not ge_limbs(A, B) or ge_limbs(B, A) or not ge_limbs(A, A):
        sys.stderr.write("FAIL ge512\n")
        fail = 1
    rng = 0xC0FFEE
    umax = (1 << 256) - 1
    for _ in range(64):
        rng = (rng * 6364136223846793005 + 1) & ((1 << 64) - 1)
        xa = (rng * 0x9E3779B97F4A7C15) & umax
        xb = (rng * 0xBF58476D1CE4E5B9) & umax
        xd = (rng * 0x94D049BB133111EB) & umax or 1
        st, q, rem, nn = muldiv256(le256(xa), le256(xb), le256(xd))
        prod = xa * xb
        qq, rr = divmod(prod, xd)
        if qq > umax:
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
    sys.stdout.write("SELFTEST_PASS knuth_d q*d+r==n ge512 carry_fits_u64\n")
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
            sys.stdout.write(f"{st} {be_hex(n[:N256], N256)} {be_hex(n[N256:], N256)}\n")
        elif op == "MULDIV":
            if len(parts) < 4:
                return 1
            a, b, d = parse_be(ha, 32), parse_be(hb, 32), parse_be(parts[3], 32)
            st, q, rem, _n = muldiv256(a, b, d)
            sys.stdout.write(f"{st} {be_hex(q, N256)} {be_hex(rem[:N256], N256)}\n")
        else:
            sys.stderr.write(f"unknown op {op}\n")
            return 1
        nvec += 1
    sys.stderr.write(f"BATCH_N={nvec} KNUTH_D_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_knuth_d.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
