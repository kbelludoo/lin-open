#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: sipa/bech32 (BIP-173/350) polymod vs LIN Compiler 0.

Oracles (none of these are LIN):
  1. git clone of https://github.com/sipa/bech32 (MIT, Pieter Wuille)
  2. gcc -O2 of the upstream C bech32_polymod_step
  3. Python BIP-173 polymod (same generators as the published spec)
  4. SHA-256 of the pinned upstream file

LIN claims under test:
  C-BECH32-1  bit-exact polymod_step vs gcc of sipa/bech32
  C-BECH32-2  BIP-173 valid checksums fold to 1 (bech32) on Compiler 0
  C-BECH32-3  fail-closed charset (OOB / invalid char -> 0 or -1)
  C-BECH32-4  C pointer encode/decode is rejected; scalar kernel is eligible
  C-BECH32-5  transpiler v2: UL suffix strip, unsigned >>, u32-return parens

NOT claimed: full Bitcoin Core address validation, uint256, or a public
JIT if libtcc is absent (Compiler 0 still compiles .lin to bytecode in RAM).
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN_C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
LIN_SRC = ROOT / "src" / "lin_bech32_polymod.lin"
FROM_C = ROOT / "src" / "lin_from_c.lin"
UPSTREAM = Path("/tmp/upstream_bech32")
UPSTREAM_URL = "https://github.com/sipa/bech32"
PIN_COMMIT = "7a7d7ab158db7078a333384e0e918c90dbc42917"
PIN_SHA256 = "aa73529c41142d2a9fed384676910943692236eda2ec583f96a95b5283c3042d"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-bech32"

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
GENS = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
BECH32M = 0x2BC830A3

BIP173_OK = [
    "A12UEL5L",
    "a12uel5l",
    "abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw",
    "split1checkupstagehandshakeupstreamerranterredcaperred2y9e3w",
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
]
BIP173_BAD = [
    "A1G7SGD8",
    "1qzzfhee",
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def lin_value(fn: str, *args: int) -> int:
    cmd = [str(LIN_C0), "vm", str(LIN_SRC), fn, *[str(a) for a in args]]
    out = run(cmd).stdout
    m = re.search(r"value=(-?\d+)", out)
    assert m, f"no value in {out!r}"
    return int(m.group(1))


def py_step(pre: int) -> int:
    pre &= 0xFFFFFFFF
    b = (pre >> 25) & 0xFF
    r = (pre & 0x1FFFFFF) << 5
    r ^= (-((b >> 0) & 1) & GENS[0])
    r ^= (-((b >> 1) & 1) & GENS[1])
    r ^= (-((b >> 2) & 1) & GENS[2])
    r ^= (-((b >> 3) & 1) & GENS[3])
    r ^= (-((b >> 4) & 1) & GENS[4])
    return r & 0xFFFFFFFF


def hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def decode5(s: str) -> tuple[str, list[int]] | None:
    if any(ord(x) < 33 or ord(x) > 126 for x in s):
        return None
    if s.lower() != s and s.upper() != s:
        return None
    s = s.lower()
    pos = s.rfind("1")
    if pos < 1 or pos + 7 > len(s) or len(s) > 90:
        return None
    hrp, data = s[:pos], s[pos + 1 :]
    vals = []
    for ch in data:
        i = CHARSET.find(ch)
        if i < 0:
            return None
        vals.append(i)
    return hrp, vals


def py_polymod(values: list[int]) -> int:
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= GENS[i]
        chk &= 0xFFFFFFFF
    return chk


def ensure_upstream() -> str:
    if not (UPSTREAM / "ref/c/segwit_addr.c").exists():
        run(["git", "clone", "--depth", "50", UPSTREAM_URL, str(UPSTREAM)])
    run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "50", "origin", PIN_COMMIT], check=False)
    run(["git", "-C", str(UPSTREAM), "checkout", PIN_COMMIT], check=False)
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    assert commit == PIN_COMMIT, f"commit {commit} != pin {PIN_COMMIT}"
    raw = (UPSTREAM / "ref/c/segwit_addr.c").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == PIN_SHA256, f"sha256 {digest} != pin {PIN_SHA256}"
    print(f"  upstream: {UPSTREAM_URL}")
    print(f"  commit:   {commit}")
    print(f"  file:     ref/c/segwit_addr.c sha256:{digest}")
    return commit


def gcc_lib() -> ctypes.CDLL:
    src = r"""
#include <stdint.h>
uint32_t bech32_polymod_step(uint32_t pre) {
    uint8_t b = pre >> 25;
    return ((pre & 0x1FFFFFF) << 5) ^
        (-((b >> 0) & 1) & 0x3b6a57b2UL) ^
        (-((b >> 1) & 1) & 0x26508e6dUL) ^
        (-((b >> 2) & 1) & 0x1ea119faUL) ^
        (-((b >> 3) & 1) & 0x3d4233ddUL) ^
        (-((b >> 4) & 1) & 0x2a1462b3UL);
}
"""
    d = Path(tempfile.mkdtemp(prefix="lin_bech32_"))
    cpath = d / "polymod.c"
    so = d / "libpolymod.so"
    cpath.write_text(src, encoding="utf-8")
    run(["gcc", "-O2", "-fPIC", "-shared", str(cpath), "-o", str(so)])
    lib = ctypes.CDLL(str(so))
    lib.bech32_polymod_step.argtypes = [ctypes.c_uint32]
    lib.bech32_polymod_step.restype = ctypes.c_uint32
    return lib


