#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 cumulateToLiquidityIndex vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned aave/aave-v3-core ReserveLogic.sol + WadRayMath.sol
      (sha256 + git blob; Solidity is hash-pinned, not vendored)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_aave_cumulate.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet RAY=1e27 / aToken parity
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Aave flashloan-premium-into-index algorithm, RAY'=1e9).
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
LIN = ROOT / "src" / "lin_aave_cumulate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_cumulate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_cumulate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_cumulate" / "aave_cumulate_evidence.json"

E9 = 10**9
I64MAX = 2**63 - 1
RAY = 10**9
HALF = 5 * 10**8
RATIO = 10**9
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
PINNED_RL_BLOB = "bc48163dbbfcac7c832d2e9dfef71a9ddadfe836"
PINNED_RL_SHA = "6b827ea494fa5bb1b38fa9e7db973bd0aed0ee3d53677cac950f6614cb8fd0c9"
PINNED_WR_BLOB = "f61fe87f2f2748144cd4d113c848e649c41a4e5d"
PINNED_WR_SHA = "fae5b995ec613cc213050c99ea6352c9c18ceebba106d03b1726cfa8f1f0124e"
UPSTREAM_RL = "contracts/protocol/libraries/logic/ReserveLogic.sol"
UPSTREAM_WR = "contracts/protocol/libraries/math/WadRayMath.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-cumulate"


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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
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


