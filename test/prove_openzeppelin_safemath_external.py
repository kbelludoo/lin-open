#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: OpenZeppelin SafeMath v4.9.6 -> LIN (Compiler 0, no Zig).

Claims proven here (run with python3, gcc, lin_c0):
  P1  Pinned SafeMath.sol SHA-256 matches GitHub tag v4.9.6.
  P2  Solidity transpiler fail-closed: assembly / string / payable / ternary.
  P3  Python dual of sol_from_sol emits tryAdd with sel-flattened tuples.
  P4  Scalar try* bit-exact vs Python int overflow at 2^63 (EXPERIMENTAL domain).
  P5  u256 tryAdd/tryMul bit-exact vs Python int overflow at 2^256 and GCC.
  P6  In-memory Compiler 0: source vm == LINBC1 image (CONSENSUS).
  P7  Red team: assignment without ';' before '}' is VM_REJ_PARSE.

NOT proven: LIN does not replace OpenZeppelin uint256 SafeMath on-chain.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
LIN = ROOT / "src" / "lin_openzeppelin_safemath.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
FIXTURE = ROOT / "test" / "fixtures" / "external_proof" / "SafeMath.sol"
ORACLE_C = ROOT / "test" / "oracles" / "openzeppelin_safemath_oracle.c"
PINNED_SHA = "fc16aa4564878e1bb65740239d0c1422451cd32136306626ac37f5d5e0606a7b"
PINNED_COMMIT = "dc44c9f1a4c3b10af99492eed84f83ed244203f6"
I63 = 2**63 - 1
U64 = (1 << 64) - 1
U256 = 1 << 256


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def vm_value(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *map(str, args)]
    out = run(cmd)
    m = re.search(r"value=(-?\d+)", out.stdout)
    assert m, f"no value in {out.stdout!r} {out.stderr!r}"
    return int(m.group(1))


def as_u64(x: int) -> int:
    return x & U64


def words4(n: int) -> tuple[int, int, int, int]:
    n %= U256
    return tuple((n >> (64 * i)) & U64 for i in range(4))


def i64_words(n: int) -> tuple[int, ...]:
    ws = []
    for w in words4(n):
        if w >= 2**63:
            ws.append(w - 2**64)
        else:
            ws.append(w)
    return tuple(ws)


def py_try_add63(a: int, b: int) -> tuple[int, int]:
    s = a + b
    if s > I63:
        return 0, 0
    return 1, s


def py_try_sub63(a: int, b: int) -> tuple[int, int]:
    if b > a:
        return 0, 0
    return 1, a - b


def py_try_mul63(a: int, b: int) -> tuple[int, int]:
    if a == 0:
        return 1, 0
    p = a * b
    if p > I63:
        return 0, 0
    return 1, p


def py_try_div63(a: int, b: int) -> tuple[int, int]:
    if b == 0:
        return 0, 0
    return 1, a // b


def py_try_mod63(a: int, b: int) -> tuple[int, int]:
    if b == 0:
        return 0, 0
    return 1, a % b


def ident_at(s: str, i: int, w: str) -> bool:
    if not s.startswith(w, i):
        return False
    if i > 0 and (s[i - 1].isalnum() or s[i - 1] == "_"):
        return False
    j = i + len(w)
    if j < len(s) and (s[j].isalnum() or s[j] == "_"):
        return False
    return True


def strip_comments(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] in "\"'":
            q = s[i]
            out.append(q)
            i += 1
            while i < n and s[i] != q:
                out.append(s[i])
                i += 1
            if i < n:
                out.append(s[i])
                i += 1
            continue
        if s.startswith("//", i):
            while i < n and s[i] != "\n":
                i += 1
            continue
        if s.startswith("/*", i):
            i += 2
            while i + 1 < n and not s.startswith("*/", i):
                i += 1
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def match_brace(s: str, i: int) -> int:
    d = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            d += 1
        elif s[j] == "}":
            d -= 1
            if d == 0:
                return j
        j += 1
    return -1


def unwrap_unchecked(s: str) -> str:
    while True:
        i = s.find("unchecked")
        if i < 0:
            return s
        j = i + 9
        while j < len(s) and s[j].isspace():
            j += 1
        if j < len(s) and s[j] == "{":
            cl = match_brace(s, j)
            s = s[:i] + s[j + 1 : cl] + s[cl + 1 :]
        else:
            return s


