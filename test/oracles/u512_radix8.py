#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Python radix-2^8 schoolbook (not TCB, stdlib only).
32 bytes = 256 bits, 64 bytes = 512 bits.
Carry of acc + a*b fits exactly in u16:
  (2^8-1) + (2^8-1)^2 + (2^8-1) = 65535 = 2^16-1.
Independent of LIN 16-bit, C11 radix-2^32, rustc radix-2^64, and
CPython 30-bit native digits. Never uses Python int for the 512-bit
product: only u8×u8 schoolbook, restoring div, and 512-bit ge.
EXPERIMENTAL: FullMath width, not CRT/mulmod.
"""
from __future__ import annotations

import sys

U8 = 255


def parse_be(s: str, n: int) -> bytearray:
    t = s.strip()
    if t.startswith(("0x", "0X")):
        t = t[2:]
    t = t.zfill(n * 2)
    be = bytes.fromhex(t[-n * 2 :])
    return bytearray(reversed(be))


def be_hex(le: bytes, n: int) -> str:
    return bytes(reversed(le[:n])).hex()


def is_zero(x: bytes) -> bool:
    return all(b == 0 for b in x)


def ge_bytes(a: bytes, b: bytes) -> bool:
    for j in range(len(a) - 1, -1, -1):
        if a[j] > b[j]:
            return True
        if a[j] < b[j]:
            return False
    return True


def mul256(a: bytes, b: bytes) -> tuple[int, bytearray]:
    n = bytearray(64)
    leftover = 0
    for i in range(32):
        carry = 0
        for j in range(32):
            k = i + j
            t = n[k] + a[i] * b[j] + carry
            n[k] = t & U8
            carry = t >> 8
        k = i + 32
        while k < 64 and carry:
            t = n[k] + carry
            n[k] = t & U8
            carry = t >> 8
            k += 1
        if carry:
            leftover = 1
    return (-2 if leftover else 1), n


def div512(n: bytes, d: bytes) -> tuple[int, bytearray, bytearray]:
    q = bytearray(32)
    rem = bytearray(64)
    if is_zero(d):
        return -1, q, rem
    for bit in range(511, -1, -1):
        limb, pos = bit >> 3, bit & 7
        carry = (n[limb] >> pos) & 1
        for j in range(64):
            t = rem[j] * 2 + carry
            rem[j] = t & U8
            carry = t >> 8
        if carry:
            return -2, q, rem
        dext = bytearray(64)
        dext[:32] = d
        if ge_bytes(rem, dext):
            if bit >= 256:
                return -2, q, rem
            q[limb] |= 1 << pos
            borrow = 0
            for j in range(64):
                dj = (d[j] if j < 32 else 0) + borrow
                if rem[j] < dj:
                    rem[j] = rem[j] + 256 - dj
                    borrow = 1
                else:
                    rem[j] = rem[j] - dj
                    borrow = 0
    return 1, q, rem


def identity512(n: bytes, q: bytes, d: bytes, rem: bytes) -> bool:
    st, qd = mul256(q, d)
    if st != 1:
        return False
    carry = 0
    for i in range(64):
        t = qd[i] + rem[i] + carry
        qd[i] = t & U8
        carry = t >> 8
    if carry:
        return False
    if qd != n:
        return False
    dext = bytearray(64)
    dext[:32] = d
    return not ge_bytes(rem, dext)


def muldiv256(a: bytes, b: bytes, d: bytes) -> tuple[int, bytearray, bytearray, bytearray]:
    st, n = mul256(a, b)
    if st != 1:
        return st, bytearray(32), bytearray(64), n
    st, q, rem = div512(n, d)
    if st != 1:
        return st, q, rem, n
    if not identity512(n, q, d, rem):
        return -2, q, rem, n
    return 1, q, rem, n


def le32(v: int) -> bytearray:
    return bytearray(int(v).to_bytes(32, "little"))


def expect_st(st: int, want: int, msg: str) -> int:
    if st != want:
        sys.stderr.write(f"FAIL {msg} status={st} want={want}\n")
        return 1
    return 0


def selftest() -> int:
    fail = 0
    if U8 + U8 * U8 + U8 != 65535:
        sys.stderr.write("FAIL carry does not fit u16\n")
        fail = 1
    a, b, d = le32(7), le32(9), le32(2)
    st, q, rem, _n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "7*9/2")
    if q[0] != 31 or rem[0] != 1:
        sys.stderr.write("FAIL 7*9/2 words\n")
        fail = 1
    a = bytearray(b"\xff" * 32)
    b = bytearray(b"\xff" * 32)
    st, n = mul256(a, b)
    fail |= expect_st(st, 1, "max*max")
    if n[0] != 1:
        sys.stderr.write("FAIL max^2 lo\n")
        fail = 1
    if n[32] != 0xFE or n[63] != 0xFF:
        sys.stderr.write("FAIL max^2 hi bytes\n")
        fail = 1
    a = bytearray(32)
    a[31] = 0x80
    b, d = le32(2), le32(3)
    st, q, rem, n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "2^255*2/3")
    if q != bytearray(b"\x55" * 32) or rem[0] != 1:
        sys.stderr.write("FAIL 2^255*2/3 pattern\n")
        fail = 1
    if not identity512(n, q, d, rem):
        sys.stderr.write("FAIL identity 2^255*2/3\n")
        fail = 1
    fail |= expect_st(muldiv256(le32(1), le32(1), le32(0))[0], -1, "d=0")
    a = bytearray(32)
    a[31] = 0x80
    fail |= expect_st(muldiv256(a, le32(2), le32(1))[0], -2, "q overflow")
    st, q, rem, _n = muldiv256(le32(997000), le32(20000), le32(10997000))
    fail |= expect_st(st, 1, "getAmountOut")
    if int.from_bytes(q, "little") != 1813:
        sys.stderr.write("FAIL 1813\n")
        fail = 1
    a, b, d = le32(2), bytearray(32), bytearray(b"\xff" * 32)
    b[31] = 0x80
    st, q, rem, _n = muldiv256(a, b, d)
    fail |= expect_st(st, 1, "wrap-borrow")
    if q[0] != 1 or rem[0] != 1:
        sys.stderr.write("FAIL wrap-borrow words\n")
        fail = 1
    A = bytearray(64)
    B = bytearray(64)
    A[32] = 1
    B[:32] = b"\xff" * 32
    if not ge_bytes(A, B) or ge_bytes(B, A) or not ge_bytes(A, A):
        sys.stderr.write("FAIL ge512\n")
        fail = 1
    if fail:
        return 1
    sys.stdout.write("SELFTEST_PASS radix8 q*d+r==n ge512 carry_fits_u16\n")
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
            sys.stdout.write(("1" if ge_bytes(A, B) else "0") + "\n")
        elif op == "MUL":
            a, b = parse_be(ha, 32), parse_be(hb, 32)
            st, n = mul256(a, b)
            sys.stdout.write(f"{st} {be_hex(n[:32], 32)} {be_hex(n[32:], 32)}\n")
        elif op == "MULDIV":
            if len(parts) < 4:
                return 1
            a, b, d = parse_be(ha, 32), parse_be(hb, 32), parse_be(parts[3], 32)
            st, q, rem, _n = muldiv256(a, b, d)
            sys.stdout.write(f"{st} {be_hex(q, 32)} {be_hex(rem[:32], 32)}\n")
        else:
            sys.stderr.write(f"unknown op {op}\n")
            return 1
        nvec += 1
    sys.stderr.write(f"BATCH_N={nvec} RADIX8_CONSENSUS\n")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--self-test":
        return selftest()
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        return run_batch()
    sys.stderr.write("usage: u512_radix8.py --self-test | --batch\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
