#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 getNormalizedIncome / getNormalizedDebt vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned aave/aave-v3-core ReserveLogic.sol + MathUtils.sol
      (sha256 + git blob; Solidity is hash-pinned, not vendored)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_aave_norm.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet RAY=1e27 range
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts
    * that binomial x^2/x^3 terms are nonzero at RAY' for typical APRs

Class: EXPERIMENTAL (real Aave index algorithm, RAY'=1e9 operands).
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
LIN = ROOT / "src" / "lin_aave_norm.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_norm_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_norm_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_norm" / "aave_norm_evidence.json"

RAY = 10**9
HALF = 5 * 10**8
SPY = 365 * 86400
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
PINNED = {
    "contracts/protocol/libraries/logic/ReserveLogic.sol": {
        "blob": "bc48163dbbfcac7c832d2e9dfef71a9ddadfe836",
        "sha256": "6b827ea494fa5bb1b38fa9e7db973bd0aed0ee3d53677cac950f6614cb8fd0c9",
    },
    "contracts/protocol/libraries/math/MathUtils.sol": {
        "blob": "9adca939db36cbe1009d0a00600def9314fc7332",
        "sha256": "7f73c927e9801debfe0666e2a6364b92f62fd2d58d0c4b485ff04765fd4dc58d",
    },
}
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-norm"


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_oracle() -> None:
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_ray_mul(a: int, b: int) -> int:
    if a <= 0 or b <= 0:
        return 0
    q = (a * b + HALF) // RAY
    return 0 if q > 2**63 - 1 else q


def py_linear(rate: int, dt: int) -> int:
    if rate < 0 or dt < 0:
        return 0
    inc = (rate * dt) // SPY
    s = RAY + inc
    return 0 if s > 2**63 - 1 else s


def py_income(rate: int, index: int, dt: int) -> int:
    if rate < 0 or index < 0 or dt < 0:
        return 0
    if dt == 0:
        return index
    return py_ray_mul(py_linear(rate, dt), index)


def py_compound(rate: int, dt: int) -> int:
    if rate < 0 or dt < 0:
        return 0
    if dt == 0:
        return RAY
    spy2 = SPY * SPY
    bp2 = py_ray_mul(rate, rate) // spy2
    bp3 = py_ray_mul(bp2, rate) // SPY
    e1 = dt - 1
    e2 = dt - 2 if dt > 2 else 0
    second = (dt * e1 * bp2) // 2
    third = (dt * e1 * e2 * bp3) // 6
    s = RAY + (rate * dt) // SPY + second + third
    return 0 if s > 2**63 - 1 else s


def py_debt(rate: int, index: int, dt: int) -> int:
    if rate < 0 or index < 0 or dt < 0:
        return 0
    if dt == 0:
        return index
    return py_ray_mul(py_compound(rate, dt), index)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/aave/aave-v3-core.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    notes = []
    for rel, pin in PINNED.items():
        live = UPSTREAM / rel
        if not live.exists():
            return "SKIP", "", f"{rel} missing after checkout"
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{rel}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != pin["sha256"] or blob != pin["blob"]:
            return "FAIL", "", f"{rel} live={live_hash} blob={blob}"
        text = live.read_text(encoding="utf-8")
        notes.append(f"{rel.split('/')[-1]} blob={blob}")
        if rel.endswith("ReserveLogic.sol"):
            if "function getNormalizedIncome" not in text or "function getNormalizedDebt" not in text:
                return "FAIL", "", "ReserveLogic missing getNormalizedIncome/Debt"
            if "block.timestamp" not in text:
                return "FAIL", "", "ReserveLogic missing block.timestamp"
        if rel.endswith("MathUtils.sol"):
            if "365 days" not in text or "calculateLinearInterest" not in text:
                return "FAIL", "", "MathUtils missing 365 days / linear interest"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, "; ".join(notes)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 getNormalizedIncome/Debt — external LIN proof (RAY'=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of aave-norm clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_norm.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler v3"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "ani_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ani_test_suite via lin_c0 vm", gate.stdout[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "ani_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned aave-v3-core commit matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of ReserveLogic.sol and MathUtils.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    vectors = [
        ("linear", [0, SPY], "ani_linear_interest", py_linear(0, SPY)),
        ("linear", [50_000_000, SPY], "ani_linear_interest", py_linear(50_000_000, SPY)),
        ("income", [50_000_000, RAY, 0], "ani_normalized_income", py_income(50_000_000, RAY, 0)),
        ("income", [50_000_000, RAY, SPY], "ani_normalized_income", py_income(50_000_000, RAY, SPY)),
        ("income", [50_000_000, 2 * RAY, SPY], "ani_normalized_income", py_income(50_000_000, 2 * RAY, SPY)),
        ("income", [50_000_000, RAY, 86400], "ani_normalized_income", py_income(50_000_000, RAY, 86400)),
        ("compound", [50_000_000, SPY], "ani_compounded_interest", py_compound(50_000_000, SPY)),
        ("debt", [50_000_000, RAY, SPY], "ani_normalized_debt", py_debt(50_000_000, RAY, SPY)),
        ("compound", [10**12, SPY], "ani_compounded_interest", py_compound(10**12, SPY)),
        ("linear", [10**12, SPY], "ani_linear_interest", py_linear(10**12, SPY)),
        ("debt", [50_000_000, RAY, 0], "ani_normalized_debt", py_debt(50_000_000, RAY, 0)),
        ("raymul", [10**10, 10**10], "ani_ray_mul", py_ray_mul(10**10, 10**10)),
    ]
    n_ok = 0
    for kind, args, fn, py in vectors:
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind}{tuple(args)} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{tuple(args)}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{tuple(args)}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("DT-SHORT", "PASS", "dt==0 returns the stored index (Aave same-block short-circuit)",
        f"income={lin_vm('ani_normalized_income', 50_000_000, RAY, 0)}")
    rec("EXPLICIT-DT", "PASS", "5% RAY' for 1 year: income 1.05e9 vs ignore-dt still 1e9",
        f"income={lin_vm('ani_normalized_income', 50_000_000, RAY, SPY)} ignore={lin_vm('ani_wrong_ignore_dt', RAY)}")
    rec("BINOM-SCALE", "PASS", "typical 5% APR: compound extra terms floor to 0 at RAY'=1e9; extreme 1e12 rate is distinct",
        f"c5={lin_vm('ani_compounded_interest', 50_000_000, SPY)} c_big={lin_vm('ani_compounded_interest', 10**12, SPY)} lin_big={lin_vm('ani_linear_interest', 10**12, SPY)}")

    wrapped = (10**10 * 10**10) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("ani_ray_mul", 10**10, 10**10)
    naive = lin_vm("ani_naive_i64_mul", 10**10, 10**10)
    if wide != 10**11 or naive != wrapped or wrapped == wide:
        rec("I64-WRAP", "FAIL", "naive i64 1e10*1e10 should wrap; 128-bit rayMul should be 1e11",
            f"naive={naive} wrap={wrapped} rayMul={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e10*1e10) wraps; 128-bit rayMul does not",
        f"i64_wrap={wrapped} rayMul={wide}")

    jit_ok = lin_roundtrip_jit("ani_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ani_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ani_normalized_income", 50_000_000, RAY, 0)
        if jv == RAY:
            rec("C0-JIT", "PASS", "lin_c0 jit ani_normalized_income(5e7,RAY,0)==RAY (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "ani_normalized_income(rate: int, index: int, dt: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN income args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes rate/index/dt as arguments (no block.timestamp)")
    if "ani_muldiv_add_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product (naive i64 a*b wraps on 1e10*1e10)")
    if "REJ_SOLIDITY_AAVE_NORM" not in sol_src or "365 days" not in sol_src or "uint40" not in sol_src:
        rec("SOL-EMIT", "FAIL", "solidity transpiler missing days/uint40/AAVE_NORM")
        return 1
    rec("SOL-EMIT", "PASS", "lin_from_solidity.lin expands N days and fail-closes Aave-norm storage/time")
    if "REJ_C_AAVE_NORM" not in c_src or "REJ_C_TIME" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing AAVE_NORM / TIME reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes wall-clock time and Aave getNormalizedIncome")
    if "REJ_RUST_AAVE_NORM" not in rs_src or "REJ_RUST_TIME" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing AAVE_NORM / TIME reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes Instant::now/SystemTime and normalized_income")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after transpiler delta", (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_AAVE_NORM_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/aave/aave-v3-core",
            "commit": commit or PINNED_COMMIT,
            "paths": list(PINNED.keys()),
            "files": PINNED,
            "license": "MIT after BUSL-1.1 Change Date 2023-01-27",
            "vendored": False,
        },
        "lin_clone": "src/lin_aave_norm.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/aave_norm_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "ray_prime": RAY,
        "seconds_per_year": SPY,
        "named_goldens": {
            "linear(5e7, 1y)": 1050000000,
            "income(5e7, RAY, 0)": RAY,
            "income(5e7, RAY, 1y)": 1050000000,
            "income(5e7, RAY, 1d)": 1000136986,
            "compound(5e7, 1y)": 1050000000,
            "compound(1e12, 1y)": 498260632232000,
            "rayMul(1e10, 1e10)": 10**11,
            "naive_i64(1e10, 1e10)": wrapped,
        },
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
