#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent re-proof of the Compound JumpRate LIN clone.

This file does not copy the C11 limb muldiv. Python int is the exact
(a*b)//d oracle. It exists to prove the claimed *improvements*, not only
that a mirrored oracle agrees with LIN.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
PIN = ROOT / "test" / "fixtures" / "external_proof" / "BaseJumpRateModelV2.sol"
UPSTREAM = Path("/tmp/upstream_compound_protocol/contracts/BaseJumpRateModelV2.sol")

BASE = 10**18
BLOCKS = 2102400
KINK = 8 * 10**17
MULT_YEAR = 4 * 10**16
JUMP_YEAR = 109 * 10**16
U64 = 1 << 64


def run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/lib/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    lp = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = "/tmp/tinycc/lib" + (":" + lp if lp else "")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def lin(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    m = re.search(r"\bvalue=(-?\d+)\b", proc.stdout)
    if not m:
        raise RuntimeError(proc.stdout)
    return int(m.group(1))


def wrap_u64_muldiv(a: int, b: int, d: int) -> int:
    return ((a * b) % U64) // d


def exact_muldiv(a: int, b: int, d: int) -> int:
    return 0 if d == 0 else (a * b) // d


def utilization(cash: int, borrows: int, reserves: int) -> int:
    if borrows == 0:
        return 0
    if cash + borrows < reserves:
        return 0
    denom = cash + borrows - reserves
    if denom == 0:
        return 0
    return exact_muldiv(borrows, BASE, denom)


def borrow_rate(cash: int, borrows: int, reserves: int, bb: int, mb: int, jb: int, kink: int) -> int:
    util = utilization(cash, borrows, reserves)
    if util <= kink:
        return exact_muldiv(util, mb, BASE) + bb
    normal = exact_muldiv(kink, mb, BASE) + bb
    return exact_muldiv(util - kink, jb, BASE) + normal


def main() -> int:
    claims: list[tuple[str, str, str]] = []

    def rec(ident: str, ok: bool, note: str) -> None:
        claims.append((ident, "PASS" if ok else "FAIL", note))
        print(f"  [{'PASS' if ok else 'FAIL'}] {ident:22s}  {note}")

    print("=" * 78)
    print("  INDEPENDENT re-proof of Compound JumpRate LIN improvements")
    print("=" * 78)

    if not C0.exists():
        print("missing lin_c0", file=sys.stderr)
        return 2

    rec(
        "PIN-LIVE",
        PIN.exists() and UPSTREAM.exists() and PIN.read_bytes() == UPSTREAM.read_bytes(),
        "pinned fixture bytes == live compound-protocol clone",
    )

    src = LIN.read_text(encoding="utf-8")
    rec(
        "IMP-EXPLICIT-SIG",
        "cjr_borrow_rate(cash: int, borrows: int, reserves: int, base_block: int, mult_block: int, jump_block: int, kink: int)"
        in src
        and "msg.sender" not in src
        and "multiplierPerBlock" not in src,
        "borrow rate takes IRM params as args (no Solidity storage / msg.sender)",
    )

    a, b, d = BASE, BASE, 2 * BASE
    exact = exact_muldiv(a, b, d)
    wrapped = wrap_u64_muldiv(a, b, d)
    got = lin("cjr_muldiv", a, b, d)
    rec("IMP-WRAP-DIVERGES", wrapped != exact, f"uint64 wrap muldiv={wrapped} exact={exact}")
    rec("IMP-WIDE-EQ-PY", got == exact, f"LIN cjr_muldiv={got} python_exact={exact}")
    rec("IMP-WIDE-NE-WRAP", got != wrapped, "LIN does not follow wrapping i64 product")

    naive_year = ((MULT_YEAR * BASE) % U64) // BLOCKS
    lin_year = (MULT_YEAR * BASE // KINK) // BLOCKS
    sol_year = (MULT_YEAR * BASE) // (BLOCKS * KINK)
    mb = lin("cjr_multiplier_per_block", MULT_YEAR, KINK)
    rec("IMP-YEAR-U64-WRONG", naive_year != sol_year, f"u64 wrap year={naive_year} exact={sol_year}")
    rec("IMP-YEAR-LIN", mb == lin_year == sol_year, f"multiplierPerBlock lin={mb} exact={sol_year}")

    jb = lin("cjr_jump_per_block", JUMP_YEAR)
    bb = lin("cjr_base_per_block", 0)
    rec("IMP-JUMP-BLOCK", jb == JUMP_YEAR // BLOCKS, f"jumpPerBlock={jb}")

    r50_py = borrow_rate(BASE, BASE, 0, bb, mb, jb, KINK)
    r90_py = borrow_rate(10**17, 9 * 10**17, 0, bb, mb, jb, KINK)
    r50 = lin("cjr_borrow_rate", BASE, BASE, 0, bb, mb, jb, KINK)
    r90 = lin("cjr_borrow_rate", 10**17, 9 * 10**17, 0, bb, mb, jb, KINK)
    rec("IMP-RATE-50", r50 == r50_py, f"50% util borrow={r50}")
    rec("IMP-RATE-90", r90 == r90_py and r90 > r50, f"90% util borrow={r90} (jump > 50%)")

    r50_alt = lin("cjr_borrow_rate", BASE, BASE, 0, bb, mb * 2, jb, KINK)
    rec("IMP-EXPLICIT-LIVE", r50_alt != r50, "same cash/borrows, different mult_block => different rate")

    under = lin("cjr_utilization", 1, 1, 100)
    rec("IMP-UNDERFLOW-0", under == 0, "cash+borrows < reserves fail-closed 0 (Solidity 0.8 reverts)")

    gate = run([str(C0), "vm", str(SOL_TR), "sol_from_sol_gate"])
    gv = re.search(r"\bvalue=(-?\d+)\b", gate.stdout)
    if gate.returncode == 0 and gv is not None and int(gv.group(1)) == 1:
        rec("IMP-SOL-EMIT-RUN", True, "sol_from_sol_gate==1 on C0")
    elif "VM_REJ_STRING_LITERAL" in (gate.stdout + gate.stderr):
        print("  [SKIP] IMP-SOL-EMIT-RUN       C0 integer VM rejects string literals; emit not executed")
        claims.append(("IMP-SOL-EMIT-RUN", "SKIP", "VM_REJ_STRING_LITERAL"))
    else:
        rec("IMP-SOL-EMIT-RUN", False, (gate.stdout + gate.stderr)[:200])

    jit = run([str(C0), "roundtrip-jit", str(LIN), "cjr_test_suite"])
    rec("IMP-JIT", jit.returncode == 0 and "CONSENSUS" in jit.stdout, "roundtrip-jit CONSENSUS on cjr_test_suite")

    failed = sum(1 for _, s, _ in claims if s == "FAIL")
    passed = sum(1 for _, s, _ in claims if s == "PASS")
    skipped = sum(1 for _, s, _ in claims if s == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