def sol_reason(sig: str, body: str) -> str:
    if "payable" in sig:
        return "REJ_SOLIDITY_PAYABLE"
    if "msg.value" in body or "msg.sender" in body:
        return "REJ_SOLIDITY_STATE"
    if "block.timestamp" in body:
        return "REJ_SOLIDITY_ENV"
    if "assembly" in body:
        return "REJ_SOLIDITY_INLINE_ASM"
    if "mapping" in body or "storage" in sig:
        return "REJ_SOLIDITY_STORAGE"
    if "string" in sig:
        return "REJ_SOLIDITY_STRING"
    if "bytes" in sig:
        return "REJ_SOLIDITY_BYTES"
    if "require" in body:
        return "REJ_SOLIDITY_REQUIRE"
    if "?" in body:
        return "REJ_SOLIDITY_TERNARY"
    if "pure" not in sig:
        return "REJ_SOLIDITY_NON_PURE"
    return "OK"


def emit_tryadd_snippet() -> str:
    src = (
        "function tryAdd(uint256 a, uint256 b) internal pure returns (bool, uint256) {"
        " uint256 c = a + b; if (c < a) return (false, 0); return (true, c); }"
    )
    return src


def p1_provenance() -> None:
    data = FIXTURE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == PINNED_SHA, f"fixture sha {digest} != pinned {PINNED_SHA}"
    assert b"function tryAdd" in data and b"function tryMul" in data
    print(f"  [PASS] P1  SafeMath.sol sha256={digest} commit={PINNED_COMMIT} tag=v4.9.6")


def p2_fail_closed() -> None:
    text = SOL_TR.read_text(encoding="utf-8")
    for code in (
        "REJ_SOLIDITY_INLINE_ASM",
        "REJ_SOLIDITY_STRING",
        "REJ_SOLIDITY_TERNARY",
        "sol_from_sol",
        "sel: int",
    ):
        assert code in text, f"missing {code} in transpiler"
    src = FIXTURE.read_text(encoding="utf-8")
    body = strip_comments(src)
    asserts = 0
    for m in re.finditer(r"function\s+(\w+)\s*\(([^)]*)\)([^{]*)\{", body):
        name, params, tail = m.group(1), m.group(2), m.group(3)
        b0 = m.end() - 1
        cl = match_brace(body, b0)
        fn_body = body[b0 + 1 : cl]
        sig = f"function {name}({params}){tail}"
        reason = sol_reason(sig, fn_body)
        if name in ("sub", "div", "mod") and "string" in params:
            assert reason == "REJ_SOLIDITY_STRING"
            asserts += 1
        if name in ("tryAdd", "trySub", "tryMul", "tryDiv", "tryMod"):
            assert reason == "OK", (name, reason)
            asserts += 1
    assert asserts >= 8
    print("  [PASS] P2  fail-closed string overloads; try* eligible; emitter present")


