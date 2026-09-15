#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jump / supply / fail-closed / fuzz edges for the uint64 JumpRate clone.

Class: EXPERIMENTAL. Not Solidity uint256 or mainnet cToken parity.
"""
from __future__ import annotations

import os
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "test" / "oracles"))
from compound_jumprate_py import (  # noqa: E402
    BASE,
    BLOCKS,
    I64_MAX,
    JUMP_YEAR,
    KINK,
    MULT_YEAR,
    borrow_rate,
    jump_per_block,
    muldiv,
    multiplier_per_block,
    solidity_multiplier_per_block,
    supply_rate,
    utilization,
)

LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"


def run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def rec(claims: list[dict[str, str]], ident: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:16s}  {desc}")
    if note:
        print(f"            note: {note}")


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    m = re.search(r"\bvalue=(-?\d+)\b", proc.stdout)
    if not m:
        raise RuntimeError(proc.stdout)
    return int(m.group(1))


def c11(args: list[str]) -> int:
    proc = run([str(ORACLE_BIN), *args])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    return int(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  COMPOUND JUMPRATE EDGES — jump path, supply, fail-closed, fuzz")
    print("=" * 78)

    gcc = run(["gcc", "-O2", "-std=c11", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if gcc.returncode != 0:
        rec(claims, "C11-BUILD", "FAIL", "gcc oracle", gcc.stderr)
        return 1
    if not C0.exists():
        rec(claims, "C0", "FAIL", "lin_c0 missing; make -C transpile/c c0")
        return 1

    mb = multiplier_per_block(MULT_YEAR, KINK)
    jb = jump_per_block(JUMP_YEAR)
    py90 = borrow_rate(10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    lin90 = lin_vm(LIN, "cjr_borrow_rate", 10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    c1190 = c11(["borrow", str(10**17), str(9 * 10**17), "0", "0", str(mb), str(jb), str(KINK)])
    if not (py90 == lin90 == c1190 == 70871385082):
        rec(claims, "BORROW-90", "FAIL", "jump path util>kink", f"py={py90} lin={lin90} c11={c1190}")
        return 1
    rec(claims, "BORROW-90", "PASS", "90% util (above kink) three-way consensus", f"rate={py90}")

    py_s = supply_rate(BASE, BASE, 0, 0, mb, jb, KINK, 10**17)
    lin_s = lin_vm(LIN, "cjr_supply_rate", BASE, BASE, 0, 0, mb, jb, KINK, 10**17)
    c11_s = c11(["supply", str(BASE), str(BASE), "0", "0", str(mb), str(jb), str(KINK), str(10**17)])
    if not (py_s == lin_s == c11_s == 5351027396):
        rec(claims, "SUPPLY-50", "FAIL", "supply@50% rf=0.1", f"py={py_s} lin={lin_s} c11={c11_s}")
        return 1
    rec(claims, "SUPPLY-50", "PASS", "supply rate 50% util rf=10% three-way", f"rate={py_s}")

    edges = [
        ("underflow", utilization(0, 100, 200), lin_vm(LIN, "cjr_utilization", 0, 100, 200), 0),
        ("reserves-2x", utilization(0, BASE, BASE // 2), lin_vm(LIN, "cjr_utilization", 0, BASE, BASE // 2), 2 * 10**18),
        ("q-overflow", muldiv(BASE, BASE, 1), lin_vm(LIN, "cjr_muldiv", BASE, BASE, 1), 0),
        ("div0", muldiv(5, 5, 0), lin_vm(LIN, "cjr_muldiv", 5, 5, 0), 0),
        ("kink0", multiplier_per_block(MULT_YEAR, 0), lin_vm(LIN, "cjr_multiplier_per_block", MULT_YEAR, 0), 0),
        ("tiny-denom", utilization(0, 10, 9), lin_vm(LIN, "cjr_utilization", 0, 10, 9), 0),
    ]
    for name, py, lin, want in edges:
        if not (py == lin == want):
            rec(claims, "FAILCLOSED", "FAIL", name, f"py={py} lin={lin} want={want}")
            return 1
    rec(claims, "FAILCLOSED", "PASS", "6/6 fail-closed / reserves vectors match Python")

    rng = random.Random(20260915)
    n_ok = 0
    for _ in range(64):
        a = rng.randint(0, 10**9)
        b = rng.randint(0, 10**9)
        d = rng.randint(1, 10**9)
        py = muldiv(a, b, d)
        lin = lin_vm(LIN, "cjr_muldiv", a, b, d)
        cc = c11(["muldiv", str(a), str(b), str(d)])
        prod = a * b
        if py != lin or py != cc:
            rec(claims, "FUZZ-MULDIV", "FAIL", f"({a}*{b})/{d}", f"py={py} lin={lin} c11={cc}")
            return 1
        if prod // d <= I64_MAX and prod != py * d + (prod % d):
            rec(claims, "REM-ID", "FAIL", "a*b != q*d+r", f"a={a} b={b} d={d}")
            return 1
        n_ok += 1
    rec(claims, "FUZZ-MULDIV", "PASS", f"{n_ok}/64 random muldiv Python==LIN==C11 + remainder id")

    reorder_ok = 0
    den_wide = 0
    pairs = [
        (MULT_YEAR, KINK),
        (10**16, 5 * 10**17),
        (1, KINK),
        (123456789, 987654321),
    ]
    for my, k in pairs:
        sol = solidity_multiplier_per_block(my, k)
        two = multiplier_per_block(my, k)
        lin = lin_vm(LIN, "cjr_multiplier_per_block", my, k)
        if sol > I64_MAX or muldiv(my, BASE, k) == 0:
            rec(claims, "REORDER", "FAIL", f"pair overflows profile my={my} k={k}")
            return 1
        if not (sol == two == lin):
            rec(claims, "REORDER", "FAIL", f"mult_year={my} kink={k}", f"{sol} {two} {lin}")
            return 1
        reorder_ok += 1
        if BLOCKS * k > I64_MAX:
            den_wide += 1
    if den_wide == 0:
        rec(claims, "DEN-WIDE", "FAIL", "expected at least one pair where blocks*kink exceeds i64")
        return 1
    rec(claims, "DEN-WIDE", "PASS", "blocks*kink exceeds i64; two-step still matches bigint floor", f"n={den_wide}")
    rec(claims, "REORDER", "PASS", f"{reorder_ok}/{len(pairs)} year-to-block identity when the intermediate fits i64")

    sol_k1 = solidity_multiplier_per_block(MULT_YEAR, 1)
    lin_k1 = lin_vm(LIN, "cjr_multiplier_per_block", MULT_YEAR, 1)
    if sol_k1 <= I64_MAX or lin_k1 != 0:
        rec(claims, "INTERMED-OV", "FAIL", "kink=1 should overflow intermediate", f"sol={sol_k1} lin={lin_k1}")
        return 1
    rec(
        claims,
        "INTERMED-OV",
        "PASS",
        "kink=1: Solidity bigint quotient does not fit i64; LIN two-step fail-closed to 0 (not uint256)",
        f"sol_digits={len(str(sol_k1))} lin={lin_k1}",
    )

    chk = run([str(C0), "check", str(SOL_TR)])
    src_sol = SOL_TR.read_text(encoding="utf-8")
    if ".typecheck=passed" not in chk.stdout:
        rec(claims, "SOL-GATE", "FAIL", "lin_from_solidity.lin check", chk.stdout)
        return 1
    if "REJ_SOLIDITY_NON_PURE" not in src_sol or "REJ_SOLIDITY_STATE" not in src_sol:
        rec(claims, "SOL-GATE", "FAIL", "missing view/msg.sender reject tests")
        return 1
    if "sol_from_sol_gate" not in src_sol or "1000000000000000000" not in src_sol:
        rec(claims, "SOL-GATE", "FAIL", "missing 1eN emit gate")
        return 1
    rec(
        claims,
        "SOL-GATE",
        "PASS",
        "transpiler typechecks; source rejects view/msg.sender; emit gate expands 1e18 (vm refuses string literals)",
    )

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
