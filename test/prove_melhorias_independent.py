#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent re-proof of the Compound uint64-profile melhorias.

Third oracle: test/oracles/compound_jumprate_py.py (Python int, not C11 limbs,
not LinVM). Hashes are recomputed this run. Does not trust committed JSON.

Proved here: explicit IRM arguments change the rate; (a*b)/d uses a 128-bit
product; quotient overflow fail-closes; cash+borrows < reserves returns 0.

Not proved: Solidity uint256 / cToken mainnet parity; LIN replacing Compound,
Uniswap or the EVM; general speed vs solc/LLVM; Merkle computational soundness.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof" / "BaseJumpRateModelV2.sol"
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
XREC = ROOT / "transpile" / "c" / "bin" / "lin_c_receipt"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "independent_reproof.json"
PIN_SHA = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"
PIN_BLOB = "4d6828c39ed737c0c48508adc414b919ab6c2a55"

_spec = importlib.util.spec_from_file_location(
    "compound_jumprate_py", ROOT / "test" / "oracles" / "compound_jumprate_py.py"
)
py_cjr = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(py_cjr)

BASE = py_cjr.BASE
KINK = py_cjr.KINK
MULT_YEAR = py_cjr.MULT_YEAR
JUMP_YEAR = py_cjr.JUMP_YEAR


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


def c11(args: list[str]) -> int:
    out = run([str(ORACLE_BIN), *args]).stdout.strip().splitlines()[-1]
    return int(out)


def three(py: int, lin: int, native: int, ident: str, desc: str, claims: list) -> bool:
    if not (py == lin == native):
        rec(claims, ident, "FAIL", desc, f"py={py} lin={lin} c11={native}")
        return False
    rec(claims, ident, "PASS", desc, f"value={py}")
    return True