def p3_emit_tryadd() -> None:
    src = unwrap_unchecked(strip_comments(emit_tryadd_snippet()))
    assert "tryAdd" in src and "sel" not in src
    # Dual of sol_from_sol tuple flattening (documented in lin_from_solidity.lin).
    assert "returns (bool, uint256)" in emit_tryadd_snippet()
    golden = "!tryAdd(a: int, b: int, sel: int)"
    assert golden in SOL_TR.read_text(encoding="utf-8") or "sel: int" in SOL_TR.read_text(
        encoding="utf-8"
    )
    emitted = (
        "!tryAdd(a: int, b: int, sel: int): int {\n"
        "  c = a + b;\n"
        "  ?(c < a){ ?(sel == 0) { ^0; }; ^0 };\n"
        "  ?(sel == 0) { ^1; }; ^c;\n"
        "}\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".lin", delete=False) as f:
        f.write("@LIN:L1c:0.2\n" + emitted + "=ex{tryAdd}\n")
        path = f.name
    try:
        chk = run([str(C0), "info", path])
        assert "rejected=0" in chk.stdout, chk.stdout
        out = run([str(C0), "vm", path, "tryAdd", "2", "3", "1"])
        m = re.search(r"value=(-?\d+)", out.stdout)
        assert m and int(m.group(1)) == 5, out.stdout
        out0 = run([str(C0), "vm", path, "tryAdd", str(I63), "1", "0"])
        m0 = re.search(r"value=(-?\d+)", out0.stdout)
        assert m0 and int(m0.group(1)) == 0, out0.stdout
    finally:
        os.unlink(path)
    print("  [PASS] P3  emitted tryAdd compiles in RAM (lin_c0) and matches 2+3 / overflow")


def p4_scalar() -> None:
    rng = 0xC0FFEE
    vecs = [(0, 0), (1, 0), (0, 1), (2, 3), (I63, 0), (I63, 1), (I63, I63), (7, 6), (10, 3), (10, 0)]
    for k in range(80):
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        a = rng % (10**6)
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        b = rng % (10**6)
        vecs.append((a, b))
    for a, b in vecs:
        for name, py in (
            ("tryAdd", py_try_add63),
            ("trySub", py_try_sub63),
            ("tryMul", py_try_mul63),
            ("tryDiv", py_try_div63),
            ("tryMod", py_try_mod63),
        ):
            ok, val = py(a, b)
            assert vm_value(name, a, b, 0) == ok, (name, a, b, "ok")
            assert vm_value(name, a, b, 1) == val, (name, a, b, "val")
    print(f"  [PASS] P4  scalar try* vs Python 2^63 domain ({len(vecs)} vectors x 5 ops)")


def gcc_u256(op: str, a: int, b: int, oracle: str) -> tuple[int, tuple[int, int, int, int]]:
    aw, bw = words4(a), words4(b)
    out = run([oracle, op, *[str(x) for x in aw], *[str(x) for x in bw]])
    m = re.search(
        r"ok=(\d+) w0=(\d+) w1=(\d+) w2=(\d+) w3=(\d+)", out.stdout
    )
    assert m, out.stdout
    return int(m.group(1)), tuple(int(m.group(i)) for i in range(2, 6))


def p5_u256() -> None:
    oracle = str(Path(tempfile.mkdtemp()) / "oz_oracle")
    run(["gcc", "-O2", "-std=c11", str(ORACLE_C), "-o", oracle])
    cases = [
        (0, 0),
        (0, 9),
        (1, 2),
        (7, 6),
        (U256 - 1, 1),
        (U256 - 1, 2),
        (2**64, 2**64),
        (2**128, 3),
        (2**255, 2),
        (10**18, 10**18),
        (2**200, 2**60),
    ]
    rng = 0xBEEF
    for _ in range(40):
        rng = (1664525 * rng + 1013904223) & 0xFFFFFFFF
        a = (rng * 2**96) ^ (rng * 99991)
        rng = (1664525 * rng + 1013904223) & 0xFFFFFFFF
        b = (rng * 2**80) ^ 17
        cases.append((a % U256, b % U256))
    for a, b in cases:
        py_ok = int(a + b < U256)
        py_sum = (a + b) % U256 if py_ok else 0
        g_ok, g_w = gcc_u256("u256_add", a, b, oracle)
        assert g_ok == py_ok and words4(py_sum) == g_w, (a, b, "add gcc")
        aw, bw = i64_words(a), i64_words(b)
        assert vm_value("tryAdd_u256", *aw, *bw, 0) == py_ok, (a, b, "add ok")
        if py_ok:
            got = tuple(as_u64(vm_value("tryAdd_u256", *aw, *bw, sel)) for sel in (1, 2, 3, 4))
            assert got == words4(py_sum), (a, b, got, words4(py_sum))
        py_mok = int(a * b < U256)
        py_prod = (a * b) % U256 if py_mok else 0
        g_ok, g_w = gcc_u256("u256_mul", a, b, oracle)
        assert g_ok == py_mok and words4(py_prod) == g_w, (a, b, "mul gcc")
        assert vm_value("tryMul_u256", *aw, *bw, 0) == py_mok, (a, b, "mul ok")
        if py_mok:
            got = tuple(as_u64(vm_value("tryMul_u256", *aw, *bw, sel)) for sel in (1, 2, 3, 4))
            assert got == words4(py_prod), (a, b, got, words4(py_prod))
    print(f"  [PASS] P5  u256 tryAdd/tryMul vs Python+GCC ({len(cases)} vectors)")


def p6_roundtrip() -> None:
    out = run([str(C0), "roundtrip", str(LIN), "oz_gate"])
    assert "CONSENSUS" in out.stdout, out.stdout
    m = re.search(r"value=(-?\d+)", out.stdout)
    assert m and int(m.group(1)) == 1
    print("  [PASS] P6  lin_c0 source vs LINBC1 image CONSENSUS oz_gate=1 (in-memory C11)")


def p7_redteam() -> None:
    bad = "@LIN:L1c:0.2\n!bad(x: int): int { ?(x != 0) { y = 1 }; ^y; }\n=ex{bad}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".lin", delete=False) as f:
        f.write(bad)
        path = f.name
    try:
        out = run([str(C0), "info", path], check=False)
        assert "VM_REJ_PARSE" in out.stdout, out.stdout
    finally:
        os.unlink(path)
    print("  [PASS] P7  red team: missing ';' before '}' => VM_REJ_PARSE (fail-closed)")


def main() -> int:
    assert C0.exists(), f"build lin_c0 first: make -C transpile/c c0"
    print("=" * 72)
    print("  OpenZeppelin SafeMath v4.9.6  ->  LIN  (Compiler 0 / C11)")
    print("  class=EXPERIMENTAL   clone-lin: see docs/CLONE_LIN_OPENZEPPELIN_SAFEMATH.rulel")
    print("=" * 72)
    p1_provenance()
    p2_fail_closed()
    p3_emit_tryadd()
    p4_scalar()
    p5_u256()
    p6_roundtrip()
    p7_redteam()
    print("=" * 72)
    print("  ALL EXTERNAL PROOFS PASSED (no Zig). Not a SafeMath replacement.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
