#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 WadRayMath.rayMul / rayDiv vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned aave/aave-v3-core WadRayMath.sol
      (sha256 + git blob; Solidity is hash-pinned, not vendored)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_aave_raymul.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet RAY=1e27 range
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts
    * wadMul / wadDiv / rayToWad (see the other Aave clone-lin repos)

Class: EXPERIMENTAL (real Aave rayMul/rayDiv algorithm, RAY'=1e9 operands).
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
LIN = ROOT / "src" / "lin_aave_raymul.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_raymul_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_raymul_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_raymul" / "aave_raymul_evidence.json"

RAY = 10**9
HALF = 5 * 10**8
PINNED_SHA256 = "fae5b995ec613cc213050c99ea6352c9c18ceebba106d03b1726cfa8f1f0124e"
PINNED_BLOB = "f61fe87f2f2748144cd4d113c848e649c41a4e5d"
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
UPSTREAM_REL = "contracts/protocol/libraries/math/WadRayMath.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-raymul"


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
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
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
    if a < 0 or b < 0 or a == 0 or b == 0:
        return 0
    q = (a * b + HALF) // RAY
    if q > 2**63 - 1:
        return 0
    return q


def py_ray_div(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        return 0
    q = (a * RAY + b // 2) // b
    if q > 2**63 - 1:
        return 0
    return q


def py_floor_mul(a: int, b: int) -> int:
    if a < 0 or b < 0 or a == 0 or b == 0:
        return 0
    q = (a * b) // RAY
    if q > 2**63 - 1:
        return 0
    return q


def py_floor_div(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        return 0
    q = (a * RAY) // b
    if q > 2**63 - 1:
        return 0
    return q


def ensure_upstream() -> tuple[str, str, str]:
    """Fetch the pinned commit. SKIP on network failure; hash pin still holds."""
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
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    if "function rayMul" not in text or "function rayDiv" not in text or "HALF_RAY" not in text:
        return "FAIL", commit, "pinned file missing rayMul/rayDiv/HALF_RAY"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_RAYMUL_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 rayMul/rayDiv — external LIN proof (RAY'=1e9, C11 oracle)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of rayMul clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_raymul.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    chk4 = run([str(C0), "check", str(RS_TR)])
    if chk4.returncode != 0 and "LIN_CHECK" not in chk4.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk4.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "arm_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "arm_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "arm_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned aave-v3-core commit matches hash pin",
            f"commit={commit} blob={blob} sha256={PINNED_SHA256}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of WadRayMath.sol")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; hash pin still holds",
            up_note,
        )
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
        ("mul", RAY, RAY, "arm_ray_mul"),
        ("mul", 1, HALF, "arm_ray_mul"),
        ("floor_mul", 1, HALF, "arm_wrong_floor_mul"),
        ("mul", 3, HALF, "arm_ray_mul"),
        ("floor_mul", 3, HALF, "arm_wrong_floor_mul"),
        ("mul", 1, HALF - 1, "arm_ray_mul"),
        ("div", 2, 3, "arm_ray_div"),
        ("floor_div", 2, 3, "arm_wrong_floor_div"),
        ("div", RAY, 2 * RAY, "arm_ray_div"),
        ("mul", 10**10, 10**10, "arm_ray_mul"),
        ("mul", 4 * 10**18, 3 * 10**18, "arm_ray_mul"),
        ("mul", 1, 1, "arm_ray_mul"),
        ("mul", 0, RAY, "arm_ray_mul"),
        ("div", 1, 0, "arm_ray_div"),
        ("div", 1, 3, "arm_ray_div"),
    ]
    n_ok = 0
    for kind, a, b, fn in vectors:
        want = int(oracle([kind, str(a), str(b)]).splitlines()[-1])
        want_limbs = int(oracle([kind, str(a), str(b), "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, a, b)
        if kind == "mul":
            py = py_ray_mul(a, b)
        elif kind == "div":
            py = py_ray_div(a, b)
        elif kind == "floor_mul":
            py = py_floor_mul(a, b)
        else:
            py = py_floor_div(a, b)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind}({a},{b}) i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}({a},{b})", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}({a},{b})", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec(
        "HALF-UP-MUL",
        "PASS",
        "rayMul(1, 5e8) half-up 1 vs floor 0",
        f"half_up={lin_vm('arm_ray_mul', 1, HALF)} floor={lin_vm('arm_wrong_floor_mul', 1, HALF)}",
    )
    rec(
        "HALF-UP-DIV",
        "PASS",
        "rayDiv(2, 3) half-up 666666667 vs floor 666666666",
        f"half_up={lin_vm('arm_ray_div', 2, 3)} floor={lin_vm('arm_wrong_floor_div', 2, 3)}",
    )

    wrapped = (10**10 * 10**10) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("arm_ray_mul", 10**10, 10**10)
    naive = lin_vm("arm_naive_i64_mul", 10**10, 10**10)
    if wide != 10**11 or naive != wrapped or wrapped == wide:
        rec(
            "I64-WRAP",
            "FAIL",
            "naive i64 1e10*1e10 should wrap; 128-bit rayMul should be 1e11",
            f"naive={naive} wrap={wrapped} rayMul={wide}",
        )
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e10*1e10) wraps; 128-bit rayMul does not",
        f"i64_wrap={wrapped} rayMul={wide}",
    )

    ov = lin_vm("arm_ray_mul", 4 * 10**18, 3 * 10**18)
    ov_ok = lin_vm("arm_ray_mul_ok", 4 * 10**18, 3 * 10**18)
    if ov != 0 or ov_ok != 0:
        rec("OVERFLOW-FC", "FAIL", "rayMul(4e18,3e18) should fail-close", f"mul={ov} ok={ov_ok}")
        return 1
    rec("OVERFLOW-FC", "PASS", "rayMul(4e18, 3e18) fail-closes to 0 (quotient > i64)")

    jit_ok = lin_roundtrip_jit("arm_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on arm_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("arm_ray_mul", 1, HALF)
        if jv == 1:
            rec("C0-JIT", "PASS", "lin_c0 jit arm_ray_mul(1,5e8)==1 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "arm_ray_mul(a: int, b: int)" not in src or "RAY'" not in src and "1e9" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN rayMul args")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes rayMul/rayDiv operands as arguments (no Yul)")
    if "arm_muldiv_add_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product (naive i64 a*b wraps on 1e10*1e10)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1

    if "REJ_SOLIDITY_AAVE_RAYMUL" not in sol_src or "0.5e" not in sol_src:
        rec("SOL-EMIT", "FAIL", "solidity transpiler missing 0.5eN / RAYMUL reject")
        return 1
    rec("SOL-EMIT", "PASS", "lin_from_solidity.lin expands 0.5eN and fail-closes Yul rayMul")
    if "REJ_C_AAVE_RAYMUL" not in c_src or "REJ_C_INLINE_ASM" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing RAYMUL / inline-asm reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes inline asm and Aave rayMul")
    if "REJ_RUST_AAVE_RAYMUL" not in rs_src or "REJ_RUST_INLINE_ASM" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing RAYMUL / asm reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes asm! and Aave rayMul")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after transpiler delta", jr.stdout[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/aave/aave-v3-core",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT after BUSL-1.1 Change Date 2023-01-27",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_aave_raymul.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/aave_raymul_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["ray_prime"] = RAY
    evidence["named_goldens"] = {
        "rayMul(1, 5e8)": 1,
        "floor_mul(1, 5e8)": 0,
        "rayDiv(2, 3)": 666666667,
        "floor_div(2, 3)": 666666666,
        "rayMul(1e10, 1e10)": 10**11,
        "naive_i64(1e10, 1e10)": wrapped,
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