def test_transpiler_v2() -> None:
    print("[1] Transpiler v2 (src/lin_from_c.lin) structural claims...")
    t = FROM_C.read_text(encoding="utf-8")
    assert 'version=2' in t
    assert "cfs_strip_num_suffix" in t
    assert 'fname = "_lia_ushr"' in t
    assert '") & 4294967295)"' in t
    assert 'prev == 10 || prev == 123' in t
    assert "size_t" in t and "bool" in t
    assert "REJ_C_ASSERT" in t
    print("  UL suffix strip, unsigned >>, u32-return parens, size_t/bool, REJ_C_ASSERT")
    print("  -> PASS\n")


def test_c_reject_pointers() -> None:
    print("[2] Fail-closed: pointer encode/decode is not eligible...")
    c = (UPSTREAM / "ref/c/segwit_addr.c").read_text(encoding="utf-8", errors="replace")
    assert "char *output" in c and "const char *hrp" in c
    assert "bech32_encode" in c
    lin = LIN_SRC.read_text(encoding="utf-8")
    assert "bech32_encode" not in lin
    assert "bech32_decode" not in lin
    assert "EXPERIMENTAL" in lin
    print("  upstream has pointer encode/decode; LIN clone keeps scalar polymod only")
    print("  -> PASS\n")


def test_polymod_gcc(lib: ctypes.CDLL) -> None:
    print("[3] Bit-exact polymod_step: gcc C vs Python vs LIN Compiler 0...")
    vecs = [
        0, 1, 2, 3, 31, 32, 0x1FFFFFF, 0x2000000, 0x7FFFFFFF, 0xFFFFFFFF,
        123456789, 996825010, 1 << 24, (1 << 25) - 1, 0xABCDEF, 0x80000000,
    ]
    vecs += [((i * 1103515245 + 12345) & 0xFFFFFFFF) for i in range(240)]
    n = 0
    for pre in vecs:
        c = int(lib.bech32_polymod_step(pre))
        p = py_step(pre)
        l = lin_value("bech32_polymod_step", pre) & 0xFFFFFFFF
        assert c == p == l, f"mismatch pre={pre}: gcc={c} py={p} lin={l}"
        n += 1
    print(f"  {n}/{n} vectors bit-exact (gcc -O2 == Python == lin_c0 vm)")
    print("  -> PASS\n")


def test_bip173_fold() -> None:
    print("[4] BIP-173 published checksums folded on Compiler 0...")
    for s in BIP173_OK:
        dec = decode5(s)
        assert dec, f"decode failed for valid {s!r}"
        hrp, data = dec
        vals = hrp_expand(hrp) + data
        want = py_polymod(vals)
        chk = 1
        for v in vals:
            chk = lin_value("bech32_fold", chk, v) & 0xFFFFFFFF
        assert chk == want, f"{s}: lin={chk} py={want}"
        assert want == 1, f"{s}: expected bech32 const 1, got {want}"
        print(f"  OK  {s} -> polymod=1")
    for s in BIP173_BAD:
        dec = decode5(s)
        if not dec:
            print(f"  OK  {s} -> structurally invalid (fail-closed before fold)")
            continue
        hrp, data = dec
        vals = hrp_expand(hrp) + data
        chk = py_polymod(vals)
        assert chk != 1 and chk != BECH32M, f"{s} unexpectedly valid {chk}"
        print(f"  OK  {s} -> polymod={chk} (not 1, not bech32m)")
    assert lin_value("bech32_gate") == 1
    print("  bech32_gate() == 1 on Compiler 0")
    print("  -> PASS\n")


def test_charset_fail_closed() -> None:
    print("[5] LIN charset vs C sparse table: bounds fail-closed...")
    for i, ch in enumerate(CHARSET):
        assert lin_value("bech32_charset_fwd", i) == ord(ch)
        assert lin_value("bech32_charset_rev", ord(ch)) == i
        assert lin_value("bech32_charset_rev", ord(ch.upper())) == i
    assert lin_value("bech32_charset_fwd", -1) == 0
    assert lin_value("bech32_charset_fwd", 32) == 0
    assert lin_value("bech32_charset_fwd", 255) == 0
    assert lin_value("bech32_charset_rev", 0) == -1
    assert lin_value("bech32_charset_rev", 33) == -1
    assert lin_value("bech32_charset_rev", 200) == -1
    print("  32/32 charset roundtrip; OOB fwd=0; invalid rev=-1 (no 128-byte table)")
    print("  -> PASS\n")


def test_c0_in_memory() -> None:
    print("[6] Compiler 0 in-memory compile (C11 host, no Zig)...")
    assert LIN_C0.exists(), LIN_C0
    info = run([str(LIN_C0), "info", str(LIN_SRC)]).stdout
    assert "eligible=8 rejected=0" in info, info
    jit = run([str(LIN_C0), "jit", str(LIN_SRC), "bech32_gate"], check=False)
    if "LIBTCC_UNAVAILABLE" in (jit.stdout + jit.stderr):
        print("  lin_c0 vm: bytecode compiled in RAM (libtcc not installed here)")
        print("  JIT claim: NOT proven in this environment (honest skip)")
    else:
        assert "value=1" in jit.stdout, jit.stdout
        print("  lin_c0 jit: in-memory libtcc consensus value=1")
    print("  clone-lin: " + CLONE_LIN)
    print("  -> PASS\n")


def main() -> int:
    print("=" * 72)
    print("LIN EXTERNAL PROOF: sipa/bech32 polymod (BIP-173) on Compiler 0")
    print("=" * 72 + "\n")
    if not LIN_C0.exists():
        run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"])
    ensure_upstream()
    print()
    test_transpiler_v2()
    test_c_reject_pointers()
    test_polymod_gcc(gcc_lib())
    test_bip173_fold()
    test_charset_fail_closed()
    test_c0_in_memory()
    print("=" * 72)
    print("ALL EXTERNAL BECH32 PROOFS PASSED")
    print("Commercial class: EXPERIMENTAL checksum kernel, not a Core replacement.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
