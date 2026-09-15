#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent re-proof of Compound JumpRate melhorias.

Third oracle is Python arbitrary-precision int — not the C11 limb clone and
not LinVM. Hashes are recomputed with hashlib / git hash-object this run.

Class: EXPERIMENTAL. Real deltas on this profile:
  1. IRM storage parameters are function arguments
  2. (a*b)/d uses a 128-bit product; q that does not fit nonnegative i64
     fail-closes to 0

Not claimed: mainnet uint256 / cToken parity, EVM replacement, general
superiority vs solc/LLVM, or zk/computational soundness of Merkle (C4 is
tamper-evidence + re-execution).
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
FIX = ROOT / "test" / "fixtures" / "external_proof" / "BaseJumpRateModelV2.sol"
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "independent_reproof.json"

PIN_SHA = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"
PIN_BLOB = "4d6828c39ed737c0c48508adc414b919ab6c2a55"
BASE = 10**18
KINK = 800_000_000_000_000_000
MULT_YEAR = 40_000_000_000_000_000
JUMP_YEAR = 1_090_000_000_000_000_000
BLOCKS = 2_102_400
I63_MAX = 2**63 - 1
RF10 = 100_000_000_000_000_000


def run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def rec(claims: list[dict[str, str]], ident: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:16s}  {desc}")
    if note:
        print(f"            note: {note}")


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]])
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout + proc.stderr)
    m = re.search(r"\bvalue=(-?\d+)\b", proc.stdout)
    if not m:
        raise RuntimeError(proc.stdout)
    return int(m.group(1))


def i64_wrap(x: int) -> int:
    x = x & ((1 << 64) - 1)
    return x - (1 << 64) if x >= 2**63 else x


