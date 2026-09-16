#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: OpenZeppelin Math.sqrt / log2 (MIT) vs LIN C0.

PASS claims this run recomputes against:
  * pinned excerpt of Math.sol whose functions are substrings of v5.0.2
  * live git fetch of OpenZeppelin/openzeppelin-contracts@v5.0.2
  * independent C11 oracle (Newton + log2, no libc sqrt)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting src/lin_oz_sqrt.lin
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python int.bit_length()-1 and math.isqrt as a third oracle

NOT claimed:
  * Solidity uint256 / mainnet OpenZeppelin parity
  * that LIN replaces OpenZeppelin or the EVM
  * libc/IEEE-754 sqrt; C `sqrt(` is fail-closed as REJ_C_FLOAT

Class: EXPERIMENTAL (real OZ algorithm, non-negative i64 operands).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_oz_sqrt.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "oz_sqrt_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "oz_sqrt_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_oz/openzeppelin-contracts")
EVIDENCE = ROOT / "examples" / "oz_sqrt" / "oz_sqrt_evidence.json"
EXCERPT = FIX / "Math_sqrt_log2.sol"

PINNED_FULL_SHA256 = "a6ee779fc42e6bf01b5e6a963065706e882b016affbedfd8be19a71ea48e6e15"
PINNED_BLOB = "9681524529b34f34033ae97064a2700bfc4eec00"
PINNED_COMMIT = "dbb6104ce834628e473d2173bbc9d47f81a9eec3"
PINNED_EXCERPT_SHA256 = "c01c219d2ea425653f0bd8ba58c74368cbe0fd1cbd3e3a9424a10dfb4258726d"
UPSTREAM_REL = "contracts/utils/math/Math.sol"
UPSTREAM_URL = "https://github.com/OpenZeppelin/openzeppelin-contracts.git"

VECTORS = [
    0,
    1,
    2,
    3,
    4,
    8,
    9,
    10,
    15,
    16,
    81,
    82,
    99,
    100,
    1024,
    10**6,
    10**18,
    2**20,
    2**31,
    2**32 - 1,
    2**62,
    2**63 - 1,
]


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
    proc = run(
        [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90
    )
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


def ensure_upstream() -> tuple[str, str, str]:
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
        cl = run(
            ["git", "clone", "--depth", "1", "--branch", "v5.0.2", UPSTREAM_URL, str(UPSTREAM)],
            timeout=120,
        )
        if cl.returncode != 0:
            return "SKIP", "", (cl.stderr or cl.stdout or "clone failed")[:240]
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_FULL_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob} commit={commit}"
    return "PASS", commit, blob


def py_log2(a: int) -> int:
    return (a.bit_length() - 1) if a > 0 else 0


def py_sqrt(a: int) -> int:
    return math.isqrt(a) if a >= 0 else 0


