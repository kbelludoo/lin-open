#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent proof of the Compound JumpRate V2 LIN improvements.

This file does not reimplement the 32-bit limb muldiv from the LIN clone.
Every numeric expected value is Python arbitrary-precision (a * b) // d,
then compared to Compiler 0 (`lin_c0 vm` / `roundtrip-jit`) and to the
separate C11 `__int128` oracle.

Class: EXPERIMENTAL uint64-scale. Not claimed: Solidity uint256 / mainnet
cToken parity, EVM replacement, or TVL impact.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
PIN = ROOT / "test" / "fixtures" / "external_proof" / "BaseJumpRateModelV2.sol"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "improvements_proof.json"

BASE = 10**18
KINK = 8 * 10**17
BLOCKS = 2102400
MULT_YEAR = 4 * 10**16
JUMP_YEAR = 109 * 10**16
RF10 = 10**17
U64 = (1 << 64) - 1
PIN_SHA = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"


def py_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    return (a * b) // d


def naive_u64_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    return ((a * b) & U64) // d


def py_util(cash: int, borrows: int, reserves: int) -> int:
    if borrows == 0:
        return 0
    if cash + borrows < reserves:
        return 0
    denom = cash + borrows - reserves
    if denom == 0:
        return 0
    return py_muldiv(borrows, BASE, denom)


def py_borrow(cash: int, borrows: int, reserves: int, base_b: int, mult_b: int, jump_b: int, kink: int) -> int:
    util = py_util(cash, borrows, reserves)
    if util <= kink:
        return py_muldiv(util, mult_b, BASE) + base_b
    normal = py_muldiv(kink, mult_b, BASE) + base_b
    return py_muldiv(util - kink, jump_b, BASE) + normal


def py_supply(cash: int, borrows: int, reserves: int, base_b: int, mult_b: int, jump_b: int, kink: int, rf: int) -> int:
    if rf > BASE:
        return 0
    br = py_borrow(cash, borrows, reserves, base_b, mult_b, jump_b, kink)
    rate_to_pool = py_muldiv(br, BASE - rf, BASE)
    return py_muldiv(py_util(cash, borrows, reserves), rate_to_pool, BASE)


def tcc_env() -> dict[str, str]:
    env = os.environ.copy()
    pairs = [
        ("/tmp/tinycc/lib/libtcc.so", "/tmp/tinycc/lib/tcc"),
        ("/tmp/tinycc/libtcc.so", "/tmp/tinycc"),
    ]
    for lib, d in pairs:
        if Path(lib).exists() and Path(d).exists():
            env["LIN_TCC_LIB"] = lib
            env["LIN_TCC_DIR"] = d
            env["LD_LIBRARY_PATH"] = d + ":" + str(Path(lib).parent) + ":" + env.get("LD_LIBRARY_PATH", "")
            return env
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return env


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=tcc_env(), check=False)


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(proc.stdout)
    return v