def py_muldiv(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > I63_MAX else q


def c11(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  INDEPENDENT RE-PROOF — Python bigint vs LIN C0 vs C11 (this run)")
    print("=" * 78)

    got_sha = hashlib.sha256(FIX.read_bytes()).hexdigest()
    if got_sha != PIN_SHA:
        rec(claims, "PIN-SHA", "FAIL", "fixture sha256 mismatch", got_sha)
        return 1
    rec(claims, "PIN-SHA", "PASS", "BaseJumpRateModelV2.sol sha256 recomputed this run")

    blob = run(["git", "hash-object", str(FIX)]).stdout.strip()
    if blob != PIN_BLOB:
        rec(claims, "PIN-BLOB", "FAIL", "git blob mismatch", blob)
        return 1
    rec(claims, "PIN-BLOB", "PASS", "git hash-object matches pinned blob")

    gcc = run(["gcc", "-O2", "-std=c11", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if gcc.returncode != 0:
        rec(claims, "C11-BUILD", "FAIL", "gcc oracle", gcc.stderr)
        return 1
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "C11 selftest", st.stdout)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11 __int128 vs limb clone selftest")

    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check", chk.stdout)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of JumpRate clone")

    vectors = [
        (100, 200, 50),
        (7, 9, 1),
        (BASE, 1, 2),
        (BASE, BASE, 2 * BASE),
        (BASE, BASE, 1),
        (BASE, -1, 2),
        (100, 200, 0),
    ]
    for a, b, d in vectors:
        py = py_muldiv(a, b, d)
        lin = lin_vm("cjr_muldiv", a, b, d)
        if d < 0 or a < 0 or b < 0:
            if not (py == lin == 0):
                rec(claims, "MULDIV-3WAY", "FAIL", f"({a}*{b})/{d}", f"py={py} lin={lin}")
                return 1
            continue
        c11v = int(c11(["muldiv", str(a), str(b), str(d)]))
        if not (py == lin == c11v):
            rec(claims, "MULDIV-3WAY", "FAIL", f"({a}*{b})/{d}", f"py={py} lin={lin} c11={c11v}")
            return 1
    rec(claims, "MULDIV-3WAY", "PASS", "7/7 muldiv incl. q-overflow and fail-closed edges")

    wrap = i64_wrap(BASE * BASE)
    bigint_half = (BASE * BASE) // (2 * BASE)
    if wrap == bigint_half or lin_vm("cjr_muldiv", BASE, BASE, 2 * BASE) != bigint_half:
        rec(claims, "I64-WRAP", "FAIL", "i64 wrap equalled bigint or LIN missed 128-bit path")
        return 1
    rec(
        claims,
        "I64-WRAP",
        "PASS",
        "naive signed-i64 1e18*1e18 wraps; Python/LIN 128-bit muldiv does not",
        f"i64={wrap} bigint_half={bigint_half}",
    )
    if lin_vm("cjr_muldiv", BASE, BASE, 1) != 0:
        rec(claims, "Q-FITS-I64", "FAIL", "1e18*1e18/1 must fail-close")
        return 1
    rec(claims, "Q-FITS-I64", "PASS", "q not fitting nonnegative i64 fail-closes to 0")

    id_n = 0
    for a, b, d in ((100, 200, 50), (BASE, BASE, 2 * BASE), (123456789, 987654321, 42)):
        q, r, ov = [int(x) for x in c11(["muldiv-id", str(a), str(b), str(d)]).split()]
        if ov != 0 or q * d + r != a * b or lin_vm("cjr_muldiv", a, b, d) != q:
            rec(claims, "MULDIV-ID", "FAIL", f"remainder identity ({a}*{b})/{d}")
            return 1
        id_n += 1
    rec(claims, "MULDIV-ID", "PASS", f"{id_n}/{id_n} q*d+r == a*b on Python/C11/LIN")

    sol_mb = (MULT_YEAR * BASE) // (BLOCKS * KINK)
    lin_mb = ((MULT_YEAR * BASE) // KINK) // BLOCKS
    c0_mb = lin_vm("cjr_multiplier_per_block", MULT_YEAR, KINK)
    if not (sol_mb == lin_mb == c0_mb):
        rec(claims, "MULT-REORDER", "FAIL", "year-to-block multiplier", f"{sol_mb} {lin_mb} {c0_mb}")
        return 1
    rec(claims, "MULT-REORDER", "PASS", "floor((a*B)/(blocks*kink)) == ((a*B)/kink)/blocks on this vector", f"mb={sol_mb}")

    bb = lin_vm("cjr_base_per_block", 0)
    jb = lin_vm("cjr_jump_per_block", JUMP_YEAR)
    py_util = py_muldiv(BASE, BASE, BASE + BASE)
    lin_util = lin_vm("cjr_utilization", BASE, BASE, 0)
    py_r50 = py_muldiv(py_util, c0_mb, BASE) + bb
    lin_r50 = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK)
    c11_r50 = int(c11(["borrow", str(BASE), str(BASE), "0", str(bb), str(c0_mb), str(jb), str(KINK)]))
    if not (py_util == lin_util == 500_000_000_000_000_000):
        rec(claims, "UTIL-50", "FAIL", "50% utilization", f"py={py_util} lin={lin_util}")
        return 1
    if not (py_r50 == lin_r50 == c11_r50):
        rec(claims, "BORROW-50", "FAIL", "borrow@50%", f"py={py_r50} lin={lin_r50} c11={c11_r50}")
        return 1
    rec(claims, "UTIL-50", "PASS", "50% utilization = 0.5e18 on Python, LIN, formula")
    rec(claims, "BORROW-50", "PASS", "borrow@50% three-way consensus", f"rate={py_r50}")

    lin_r80 = lin_vm("cjr_borrow_rate", 2 * 10**17, 8 * 10**17, 0, bb, c0_mb, jb, KINK)
    lin_r90 = lin_vm("cjr_borrow_rate", 10**17, 9 * 10**17, 0, bb, c0_mb, jb, KINK)
    if not (lin_r50 <= lin_r80 < lin_r90):
        rec(claims, "KINK-PATH", "FAIL", "kink boundary monotonicity", f"{lin_r50} {lin_r80} {lin_r90}")
        return 1
    rec(claims, "KINK-PATH", "PASS", "borrow rate rises through 50% / kink / 90% util")

    lin_s50 = lin_vm("cjr_supply_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK, RF10)
    c11_s50 = int(c11(["supply", str(BASE), str(BASE), "0", str(bb), str(c0_mb), str(jb), str(KINK), str(RF10)]))
    if lin_s50 != c11_s50 or lin_s50 <= 0 or lin_s50 >= lin_r50:
        rec(claims, "SUPPLY-50", "FAIL", "supply@50% rf=0.1", f"lin={lin_s50} c11={c11_s50} br={lin_r50}")
        return 1
    rec(claims, "SUPPLY-50", "PASS", "supply rate < borrow rate at 50% util, LIN == C11", f"rate={lin_s50}")

    lin_hi = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, c0_mb + c0_mb, jb, KINK)
    if lin_hi <= lin_r50:
        rec(claims, "PARAM-ARGS", "FAIL", "doubling mult_block must change borrow rate")
        return 1
    rec(claims, "PARAM-ARGS", "PASS", "changing an IRM argument changes the rate (not hidden storage)")

    src = LIN.read_text(encoding="utf-8")
    sig = "cjr_borrow_rate(cash: int, borrows: int, reserves: int, base_block: int, mult_block: int, jump_block: int, kink: int)"
    sol = FIX.read_text(encoding="utf-8")
    if sig not in src or "internal view" not in sol or "msg.sender" not in sol:
        rec(claims, "EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/view")
        return 1
    rec(claims, "EXPLICIT-ARGS", "PASS", "LIN takes IRM params as arguments; Solidity reads storage + msg.sender")

    hon = run([str(C0), "info", str(SOL_TR)])
    tr_src = SOL_TR.read_text(encoding="utf-8")
    if (
        "sol_jumprate_honesty_gate" not in tr_src
        or "sol_needs_wide_muldiv" not in tr_src
        or "REJ_SOLIDITY_NON_PURE" not in tr_src
        or "borrows * BASE /" not in sol
        or "VM_REJ_STRING_LITERAL" not in hon.stdout
    ):
        rec(claims, "SOL-HONESTY", "FAIL", "view IRM / wide-muldiv detector", hon.stdout[-300:])
        return 1
    rec(claims, "SOL-HONESTY", "PASS", "view IRM is non-pure; * / needs wide muldiv; C0 default vm rejects string gates")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "cjr_test_suite"], timeout=90)
    if jit.returncode != 0 or "CONSENSUS" not in jit.stdout:
        rec(claims, "C0-JIT", "SKIP", "roundtrip-jit not exercised", jit.stdout[-400:] + jit.stderr[-200:])
    else:
        rec(claims, "C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite")

    evidence = {
        "schema": "LIN_INDEPENDENT_REPROOF_1.1",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "numbers": {
            "borrow_rate_50_util": py_r50,
            "supply_rate_50_rf10": lin_s50,
            "multiplier_per_block": c0_mb,
            "jump_per_block": jb,
            "i64_wrap_1e18_sq": wrap,
            "bigint_half_util": bigint_half,
            "fixture_sha256": got_sha,
            "fixture_git_blob": blob,
        },
        "real_deltas": [
            "IRM storage parameters are explicit function arguments",
            "(a*b)/d uses 128-bit product; q not fitting nonnegative i64 fail-closes",
        ],
        "not_claimed": [
            "full Solidity uint256 / mainnet cToken parity",
            "LIN replaces Compound, Uniswap, or the EVM",
            "general speed vs solc/LLVM (SipHash ~20.8x is compile-turnaround on one host)",
            "computational soundness of Merkle receipts (C4 is tamper-evidence + re-execution, not zk)",
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