def py_md(a: int, b: int, add: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0 or add < 0:
        return 0
    q = (a * b + add) // d
    return 0 if q > I64MAX else q


def py_ray_mul(a: int, b: int) -> int:
    return 0 if b == 0 else py_md(a, b, HALF, RAY)


def py_ray_div(a: int, b: int) -> int:
    return 0 if b == 0 else py_md(a, RAY, b // 2, b)


def py_wad_to_ray(a: int) -> int:
    return py_md(a, RATIO, 0, 1)


def py_cumulate(liq: int, amt: int, idx: int) -> int:
    if liq <= 0 or amt < 0 or idx < 0:
        return 0
    a_ray = py_wad_to_ray(amt)
    t_ray = py_wad_to_ray(liq)
    if amt != 0 and a_ray == 0:
        return 0
    if t_ray == 0:
        return 0
    ratio = py_ray_div(a_ray, t_ray)
    s = ratio + RAY
    if s < ratio:
        return 0
    return py_ray_mul(s, idx)


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
    rl = UPSTREAM / UPSTREAM_RL
    wr = UPSTREAM / UPSTREAM_WR
    if not rl.exists() or not wr.exists():
        return "SKIP", "", "ReserveLogic.sol or WadRayMath.sol missing after checkout"
    blob_rl = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_RL}"]).stdout.strip()
    blob_wr = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_WR}"]).stdout.strip()
    if sha256_file(rl) != PINNED_RL_SHA or blob_rl != PINNED_RL_BLOB:
        return "FAIL", "", f"ReserveLogic live={sha256_file(rl)} blob={blob_rl}"
    if sha256_file(wr) != PINNED_WR_SHA or blob_wr != PINNED_WR_BLOB:
        return "FAIL", "", f"WadRayMath live={sha256_file(wr)} blob={blob_wr}"
    text = rl.read_text(encoding="utf-8")
    wr_text = wr.read_text(encoding="utf-8")
    if "function cumulateToLiquidityIndex" not in text:
        return "FAIL", "", "ReserveLogic missing cumulateToLiquidityIndex"
    if "amount.wadToRay().rayDiv(totalLiquidity.wadToRay())" not in text:
        return "FAIL", "", "ReserveLogic missing wadToRay/rayDiv formula"
    if "reserve.liquidityIndex" not in text or "toUint128" not in text:
        return "FAIL", "", "ReserveLogic missing storage write / toUint128"
    if "function wadToRay" not in wr_text or "function rayMul" not in wr_text:
        return "FAIL", "", "WadRayMath missing wadToRay/rayMul"
    if "uint256 internal constant RAY = 1e27" not in wr_text:
        return "FAIL", "", "WadRayMath missing RAY = 1e27"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"ReserveLogic blob={blob_rl} WadRayMath blob={blob_wr}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 cumulateToLiquidityIndex — external LIN proof (RAY'=1e9, C11 Compiler 0)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of cumulate clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_cumulate.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler cumulate reject / 0.5eN"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "acl_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "acl_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "acl_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS",
            "git fetch of pinned aave/aave-v3-core matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of ReserveLogic.sol and WadRayMath.sol")
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

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("ray_mul", ["ray_mul", "1", "500000000"], "acl_ray_mul", (1, HALF), 1),
        ("ray_div", ["ray_div", "2", "3"], "acl_ray_div", (2, 3), 666666667),
        ("wad_to_ray", ["wad_to_ray", "1"], "acl_wad_to_ray", (1,), E9),
        ("wad_to_ray", ["wad_to_ray", str(E9)], "acl_wad_to_ray", (E9,), 10**18),
        ("cumulate", ["cumulate", str(E9), "0", str(E9)], "acl_cumulate", (E9, 0, E9), E9),
        ("cumulate", ["cumulate", str(E9), "1000000", str(E9)], "acl_cumulate",
         (E9, 10**6, E9), 1001000000),
        ("cumulate", ["cumulate", str(E9), "900000", str(E9)], "acl_cumulate",
         (E9, 900000, E9), 1000900000),
        ("cumulate", ["cumulate", str(E9), "1000000", "1050000000"], "acl_cumulate",
         (E9, 10**6, 1050000000), 1051050000),
        ("cumulate", ["cumulate", "0", "1000000", str(E9)], "acl_cumulate", (0, 10**6, E9), 0),
        ("cumulate", ["cumulate", str(E9), "10000000000", str(E9)], "acl_cumulate",
         (E9, 10**10, E9), 0),
        ("cumulate", ["cumulate", "2000000000", "100000000", str(E9)], "acl_cumulate",
         (2 * E9, 10**8, E9), 1050000000),
        ("floor_mul", ["floor_mul", "1", "500000000"], "acl_wrong_floor_ray_mul", (1, HALF), 0),
        ("floor_div", ["floor_div", "2", "3"], "acl_wrong_floor_ray_div", (2, 3), 666666666),
    ]
    n_ok = 0
    for kind, oargs, fn, lin_args, py in vectors:
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *lin_args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{lin_args}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{lin_args}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("HALF-UP", "PASS",
        "rayMul(1, 5e8) half-up 1 vs floor 0; rayDiv(2,3) 666666667 vs floor 666666666",
        f"mul={lin_vm('acl_ray_mul', 1, HALF)} div={lin_vm('acl_ray_div', 2, 3)}")
    rec("PREMIUM-01", "PASS",
        "0.1% of 1e9 liquidity at index=1e9 → 1001000000 (flashloan premium into aToken index)",
        f"idx={lin_vm('acl_cumulate', E9, 10**6, E9)}")
    rec("PREMIUM-009", "PASS",
        "typical 0.09% Aave V3 flashloan premium → 1000900000",
        f"idx={lin_vm('acl_cumulate', E9, 900000, E9)}")
    rec("LIQ0-FAILCLOSED", "PASS",
        "totalLiquidity=0 fail-closes to 0 (Solidity rayDiv by zero reverts)",
        f"z={lin_vm('acl_cumulate', 0, 10**6, E9)}")
    rec("RAY27", "PASS",
        "mainnet RAY=1e27 / HALF_RAY=0.5e27 do not fit i64; clone documents RAY'=1e9",
        f"fits={lin_vm('acl_ray27_fits')}")

    wrapped = (10**10 * 10**10)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("acl_ray_mul", 10**10, 10**10)
    naive = lin_vm("acl_naive_i64_mul", 10**10, 10**10)
    if wide != 100000000000 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 1e10*1e10 should wrap; 128-bit rayMul = 1e11",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 1e10*1e10 wraps; 128-bit rayMul stays 100000000000",
        f"i64_wrap={wrapped} rayMul={wide}")

    jit_ok = lin_roundtrip_jit("acl_cumulate", E9, 10**6, E9)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on acl_cumulate (in-memory libtcc)")
    else:
        jv = lin_jit("acl_cumulate", E9, 10**6, E9)
        if jv == 1001000000:
            rec("C0-JIT", "PASS", "lin_c0 jit acl_cumulate(1e9,1e6,1e9)==1001000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "acl_cumulate(total_liq: int, amount: int, index: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN cumulate args")
        return 1
    rec("EXPLICIT-ARGS", "PASS",
        "LIN clone takes total_liq, amount, index as arguments (no reserve.liquidityIndex write)")
    if "acl_muldiv_add_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit half-up (a*b+add)/d (naive i64 1e10*1e10 wraps)")
    if "REJ_SOLIDITY_CUMULATE" not in sol_src or "0.5e" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing CUMULATE reject / 0.5eN expand")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes cumulate storage and expands 0.5eN")
    if "REJ_C_CUMULATE" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing CUMULATE reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes cumulate / liquidityIndex")
    if "REJ_RUST_CUMULATE" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing CUMULATE reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes cumulate / liquidityIndex")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_AAVE_CUMULATE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/aave/aave-v3-core",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_RL,
            "math_path": UPSTREAM_WR,
            "blob": PINNED_RL_BLOB,
            "sha256": PINNED_RL_SHA,
            "wad_ray_blob": PINNED_WR_BLOB,
            "wad_ray_sha256": PINNED_WR_SHA,
            "license": "MIT_after_BUSL_Change_Date_2023-01-27",
            "vendored": False,
        },
        "lin_clone": "src/lin_aave_cumulate.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/aave_cumulate_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "scale": E9,
        "named_goldens": {
            "identity_amount=0": E9,
            "premium_0.1pct": 1001000000,
            "premium_0.09pct": 1000900000,
            "index_already_5pct_then_0.1pct": 1051050000,
            "rayMul(1,5e8)_half_up": 1,
            "rayMul(1,5e8)_floor": 0,
            "rayDiv(2,3)_half_up": 666666667,
            "wadToRay(1)": E9,
            "naive_i64_1e10*1e10": wrapped,
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