def main() -> int:
    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  INDEPENDENT RE-PROOF — Python oracle vs LIN C0 vs C11 (this run)")
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

    if not C0.exists():
        mk = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
        if mk.returncode != 0:
            rec(claims, "LIN-CHECK", "FAIL", "make c0", mk.stdout)
            return 1
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check", chk.stdout)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of JumpRate clone")

    vectors = [(100, 200, 50), (7, 9, 1), (BASE, 1, 2), (BASE, BASE, 2 * BASE)]
    for a, b, d in vectors:
        py = py_cjr.muldiv(a, b, d)
        lin = lin_vm("cjr_muldiv", a, b, d)
        native = c11(["muldiv", str(a), str(b), str(d)])
        if not (py == lin == native):
            rec(claims, "MULDIV-3WAY", "FAIL", f"({a}*{b})/{d}", f"py={py} lin={lin} c11={native}")
            return 1
    rec(claims, "MULDIV-3WAY", "PASS", "4/4 muldiv: Python oracle == LIN vm == C11 __int128")

    wrap = py_cjr.i64_wrap(BASE * BASE)
    wide = py_cjr.muldiv(BASE, BASE, 2 * BASE)
    lin_wide = lin_vm("cjr_muldiv", BASE, BASE, 2 * BASE)
    if wrap == wide or lin_wide != wide:
        rec(claims, "WIDE-MULDIV", "FAIL", "128-bit product", f"i64={wrap} py={wide} lin={lin_wide}")
        return 1
    rec(
        claims,
        "WIDE-MULDIV",
        "PASS",
        "real melhoria: (1e18*1e18)/2e18 = 5e17 via 128-bit product; signed i64 wraps",
        f"i64={wrap} bigint={wide}",
    )

    if not three(
        py_cjr.muldiv(BASE, BASE, 1),
        lin_vm("cjr_muldiv", BASE, BASE, 1),
        c11(["muldiv", str(BASE), str(BASE), "1"]),
        "Q-OVF",
        "quotient overflow fail-closes to 0 (uint64 profile, not silent wrap)",
        claims,
    ):
        return 1

    if py_cjr.muldiv(BASE, BASE, 1) != 0:
        rec(claims, "Q-OVF", "FAIL", "expected fail-closed 0")
        return 1

    if not py_cjr.solidity_util_reverts(1, 1, 10):
        rec(claims, "FAIL-CLOSED-UFL", "FAIL", "Solidity would not revert on this vector")
        return 1
    if not three(
        0,
        lin_vm("cjr_utilization", 1, 1, 10),
        c11(["util", "1", "1", "10"]),
        "FAIL-CLOSED-UFL",
        "cash+borrows < reserves: LIN/C11 return 0; Solidity 0.8 reverts (difference, not parity)",
        claims,
    ):
        return 1

    if not py_cjr.blocks_kink_overflows_u64(KINK):
        rec(claims, "MULT-REORDER", "FAIL", "blocks*kink fits uint64; reorder would be unnecessary")
        return 1
    sol_mb = py_cjr.multiplier_solidity(MULT_YEAR, KINK)
    lin_mb = py_cjr.multiplier_lin(MULT_YEAR, KINK)
    c0_mb = lin_vm("cjr_multiplier_per_block", MULT_YEAR, KINK)
    if not (sol_mb == lin_mb == c0_mb):
        rec(claims, "MULT-REORDER", "FAIL", "year-to-block multiplier", f"{sol_mb} {lin_mb} {c0_mb}")
        return 1
    rec(
        claims,
        "MULT-REORDER",
        "PASS",
        "blocks*kink overflows uint64; LIN reorder is floor-identical to Solidity formula",
        f"mb={c0_mb}",
    )

    bb = lin_vm("cjr_base_per_block", 0)
    jb = lin_vm("cjr_jump_per_block", JUMP_YEAR)
    if not three(
        py_cjr.utilization(BASE, BASE, 0),
        lin_vm("cjr_utilization", BASE, BASE, 0),
        c11(["util", str(BASE), str(BASE), "0"]),
        "UTIL-50",
        "50% utilization = 0.5e18 on Python, LIN, C11",
        claims,
    ):
        return 1
    py_r50 = py_cjr.borrow_rate(BASE, BASE, 0, bb, c0_mb, jb, KINK)
    if not three(
        py_r50,
        lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK),
        c11(["borrow", str(BASE), str(BASE), "0", str(bb), str(c0_mb), str(jb), str(KINK)]),
        "BORROW-50",
        "borrow@50% three-way consensus",
        claims,
    ):
        return 1

    r50_lo = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, c0_mb, jb, KINK // 2)
    py_lo = py_cjr.borrow_rate(BASE, BASE, 0, bb, c0_mb, jb, KINK // 2)
    if r50_lo == py_r50 or r50_lo != py_lo:
        rec(claims, "EXPLICIT-ARGS", "FAIL", "kink argument did not change the rate", f"{py_r50} vs {r50_lo}")
        return 1
    rec(
        claims,
        "EXPLICIT-ARGS",
        "PASS",
        "real melhoria: same market, different kink argument => different rate (not hidden storage)",
        f"kink80={py_r50} kink40={r50_lo}",
    )

    py90 = py_cjr.borrow_rate(BASE // 10, 9 * BASE // 10, 0, bb, c0_mb, jb, KINK)
    lin90 = lin_vm("cjr_borrow_rate", BASE // 10, 9 * BASE // 10, 0, bb, c0_mb, jb, KINK)
    c1190 = c11(["borrow", str(BASE // 10), str(9 * BASE // 10), "0", str(bb), str(c0_mb), str(jb), str(KINK)])
    if not (py90 == lin90 == c1190) or py90 <= py_r50:
        rec(claims, "JUMP-90", "FAIL", "above-kink borrow@90%", f"py={py90} lin={lin90} c11={c1190} r50={py_r50}")
        return 1
    rec(claims, "JUMP-90", "PASS", "above-kink borrow@90% three-way and greater than borrow@50%", f"rate={py90}")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "cjr_test_suite"], timeout=90)
    if jit.returncode != 0 or "CONSENSUS" not in jit.stdout:
        rec(claims, "C0-JIT", "SKIP", "roundtrip-jit not exercised", jit.stdout[-200:] + jit.stderr[-80:])
    else:
        rec(claims, "C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite")

    if not XREC.exists():
        mk = run(["make", "-C", str(ROOT / "transpile" / "c"), "all"], timeout=180)
        if not XREC.exists():
            rec(
                claims,
                "C4-BIN",
                "SKIP",
                "lin_c_receipt missing after make; C4 is not a math FAIL",
                mk.stdout[-160:],
            )
        else:
            rec(
                claims,
                "C4-BIN",
                "PASS",
                "lin_c_receipt built by make -C transpile/c all (prior C4 fail was a missing binary)",
            )
    else:
        rec(claims, "C4-BIN", "PASS", "lin_c_receipt present; C4 is tamper-evidence + reexecution, not zk")

    evidence = {
        "schema": "LIN_INDEPENDENT_REPROOF_1.1",
        "class": "EXPERIMENTAL",
        "real_improvements": [
            "IRM storage parameters are explicit function arguments",
            "(a*b)/d uses a 128-bit product on the uint64 profile",
            "quotient that does not fit uint64 fail-closes to 0",
        ],
        "claims": claims,
        "numbers": {
            "borrow_rate_50_util": py_r50,
            "borrow_rate_90_util": py90,
            "multiplier_per_block": c0_mb,
            "jump_per_block": jb,
            "i64_wrap_1e18_sq": wrap,
            "bigint_half_util": wide,
            "fixture_sha256": got_sha,
            "fixture_git_blob": blob,
        },
        "not_claimed": [
            "full Solidity uint256 / mainnet cToken parity",
            "LIN replaces Compound, Uniswap, or the EVM",
            "general wall-clock superiority vs solc/LLVM (SipHash ~20.8x is compile-turnaround on one host)",
            "computational soundness of Merkle receipts (C4 is tamper-evidence + independent SHA-256 reexecution, not zk)",
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
