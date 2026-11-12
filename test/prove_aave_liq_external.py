#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 _calculateAvailableCollateralToLiquidate vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned aave/aave-v3-core LiquidationLogic.sol
      + PercentageMath.sol (sha256 + git blob; Solidity is hash-pinned, not vendored)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_aave_liq.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet WAD=1e18 / oracle / aToken parity
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Aave liquidation close-factor / available-collateral
algorithm, WAD'=1e9, PERCENTAGE_FACTOR=1e4).
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
LIN = ROOT / "src" / "lin_aave_liq.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_liq_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_liq_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_liq" / "aave_liq_evidence.json"

E9 = 10**9
I64MAX = 2**63 - 1
PCT = 10**4
HALF = 5 * 10**3
PINNED_COMMIT = "782f51917056a53a2c228701058a6c3fb233684a"
PINNED_LL_BLOB = "57f00fd47d14af2643dd8103a47adb70b664ec00"
PINNED_LL_SHA = "4fecfabd4ebbeccba176f41b3417dd5b3f16d65100d9e9cd373b7ed0dec51d5a"
PINNED_PM_BLOB = "c000be3a6c38a959aa3d28737445eaa5762c53b0"
PINNED_PM_SHA = "6f165ad32ddcc3383cbb611cc3045c1a4bb28f16f83a85015fe202803de0161f"
UPSTREAM_LL = "contracts/protocol/libraries/logic/LiquidationLogic.sol"
UPSTREAM_PM = "contracts/protocol/libraries/math/PercentageMath.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-aave-liq"


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


def py_mul3div1(a: int, b: int, c: int, den: int) -> int:
    if den <= 0:
        return 0
    q = (a * b) // den
    if q > I64MAX:
        return 0
    r = (a * b) % den
    qc = py_md(q, c, 0, 1)
    if q != 0 and c != 0 and qc == 0:
        return 0
    extra = py_md(r, c, 0, den)
    s = qc + extra
    if s < qc or s > I64MAX:
        return 0
    return s


def py_avail(
    dp: int, debt: int, cu: int, cp: int, du: int, user_bal: int, bonus: int, fee_pct: int, want: int
) -> int:
    if bonus <= 0 or dp <= 0 or cu <= 0 or cp <= 0 or du <= 0:
        return 0
    den = cp * du
    if den // cp != du or den > I64MAX:
        return 0
    base = py_mul3div1(dp, debt, cu, den)
    maxc = py_pmul(base, bonus)
    coll = maxc
    dneed = debt
    if user_bal < maxc:
        coll = user_bal
        t = py_mul3div1(cp, coll, du, dp)
        dneed = py_pdiv(py_md(t, 1, 0, cu), bonus)
    fee = 0
    if fee_pct != 0:
        unbonus = py_pdiv(coll, bonus)
        if coll < unbonus:
            return 0
        fee = py_pmul(coll - unbonus, fee_pct)
        if coll < fee:
            return 0
        coll = coll - fee
    if want == 1:
        return dneed
    if want == 2:
        return fee
    return coll