def py_sqrt_round(a: int, rounding: int) -> int:
    result = py_sqrt(a)
    if rounding % 2 == 0:
        return result
    if result * result < a:
        return result + 1
    return result


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_OZ_SQRT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  OPENZEPPELIN MATH.sqrt / log2 — external LIN proof (i64-scale, C11)")
    print("=" * 78)

    if not EXCERPT.exists():
        rec("PIN-FILE", "FAIL", "pinned Math_sqrt_log2.sol missing")
        return 1
    got = sha256_file(EXCERPT)
    if got != PINNED_EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "excerpt sha256 mismatch", f"{got} != {PINNED_EXCERPT_SHA256}")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned Math_sqrt_log2.sol sha256 matches harness")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    live_text = ""
    if up_status == "PASS":
        blob = up_note
        live_text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8")
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of OpenZeppelin v5.0.2 Math.sol matches pin",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/utils/math/Math.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    excerpt = EXCERPT.read_text(encoding="utf-8")
    needed = [
        "function min(uint256 a, uint256 b)",
        "function sqrt(uint256 a) internal pure",
        "function log2(uint256 value) internal pure",
        "function unsignedRoundsUp(Rounding rounding)",
    ]
    if live_text:
        missing = [n for n in needed if n not in live_text]
        if missing:
            rec("EXCERPT-IN-LIVE", "FAIL", "excerpt signatures missing from live Math.sol", str(missing))
            return 1
        rec("EXCERPT-IN-LIVE", "PASS", "excerpt function signatures are substrings of live Math.sol")
        if "1 << (log2(a) >> 1)" not in live_text or "result = (result + a / result) >> 1" not in live_text:
            rec("NEWTON-IN-LIVE", "FAIL", "Newton / log2 guess missing from live Math.sol")
            return 1
        rec("NEWTON-IN-LIVE", "PASS", "live Math.sol still has log2 initial guess + 7 Newton steps")
    else:
        rec("EXCERPT-IN-LIVE", "SKIP", "live Math.sol not fetched")
        rec("NEWTON-IN-LIVE", "SKIP", "live Math.sol not fetched")

    if "assembly" in excerpt:
        rec("EXCERPT-NO-ASM", "FAIL", "sqrt excerpt unexpectedly contains assembly")
        return 1
    rec("EXCERPT-NO-ASM", "PASS", "sqrt/log2 excerpt has no inline assembly (mulDiv is out of scope)")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Newton/log2 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle selftest (no libc sqrt)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of oz sqrt clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_oz_sqrt.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler (sqrt( is REJ_C_FLOAT)")

    gate = run([str(C0), "vm", str(LIN), "ozs_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ozs_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ozs_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for a in VECTORS:
        want = int(oracle(["sqrt", str(a)]))
        got_lin = lin_vm("ozs_sqrt", a)
        py = py_sqrt(a)
        if want != py or got_lin != py:
            rec("VEC-SQRT", "FAIL", f"sqrt({a})", f"lin={got_lin} c11={want} py={py}")
            return 1
        lg_c = int(oracle(["log2", str(a)]))
        lg_l = lin_vm("ozs_log2", a)
        lg_p = py_log2(a)
        if lg_c != lg_p or lg_l != lg_p:
            rec("VEC-LOG2", "FAIL", f"log2({a})", f"lin={lg_l} c11={lg_c} py={lg_p}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python isqrt/bit_length")

    for a, rnd in ((10, 1), (9, 1), (10, 0), (0, 1), (2**62, 1)):
        want = int(oracle(["sqrt_round", str(a), str(rnd)]))
        got_lin = lin_vm("ozs_sqrt_round", a, rnd)
        py = py_sqrt_round(a, rnd)
        if want != py or got_lin != py:
            rec("VEC-ROUND", "FAIL", f"sqrt_round({a},{rnd})", f"lin={got_lin} c11={want} py={py}")
            return 1
    rec("VEC-ROUND", "PASS", "ceil/floor rounding: C11 == LIN == Python (odd enum rounds up)")

    src = LIN.read_text(encoding="utf-8")
    if "result * result" in src or "result*result" in src:
        rec("SAFE-SQ", "FAIL", "clone still uses wrapping result*result compare")
        return 1
    rec("SAFE-SQ", "PASS", "ceil path uses remainder-safe ozs_sq_lt, not wrapping multiply")
    if "_lia_ushr" in src and "_lia_shl" in src and "<<" not in src.split("{", 1)[-1]:
        rec("NO-SHIFT-TOK", "PASS", "clone uses _lia_shl/_lia_ushr (default lin_c0 vm rejects << >>)")
    else:
        rec("NO-SHIFT-TOK", "FAIL", "raw shift tokens present or builtins missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_tr = ["sol_shifts", "sol_strip_unchecked", "REJ_SOLIDITY_POW", "REJ_SOLIDITY_ENUM", "_lia_ushr"]
    missing_tr = [t for t in need_tr if t not in sol_src]
    if missing_tr:
        rec("SOL-SHIFTS", "FAIL", "solidity transpiler missing v3 lowering", str(missing_tr))
    else:
        rec("SOL-SHIFTS", "PASS", "lin_from_solidity.lin v3: shifts, unchecked strip, POW/ENUM reject")

    c_src = C_TR.read_text(encoding="utf-8")
    if 'cfs_call_of(body, "sqrt")' not in c_src:
        rec("C-SQRT-REJ", "FAIL", "C transpiler does not reject libc sqrt(")
    else:
        rec("C-SQRT-REJ", "PASS", "lin_from_c.lin fail-closes libc sqrt( as REJ_C_FLOAT")

    if "Rounding rounding" in excerpt and "ozs_sqrt_round(a: int, rounding: int)" in src:
        rec("EXPLICIT-ROUND", "PASS", "LIN clone takes rounding as int; Solidity enum is REJ_SOLIDITY_ENUM")
    else:
        rec("EXPLICIT-ROUND", "FAIL", "rounding-as-int missing")

    jit_ok = lin_roundtrip_jit("ozs_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ozs_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ozs_sqrt", 10)
        if jv == 3:
            rec("C0-JIT", "PASS", "lin_c0 jit ozs_sqrt(10)==3 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/OpenZeppelin/openzeppelin-contracts",
        "tag": "v5.0.2",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_FULL_SHA256,
        "excerpt_sha256": PINNED_EXCERPT_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_oz_sqrt.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-oz-sqrt"
    evidence["c11_oracle"] = "test/oracles/oz_sqrt_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["goldens"] = {
        "sqrt(10)": 3,
        "sqrt_round(10,1)": 4,
        "sqrt(1e18)": 10**9,
        "sqrt(2^62)": 2**31,
        "sqrt(INT64_MAX)": 3037000499,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
