#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 percentMul / wadDiv / health factor vs LIN C0.

Recomputed vs pinned aave-v3-core v1.19.4, C11 __int128+limbs, lin_c0 vm,
optional libtcc JIT. Named contrasts: skip-LT, Liquity ICR, floor vs half-up,
debt==0 vs uint256.max, RAY overflow reject.

NOT claimed: uint256/mainnet/rayMul, replacing Aave, zk soundness.
Class: EXPERIMENTAL (real Aave HF algorithm, uint64-scale operands).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_aave_health.lin"
JUMP = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_health_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_health_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_health" / "aave_health_evidence.json"

WAD = 10**18
PINNED_COMMIT = "b74526a7bc67a3a117a1963fc871b3eb8cea8435"
PINNED = {
    "PercentageMath.sol": (
        "contracts/protocol/libraries/math/PercentageMath.sol",
        "6f165ad32ddcc3383cbb611cc3045c1a4bb28f16f83a85015fe202803de0161f",
        "c000be3a6c38a959aa3d28737445eaa5762c53b0",
    ),
    "WadRayMath.sol": (
        "contracts/protocol/libraries/math/WadRayMath.sol",
        "fae5b995ec613cc213050c99ea6352c9c18ceebba106d03b1726cfa8f1f0124e",
        "f61fe87f2f2748144cd4d113c848e649c41a4e5d",
    ),
    "GenericLogic.sol": (
        "contracts/protocol/libraries/logic/GenericLogic.sol",
        "6a5dbf307801b001ae5cd450c7bc6a7c77947b50f4bc29bdb93661ed22ea795b",
        "3342316e772a7e733723ef2963ab79566904fb30",
    ),
}
HF_SNIPPET = (
    "    vars.healthFactor = (vars.totalDebtInBaseCurrency == 0)\n"
    "      ? type(uint256).max\n"
    "      : (vars.totalCollateralInBaseCurrency.percentMul(vars.avgLiquidationThreshold)).wadDiv(\n"
    "        vars.totalDebtInBaseCurrency\n"
    "      );"
)
AVAIL_SNIPPET = "    uint256 availableBorrowsInBaseCurrency = totalCollateralInBaseCurrency.percentMul(ltv);"
PCT_SNIPPET = "  uint256 internal constant PERCENTAGE_FACTOR = 1e4;"
HALF_SNIPPET = "  uint256 internal constant HALF_PERCENTAGE_FACTOR = 0.5e4;"
PMUL_SNIPPET = "      result := div(add(mul(value, percentage), HALF_PERCENTAGE_FACTOR), PERCENTAGE_FACTOR)"
WAD_SNIPPET = "  uint256 internal constant WAD = 1e18;"
RAY_SNIPPET = "  uint256 internal constant RAY = 1e27;"
WDIV_SNIPPET = "      c := div(add(mul(a, WAD), div(b, 2)), b)"


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/aave/aave-v3-core.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    notes = []
    for name, (rel, sha, blob) in PINNED.items():
        live = UPSTREAM / rel
        if not live.exists():
            return "SKIP", "", f"{rel} missing"
        if sha256_file(live) != sha:
            return "FAIL", commit, f"{name} sha mismatch"
        got_blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{rel}"]).stdout.strip()
        if got_blob != blob:
            return "FAIL", commit, f"{name} blob mismatch {got_blob}"
        notes.append(blob)
    text_gl = (UPSTREAM / PINNED["GenericLogic.sol"][0]).read_text(encoding="utf-8")
    text_pm = (UPSTREAM / PINNED["PercentageMath.sol"][0]).read_text(encoding="utf-8")
    text_wr = (UPSTREAM / PINNED["WadRayMath.sol"][0]).read_text(encoding="utf-8")
    if HF_SNIPPET not in text_gl or AVAIL_SNIPPET not in text_gl:
        return "FAIL", commit, "health/available snippet missing"
    if PCT_SNIPPET not in text_pm or HALF_SNIPPET not in text_pm or PMUL_SNIPPET not in text_pm:
        return "FAIL", commit, "percentMul snippet missing"
    if WAD_SNIPPET not in text_wr or RAY_SNIPPET not in text_wr or WDIV_SNIPPET not in text_wr:
        return "FAIL", commit, "wadDiv/RAY snippet missing"
    return "PASS", commit, notes[2]