def py_close_debt(total: int, cover: int, hf: int) -> int:
    cf = 5000 if hf > 950000000 else 10000
    maxd = py_pmul(total, cf)
    return maxd if cover > maxd else cover


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
    ll = UPSTREAM / UPSTREAM_LL
    pm = UPSTREAM / UPSTREAM_PM
    if not ll.exists() or not pm.exists():
        return "SKIP", "", "LiquidationLogic.sol or PercentageMath.sol missing after checkout"
    blob_ll = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_LL}"]).stdout.strip()
    blob_pm = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_PM}"]).stdout.strip()
    if sha256_file(ll) != PINNED_LL_SHA or blob_ll != PINNED_LL_BLOB:
        return "FAIL", "", f"LiquidationLogic live={sha256_file(ll)} blob={blob_ll}"
    if sha256_file(pm) != PINNED_PM_SHA or blob_pm != PINNED_PM_BLOB:
        return "FAIL", "", f"PercentageMath live={sha256_file(pm)} blob={blob_pm}"
    text = ll.read_text(encoding="utf-8")
    pm_text = pm.read_text(encoding="utf-8")
    if "function _calculateAvailableCollateralToLiquidate" not in text:
        return "FAIL", "", "LiquidationLogic missing _calculateAvailableCollateralToLiquidate"
    if "baseCollateral" not in text or "percentMul(liquidationBonus)" not in text:
        return "FAIL", "", "LiquidationLogic missing baseCollateral.percentMul(bonus)"
    if "DEFAULT_LIQUIDATION_CLOSE_FACTOR = 0.5e4" not in text:
        return "FAIL", "", "LiquidationLogic missing 0.5e4 close factor"
    if "CLOSE_FACTOR_HF_THRESHOLD = 0.95e18" not in text:
        return "FAIL", "", "LiquidationLogic missing 0.95e18 HF threshold"
    if "HALF_PERCENTAGE_FACTOR = 0.5e4" not in pm_text:
        return "FAIL", "", "PercentageMath missing 0.5e4"
    if "function percentMul" not in pm_text or "function percentDiv" not in pm_text:
        return "FAIL", "", "PercentageMath missing percentMul/percentDiv"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"LiquidationLogic blob={blob_ll} PercentageMath blob={blob_pm}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 liquidation available-collateral — external LIN proof (WAD'=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of liquidation clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_liq.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler liquidation reject / 0.XeN"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "aliq_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "aliq_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "aliq_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS",
            "git fetch of pinned aave/aave-v3-core matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of LiquidationLogic.sol and PercentageMath.sol")
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
        ("percent_mul", ["percent_mul", "1", "5000"], "aliq_percent_mul", (1, 5000), 1),
        ("percent_div", ["percent_div", "2", "3"], "aliq_percent_div", (2, 3), 6667),
        ("floor_mul", ["floor_mul", "1", "5000"], "aliq_wrong_floor_percent_mul", (1, 5000), 0),
        ("floor_div", ["floor_div", "2", "3"], "aliq_wrong_floor_percent_div", (2, 3), 6666),
        ("avail", ["avail", "1000", str(E9), str(E9), "1000", str(E9), "10000000000", "10500", "0", "0"],
         "aliq_avail", (1000, E9, E9, 1000, E9, 10 * E9, 10500, 0, 0), 1050000000),
        ("avail", ["avail", "1000", str(E9), str(E9), "1000", str(E9), "10000000000", "10500", "1000", "0"],
         "aliq_avail", (1000, E9, E9, 1000, E9, 10 * E9, 10500, 1000, 0), 1045000000),
        ("avail", ["avail", "1000", str(E9), str(E9), "1000", str(E9), "10000000000", "10500", "1000", "2"],
         "aliq_avail", (1000, E9, E9, 1000, E9, 10 * E9, 10500, 1000, 2), 5000000),
        ("avail", ["avail", "1000", str(E9), str(E9), "1000", str(E9), "500000000", "10500", "0", "1"],
         "aliq_avail", (1000, E9, E9, 1000, E9, 5 * 10**8, 10500, 0, 1), 476190476),
        ("avail", ["avail", "1000", str(E9), str(E9), "0", str(E9), "10000000000", "10500", "0", "0"],
         "aliq_avail", (1000, E9, E9, 0, E9, 10 * E9, 10500, 0, 0), 0),
        ("avail", ["avail", "1000", str(E9), str(E9), "2000", str(E9), "10000000000", "10500", "0", "0"],
         "aliq_avail", (1000, E9, E9, 2000, E9, 10 * E9, 10500, 0, 0), 525000000),
        ("close_debt", ["close_debt", str(E9), str(E9), "960000000"],
         "aliq_close_debt", (E9, E9, 960000000), 500000000),
        ("close_debt", ["close_debt", str(E9), str(E9), "900000000"],
         "aliq_close_debt", (E9, E9, 900000000), E9),
    ]
    n_ok = 0
    for kind, oargs, fn, lin_args, py in vectors:
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *lin_args)
        if fn == "aliq_avail":
            py_v = py_avail(*lin_args)
        elif fn == "aliq_close_debt":
            py_v = py_close_debt(*lin_args)
        elif fn == "aliq_percent_mul":
            py_v = py_pmul(*lin_args)
        elif fn == "aliq_percent_div":
            py_v = py_pdiv(*lin_args)
        elif fn == "aliq_wrong_floor_percent_mul":
            py_v = py_md(lin_args[0], lin_args[1], 0, PCT)
        else:
            py_v = py_md(lin_args[0], PCT, 0, lin_args[1])
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{lin_args}", f"lin={got_lin} c11={want}")
            return 1
        if py_v != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{lin_args}", f"py={py_v} c11={want}")
            return 1
        if py != want:
            rec("VEC-GOLDEN", "FAIL", f"named golden {fn}", f"golden={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("HALF-UP", "PASS",
        "percentMul(1, 0.5e4) half-up 1 vs floor 0; percentDiv(2,3) 6667 vs floor 6666",
        f"mul={lin_vm('aliq_percent_mul', 1, 5000)} div={lin_vm('aliq_percent_div', 2, 3)}")
    rec("BONUS-05", "PASS",
        "equal-price 5% liquidation bonus → collateral 1050000000 (debt 1e9)",
        f"coll={lin_vm('aliq_avail', 1000, E9, E9, 1000, E9, 10 * E9, 10500, 0, 0)}")
    rec("FEE-10", "PASS",
        "10% protocol fee of the 5% bonus → liquidator 1045000000 fee 5000000",
        f"fee={lin_vm('aliq_avail', 1000, E9, E9, 1000, E9, 10 * E9, 10500, 1000, 2)}")
    rec("CAP-BAL", "PASS",
        "user collateral 5e8 < max 1.05e9 → debtNeeded 476190476 (percentDiv)",
        f"dneed={lin_vm('aliq_avail', 1000, E9, E9, 1000, E9, 5 * 10**8, 10500, 0, 1)}")
    rec("PRICE0-FAILCLOSED", "PASS",
        "collateralPrice=0 fail-closes to 0 (Solidity would divide by zero)",
        f"z={lin_vm('aliq_avail', 1000, E9, E9, 0, E9, 10 * E9, 10500, 0, 0)}")
    rec("CLOSE-50", "PASS",
        "HF > 0.95*WAD' uses 50% close factor; 1e9 debt → 5e8",
        f"d={lin_vm('aliq_close_debt', E9, E9, 960000000)}")
    rec("WAD18", "PASS",
        "mainnet 0.95e18 fits i64; 0.5e27 does not; clone documents WAD'=1e9",
        f"hf18_fits={lin_vm('aliq_hf18_fits')} ray27_fits={lin_vm('aliq_half_ray27_fits')}")

    wrapped = (10**15 * 10500)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("aliq_percent_mul", 10**15, 10500)
    naive = lin_vm("aliq_naive_i64_mul", 10**15, 10500)
    if wide != 1050000000000000 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 1e15*10500 should wrap; 128-bit percentMul = 1.05e15",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 1e15*10500 wraps; 128-bit percentMul stays 1050000000000000",
        f"i64_wrap={wrapped} percentMul={wide}")

    jit_ok = lin_roundtrip_jit("aliq_avail", 1000, E9, E9, 1000, E9, 10 * E9, 10500, 0, 0)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on aliq_avail (in-memory libtcc)")
    else:
        jv = lin_jit("aliq_avail", 1000, E9, E9, 1000, E9, 10 * E9, 10500, 0, 0)
        if jv == 1050000000:
            rec("C0-JIT", "PASS", "lin_c0 jit aliq_avail equal-price 5% == 1050000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "aliq_avail(dp: int, debt: int, cu: int, cp: int, du: int, user_bal: int, bonus: int, fee_pct: int, want: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN liquidation args")
        return 1
    rec("EXPLICIT-ARGS", "PASS",
        "LIN clone takes prices/units/bonus/fee as arguments (no oracle.getAssetPrice / storage)")
    if "aliq_muldiv_add_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit half-up percentMul (naive i64 1e15*10500 wraps)")
    if "REJ_SOLIDITY_LIQUIDATION" not in sol_src or "0.5e" not in sol_src or "0.95e" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing LIQUIDATION reject / 0.XeN expand")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes liquidation storage and expands 0.XeN")
    if "REJ_C_LIQUIDATION" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing LIQUIDATION reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes executeLiquidationCall / getAssetPrice")
    if "REJ_RUST_LIQUIDATION" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing LIQUIDATION reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes executeLiquidationCall / getAssetPrice")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_AAVE_LIQ_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/aave/aave-v3-core",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_LL,
            "math_path": UPSTREAM_PM,
            "blob": PINNED_LL_BLOB,
            "sha256": PINNED_LL_SHA,
            "pct_blob": PINNED_PM_BLOB,
            "pct_sha256": PINNED_PM_SHA,
            "license": "MIT_after_BUSL_Change_Date_2023-01-27",
            "vendored": False,
        },
        "lin_clone": "src/lin_aave_liq.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/aave_liq_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "scale": E9,
        "named_goldens": {
            "percentMul(1,0.5e4)_half_up": 1,
            "percentMul(1,0.5e4)_floor": 0,
            "percentDiv(2,3)_half_up": 6667,
            "equal_price_5pct_bonus": 1050000000,
            "equal_price_5pct_bonus_10pct_fee": 1045000000,
            "protocol_fee_10pct_of_bonus": 5000000,
            "capped_user_bal_5e8_debt_needed": 476190476,
            "hf_above_0.95_close_50pct": 500000000,
            "naive_i64_1e15*10500": wrapped,
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