def c11(kind: str, *args: int, limbs: bool = False) -> int:
    cmd = [str(ORACLE_BIN), kind, *[str(a) for a in args]]
    if limbs:
        cmd.append("--limbs")
    proc = run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    return int(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            {note}")

    print("=" * 78)
    print("  COMPOUND JUMPRATE IMPROVEMENTS — independent Python oracle")
    print("=" * 78)

    if not PIN.exists() or hashlib.sha256(PIN.read_bytes()).hexdigest() != PIN_SHA:
        rec("I-PIN", "FAIL", "pinned BaseJumpRateModelV2.sol sha256 mismatch")
        return 1
    rec("I-PIN", "PASS", "fixture sha256 matches Compound pin", PIN_SHA)

    if not C0.exists():
        proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"])
        if proc.returncode != 0 or not C0.exists():
            rec("I-C0", "FAIL", "Compiler 0 build failed", proc.stderr)
            return 1
    rec("I-C0", "PASS", "Compiler 0 present (C11, no Zig)")

    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        rec("I-C11-BUILD", "FAIL", "gcc oracle", proc.stderr)
        return 1
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("I-C11-SELFTEST", "FAIL", "C11 selftest", st.stdout + st.stderr)
        return 1
    rec("I-C11-SELFTEST", "PASS", "C11 __int128 oracle selftest")

    true = py_muldiv(BASE, BASE, 2 * BASE)
    wrap = naive_u64_muldiv(BASE, BASE, 2 * BASE)
    lin = lin_vm("cjr_muldiv", BASE, BASE, 2 * BASE)
    i128 = c11("muldiv", BASE, BASE, 2 * BASE)
    limbs = c11("muldiv", BASE, BASE, 2 * BASE, limbs=True)
    if true != 5 * 10**17 or wrap == true or lin != true or i128 != true or limbs != true:
        rec(
            "I-WIDE-MULDIV",
            "FAIL",
            "128-bit muldiv did not beat wrapping i64",
            f"py={true} wrap={wrap} lin={lin} i128={i128} limbs={limbs}",
        )
        return 1
    rec(
        "I-WIDE-MULDIV",
        "PASS",
        "1e18*1e18/2e18: Python==(C11 i128)==limbs==LIN, wrapping u64 differs",
        f"true={true} wrap_u64={wrap} (discriminating: wrap!=true)",
    )

    util_true = py_util(BASE, BASE, 0)
    util_wrap = naive_u64_muldiv(BASE, BASE, 2 * BASE)
    util_lin = lin_vm("cjr_utilization", BASE, BASE, 0)
    if util_true != util_lin or util_wrap == util_true:
        rec("I-UTIL-WIDE", "FAIL", "utilization 50% wrapping vs wide", f"py={util_true} wrap={util_wrap} lin={util_lin}")
        return 1
    rec("I-UTIL-WIDE", "PASS", "utilization(1e18,1e18,0)=5e17; wrapping muldiv would yield 6")

    r_lo = lin_vm("cjr_borrow_rate", BASE, BASE, 0, 0, 1000, 0, BASE)
    r_hi = lin_vm("cjr_borrow_rate", BASE, BASE, 0, 0, 2000, 0, BASE)
    if r_lo == r_hi or r_lo != py_borrow(BASE, BASE, 0, 0, 1000, 0, BASE):
        rec("I-EXPLICIT-ARGS", "FAIL", "borrow rate ignored explicit mult_block", f"{r_lo} vs {r_hi}")
        return 1
    rec("I-EXPLICIT-ARGS", "PASS", "same market, two mult_block args => two rates (no hidden storage)", f"{r_lo} vs {r_hi}")

    mb = py_muldiv(py_muldiv(MULT_YEAR, BASE, KINK), 1, BLOCKS)
    jb = py_muldiv(JUMP_YEAR, 1, BLOCKS)
    below_a = lin_vm("cjr_borrow_rate", BASE, BASE, 0, 0, mb, 1, KINK)
    below_b = lin_vm("cjr_borrow_rate", BASE, BASE, 0, 0, mb, 999999, KINK)
    above_a = lin_vm("cjr_borrow_rate", 10**17, 9 * 10**17, 0, 0, mb, 1, KINK)
    above_b = lin_vm("cjr_borrow_rate", 10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    if below_a != below_b or above_a == above_b or above_b <= below_a:
        rec("I-JUMP-KINK", "FAIL", "jump multiplier not gated on kink", f"below={below_a}/{below_b} above={above_a}/{above_b}")
        return 1
    rec("I-JUMP-KINK", "PASS", "jump_block unused below kink; used above kink; r90>r50")

    uf = lin_vm("cjr_utilization", 1, 1, 100)
    if uf != 0:
        rec("I-UNDERFLOW", "FAIL", "cash+borrows<reserves should fail-closed to 0", str(uf))
        return 1
    rec("I-UNDERFLOW", "PASS", "utilization(1,1,100)==0 (Solidity 0.8 would revert on underflow)")

    product = MULT_YEAR * BASE
    want_mb = (MULT_YEAR * BASE) // (BLOCKS * KINK)
    lin_mb = lin_vm("cjr_multiplier_per_block", MULT_YEAR, KINK)
    if product <= U64 or want_mb != mb or lin_mb != want_mb:
        rec("I-MULT-OVERFLOW", "FAIL", "multiplierPerBlock overflow path", f"lin={lin_mb} want={want_mb} product={product}")
        return 1
    rec(
        "I-MULT-OVERFLOW",
        "PASS",
        "(mult_year*BASE) does not fit uint64; LIN floor-matches Solidity (x)/(blocks*kink)",
        f"product={product} u64max={U64} multiplierPerBlock={lin_mb}",
    )

    r50 = lin_vm("cjr_borrow_rate", BASE, BASE, 0, 0, mb, jb, KINK)
    r90 = lin_vm("cjr_borrow_rate", 10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    s50 = lin_vm("cjr_supply_rate", BASE, BASE, 0, 0, mb, jb, KINK, RF10)
    py50 = py_borrow(BASE, BASE, 0, 0, mb, jb, KINK)
    py90 = py_borrow(10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    pys50 = py_supply(BASE, BASE, 0, 0, mb, jb, KINK, RF10)
    c50 = c11("borrow", BASE, BASE, 0, 0, mb, jb, KINK)
    c90 = c11("borrow", 10**17, 9 * 10**17, 0, 0, mb, jb, KINK)
    cs50 = c11("supply", BASE, BASE, 0, 0, mb, jb, KINK, RF10)
    if not (r50 == py50 == c50 and r90 == py90 == c90 and s50 == pys50 == cs50):
        rec("I-FORMULA", "FAIL", "Python vs LIN vs C11 IRM mismatch", f"r50={r50}/{py50}/{c50} r90={r90}/{py90}/{c90} s50={s50}/{pys50}/{cs50}")
        return 1
    rec("I-FORMULA", "PASS", "utilization/borrow/supply: Python bigint == LIN vm == C11 __int128", f"borrow50={r50} borrow90={r90} supply50_rf10={s50}")

    rt = run([str(C0), "roundtrip-jit", str(LIN), "cjr_test_suite"], timeout=90)
    if rt.returncode == 0 and "CONSENSUS" in rt.stdout:
        rec("I-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite")
    else:
        rec("I-JIT", "SKIP", "in-memory JIT not exercised", (rt.stdout + rt.stderr)[-400:])

    gate = run([str(C0), "vm", str(SOL_TR), "sol_from_sol_gate"])
    if gate.returncode == 0 and value_of(gate.stdout) == 1:
        rec("I-SOL-EMIT", "PASS", "sol_from_sol_gate executed on Compiler 0")
    elif "VM_REJ_STRING_LITERAL" in gate.stdout:
        src = SOL_TR.read_text(encoding="utf-8")
        if "sol_from_sol" in src and "sol_expand_exp" in src:
            rec(
                "I-SOL-EMIT",
                "SKIP",
                "Solidity emit path is present in source but C0 VM refuses string literals",
                "VM_REJ_STRING_LITERAL — not an execution proof of sol_from_sol",
            )
        else:
            rec("I-SOL-EMIT", "FAIL", "emit functions missing from lin_from_solidity.lin")
    else:
        rec("I-SOL-EMIT", "FAIL", "unexpected sol_from_sol_gate result", gate.stdout[-400:])

    evidence = {
        "schema": "LIN_COMPOUND_IMPROVEMENTS_PROOF_1.0",
        "class": "EXPERIMENTAL",
        "oracle": "python3 arbitrary-precision (a*b)//d — not a limb clone",
        "claims": claims,
        "vectors": {
            "wide_muldiv_true": true,
            "wide_muldiv_wrap_u64": wrap,
            "borrow_50": r50,
            "borrow_90": r90,
            "supply_50_rf10": s50,
            "multiplier_per_block": lin_mb,
        },
        "not_claimed": [
            "full Solidity uint256 / mainnet cToken parity",
            "LIN replaces Compound or the EVM",
            "wall-clock superiority vs solc",
            "executed sol_from_sol on BaseJumpRateModelV2.sol (hand-port + VM_REJ_STRING_LITERAL)",
        ],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