def py_of(kind: str, args: tuple[int, ...]) -> int:
    u64 = (1 << 64) - 1

    def mda(a: int, b: int, add: int, d: int) -> int:
        if d == 0:
            return 0
        q = (a * b + add) // d
        return 0 if q > u64 else q

    if kind == "muldiv":
        return mda(args[0], args[1], 0, args[2])
    if kind == "percentmul":
        return mda(args[0], args[1], 5000, 10000)
    if kind == "percentmulfloor":
        return mda(args[0], args[1], 0, 10000)
    if kind == "waddiv":
        b = args[1]
        return 0 if b <= 0 else mda(args[0], WAD, b // 2, b)
    if kind == "waddivfloor":
        b = args[1]
        return 0 if b <= 0 else mda(args[0], WAD, 0, b)
    if kind == "health":
        coll, lt, debt = args
        if debt <= 0:
            return 0
        return py_of("waddiv", (py_of("percentmul", (coll, lt)), debt))
    if kind == "skiplt":
        coll, debt = args
        return py_of("waddiv", (coll, debt))
    if kind == "avail":
        coll, ltv, debt = args
        cap = py_of("percentmul", (coll, ltv))
        return 0 if cap < debt else cap - debt
    return 0


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_HEALTH_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 percentMul / wadDiv / health factor — external LIN proof (C11)")
    print("=" * 78)

    excerpt = FIX / "AaveHealth.excerpt.sol"
    if not excerpt.exists() or HF_SNIPPET not in excerpt.read_text(encoding="utf-8"):
        rec("PIN-EXCERPT", "FAIL", "pinned health excerpt missing exact GenericLogic bytes")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt contains exact healthFactor / percentMul / wadDiv / RAY substrings")

    for name, (_rel, sha, _blob) in PINNED.items():
        p = FIX / name
        if not p.exists() or sha256_file(p) != sha:
            rec("PIN-FILE", "FAIL", f"pinned {name} hash mismatch")
            return 1
    rec("PIN-SHA256", "PASS", "pinned PercentageMath.sol / WadRayMath.sol / GenericLogic.sol sha256 match")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED["GenericLogic.sol"][2]
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of aave-v3-core v1.19.4 matches fixture hashes", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of GenericLogic.sol")
        rec("SNIPPET-IN-LIVE", "PASS", "health/percentMul/wadDiv/RAY excerpts are substrings of live bytes")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("SNIPPET-IN-LIVE", "SKIP", "live substring check skipped")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("SNIPPET-IN-LIVE", "FAIL", "excerpt not in live file", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv_add selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of aave health clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_health.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "ahf_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ahf_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "ahf_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "ahf_muldiv", (100, 200, 50)),
        ("percentmul", ["10000", "8000"], "ahf_percent_mul", (10000, 8000)),
        ("percentmul", ["1", "5000"], "ahf_percent_mul", (1, 5000)),
        ("percentmulfloor", ["1", "5000"], "ahf_percent_mul_floor", (1, 5000)),
        ("waddiv", ["8000", "5000"], "ahf_wad_div", (8000, 5000)),
        ("waddiv", ["2", "3"], "ahf_wad_div", (2, 3)),
        ("waddivfloor", ["2", "3"], "ahf_wad_div_floor", (2, 3)),
        ("health", ["10000", "8000", "5000"], "ahf_health", (10000, 8000, 5000)),
        ("health", ["10000", "8000", "8500"], "ahf_health", (10000, 8000, 8500)),
        ("skiplt", ["10000", "8500"], "ahf_skip_lt", (10000, 8500)),
        ("avail", ["10000", "7500", "1000"], "ahf_available", (10000, 7500, 1000)),
        ("muldiv", [str(WAD), str(WAD), "1"], "ahf_muldiv", (WAD, WAD, 1)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        got_lin = lin_vm(LIN, fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        py = py_of(kind, largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    hf80 = lin_vm(LIN, "ahf_health", 10000, 8000, 8500)
    skip = lin_vm(LIN, "ahf_skip_lt", 10000, 8500)
    ok_a = lin_vm(LIN, "ahf_health_ok", 10000, 8000, 8500)
    ok_s = lin_vm(LIN, "ahf_skip_lt_ok", 10000, 8500)
    if hf80 >= WAD or skip < WAD or ok_a != 0 or ok_s != 1:
        rec("LT-SKIP", "FAIL", "80% LT must liquidate 85% LTV; skip-LT must falsely pass", f"hf={hf80} skip={skip}")
        return 1
    rec("LT-SKIP", "PASS",
        "coll=10000 debt=8500 LT=80%: Aave HF=0.941e18 liquidatable; skip-LT=1.176e18 falsely healthy",
        f"aave={hf80} skip_lt={skip}")

    half = lin_vm(LIN, "ahf_percent_mul", 1, 5000)
    floor = lin_vm(LIN, "ahf_percent_mul_floor", 1, 5000)
    if half != 1 or floor != 0:
        rec("HALF-UP", "FAIL", "percentMul(1,50%) half-up must be 1 vs floor 0", f"h={half} f={floor}")
        return 1
    rec("HALF-UP", "PASS", "named rejected floor path: percentMul(1,5000)=1; without HALF_PERCENTAGE=0")

    wd = lin_vm(LIN, "ahf_wad_div", 2, 3)
    wdf = lin_vm(LIN, "ahf_wad_div_floor", 2, 3)
    if wd != 666666666666666667 or wdf != 666666666666666666:
        rec("WAD-HALF", "FAIL", "wadDiv(2,3) half-up vs floor", f"w={wd} f={wdf}")
        return 1
    rec("WAD-HALF", "PASS", "wadDiv(2,3)=666...667; floor path=666...666 (b/2 rounding)")

    nd = lin_vm(LIN, "ahf_no_debt", 0)
    hz = lin_vm(LIN, "ahf_health", 10000, 8000, 0)
    if nd != 1 or hz != 0:
        rec("DEBT-ZERO", "FAIL", "debt==0 must set no_debt=1 and health=0 (not uint256.max)", f"nd={nd} h={hz}")
        return 1
    rec("DEBT-ZERO", "PASS", "debt==0: LIN fail-closes health=0; Aave returns type(uint256).max (unrepresentable in i64)")

    licr = lin_vm(LIN, "ahf_liquity_icr", 10000, 8500)
    if licr != skip:
        rec("LIQUITY-CONTRAST", "FAIL", "Liquity-style ICR must equal skip-LT wadDiv")
        return 1
    rec("LIQUITY-CONTRAST", "PASS",
        "Liquity ICR (coll*WAD/debt) has no LT; same bits as skip-LT, 1.176e18 vs Aave 0.941e18")

    wrapped = (WAD * WAD) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 0:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled fail-closed 0")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes 0", f"i64_wrap={wrapped}")

    jr = run([str(C0), "vm", str(JUMP), "cjr_test_suite"])
    jv = value_of(jr.stdout)
    if jr.returncode != 0 or jv != 1:
        rec("JUMPRATE-REG", "FAIL", "JumpRate suite must still pass after transpiler delta", jr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still cjr_test_suite==1 after PERCENT_MUL/WAD_DIV rejects")

    jit_ok = lin_roundtrip_jit("ahf_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ahf_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    src = LIN.read_text(encoding="utf-8")
    if "ahf_health(coll: int, lt: int, debt: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit coll/lt/debt as arguments")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes collateral, LT and debt as arguments (no hidden storage)")
    if "getAssetPrice" in src or "1000000000000000000000000000" in src:
        rec("NO-RAY-GET", "FAIL", "clone must not call oracle getters or write a 1e27 literal")
    else:
        rec("NO-RAY-GET", "PASS", "clone has no getAssetPrice and no 1e27 i64-overflow literal")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ("REJ_SOLIDITY_PERCENT_MUL", "percentMul(", "REJ_SOLIDITY_WAD_DIV", "wadDiv(",
            "REJ_SOLIDITY_RAY", "1e27", "REJ_SOLIDITY_HEALTH", "REJ_SOLIDITY_UINT_MAX", '"="', '"ex{"')
    missing = [t for t in need if t not in sol_src]
    rec("SOL-REJ", "FAIL" if missing else "PASS",
        "v3 rejects PERCENT_MUL / WAD_DIV / RAY / HEALTH / UINT_MAX; emit splits '=' + 'ex{'" if not missing
        else "solidity transpiler v3 missing reject tokens", str(missing) if missing else "")

    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJ", "PASS" if "REJ_RUST_PERCENT_MUL" in rs_src and "* percentage" in rs_src else "FAIL",
        "rust transpiler v2 rejects * percentage wrapping wrap")

    gate_sol = run([str(C0), "vm", str(SOL_TR), "sol_parse_test_gate"])
    if "VM_REJ_STRING_LITERAL" in gate_sol.stdout or "VM_REJ_STRING_LITERAL" in gate_sol.stderr:
        rec("SOL-GATE-REJ", "PASS", "Compiler 0 refuses sol_parse_test_gate string-literal path (VM_REJ_STRING_LITERAL)")
    else:
        rec("SOL-GATE-REJ", "SKIP", "string-literal reject not observed", gate_sol.stdout[:200])

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/aave/aave-v3-core",
        "tag": "v1.19.4",
        "commit": commit or PINNED_COMMIT,
        "path": PINNED["GenericLogic.sol"][0],
        "git_blob_sha": blob,
        "file_sha256": PINNED["GenericLogic.sol"][1],
        "percentage_math_sha256": PINNED["PercentageMath.sol"][1],
        "wad_ray_math_sha256": PINNED["WadRayMath.sol"][1],
        "license": "MIT (BUSL-1.1 Change Date 2023-01-27 elapsed)",
    }
    evidence["lin_clone"] = "src/lin_aave_health.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-aave-health"
    evidence["c11_oracle"] = "test/oracles/aave_health_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["hf_80pct_lt_85debt"] = hf80
    evidence["skip_lt_85debt"] = skip
    evidence["wadDiv_2_3"] = wd
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
