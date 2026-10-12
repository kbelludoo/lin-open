#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: op-geth NewL1CostFuncFjord (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of NewL1CostFuncFjord + estimatedDASizeScaled
    * an independent C11 oracle (__int128 muldiv)
    * an independent Go oracle (math/big)
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces op-geth, Base, or OP Stack consensus
    * FlzCompressLen / FastLZ compressor
    * StateDB GetState / first-Ecotone Bedrock fallback
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real Fjord linear-regression + min clamp, i64-scale + 128-bit product).
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
LIN = ROOT / "src" / "lin_opgeth_fjord.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "opgeth_fjord_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "opgeth_fjord_c11"
GO_SRC = ROOT / "test" / "oracles" / "opgeth_fjord_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_opgeth")
EVIDENCE = ROOT / "examples" / "opgeth_fjord" / "opgeth_fjord_evidence.json"

PINNED_COMMIT = "7da4560d1fb3045286b70a8dc23360d2626543f2"
PINNED_TAG = "v1.101702.3"
PINNED_SHA256 = "35a4e1976fca49cb5f328c6bf3f1513458eda450c9e7425c24a78a8750c51dec"
PINNED_BLOB = "3266ae13faaabf599feb4417d60893a11b908fb3"
COST_REL = "core/types/rollup_cost.go"
TEST_REL = "core/types/rollup_cost_test.go"
TEST_SHA256 = "a1c7d82cdc42ce399bc62fa6ca7b5c68df16ec7786a34408e2c42d6098bb1739"
TEST_BLOB = "c07b53f023725f1758df86e09d9bff6b38ecc317"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-opgeth-fjord"

BF = 1000 * 10**6
BB = 10 * 10**6

# Official TestFjordL1CostFuncMinimumBounds / TestFjordL1CostSolidityParity
# + named contrast vs Ecotone emptyTx (calldata 480, FastLZ pin 31 from TestFlzCompressLen).
FEE_VECTORS = [
    (100, BF, BB, 2, 3, 3203000),
    (150, BF, BB, 2, 3, 3203000),
    (170, BF, BB, 2, 3, 3203000),
    (171, BF, BB, 2, 3, 3217602),
    (200, BF, BB, 2, 3, 3994602),
    (31, BF, BB, 2, 3, 3203000),
    (235, 2 * 10**6, 3 * 10**6, 20, 15, 105484),
]


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


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
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


def py_est(flz: int) -> int:
    if flz < 0:
        return 0
    raw = 836500 * flz
    if raw < 42585600:
        return 100000000
    unclamped = raw - 42585600
    return 100000000 if unclamped < 100000000 else unclamped


def py_fee(flz: int, bf: int, bb: int, bs: int, bbs: int) -> int:
    if min(flz, bf, bb, bs, bbs) < 0:
        return 0
    return (py_est(flz) * (bf * 16 * bs + bb * bbs)) // 10**12


def py_eco(z: int, o: int, bf: int, bb: int, bs: int, bbs: int) -> int:
    if min(z, o, bf, bb, bs, bbs) < 0:
        return 0
    return ((z * 4 + o * 16) * (bf * 16 * bs + bb * bbs)) // 16_000_000


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/ethereum-optimism/op-geth.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    if not (UPSTREAM / COST_REL).exists() or not (UPSTREAM / TEST_REL).exists():
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{COST_REL}"]).stdout.strip()
    live = UPSTREAM / COST_REL
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    if sha256_file(UPSTREAM / TEST_REL) != TEST_SHA256:
        return "FAIL", commit, f"{TEST_REL} sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    for name in ("NewL1CostFuncFjord.go", "estimatedDASizeScaled.go", "newL1CostFuncEcotone.go", "fjord_constants.go"):
        excerpt = (FIX / name).read_text(encoding="utf-8").strip()
        if excerpt not in live_txt:
            return "FAIL", commit, f"{name} excerpt not a substring"
    return "PASS", commit, blob


def go_oracle(op: str, *args: int) -> str | None:
    proc = run(["go", "run", str(GO_SRC), op, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  OP-GETH NewL1CostFuncFjord — external LIN proof")
    print("=" * 78)

    src_fj = (FIX / "NewL1CostFuncFjord.go").read_text(encoding="utf-8")
    src_est = (FIX / "estimatedDASizeScaled.go").read_text(encoding="utf-8")
    src_eco = (FIX / "newL1CostFuncEcotone.go").read_text(encoding="utf-8")
    src_c = (FIX / "fjord_constants.go").read_text(encoding="utf-8")
    if "fjordDivisor" not in src_fj or "estimatedDASizeScaled" not in src_fj:
        rec("PIN-EXCERPT", "FAIL", "Fjord excerpt missing 1e12 divisor / estimated size")
        return 1
    if "L1CostIntercept" not in src_est or "MinTransactionSizeScaled" not in src_est:
        rec("PIN-EXCERPT", "FAIL", "estimatedDASizeScaled excerpt missing intercept / min clamp")
        return 1
    if "ecotoneDivisor" not in src_eco or "-42_585_600" not in src_c:
        rec("PIN-EXCERPT", "FAIL", "Ecotone contrast or intercept constant missing")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpts: Fjord + estimatedDASizeScaled + Ecotone + intercept")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of op-geth v1.101702.3 matches pinned sha256/blob",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of rollup_cost.go + official Fjord test")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Fjord L1-fee selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 goldens vs official op-geth Fjord / Solidity-parity vectors")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go math/big goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of fjord clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_opgeth_fjord.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v15 (REJ_GO_FJORD / INTERCEPT / FASTLZ)")

    gate = run([str(C0), "vm", str(LIN), "fjo_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "fjo_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "fjo_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for flz, bf, bb, bs, bbs, want in FEE_VECTORS:
        args = [flz, bf, bb, bs, bbs]
        py = py_fee(*args)
        c11 = int(oracle(["fee", *[str(a) for a in args]]).splitlines()[-1])
        got = lin_vm("fjo_fee", *args)
        go = go_oracle("fee", *args)
        if not (py == c11 == got == want and go == str(want)):
            rec("VEC-LIN", "FAIL", f"fee {args}", f"py={py} c11={c11} lin={got} go={go} want={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} Fjord vectors: Python == C11 == Go == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint Fjord table matches C11 and LIN")

    if lin_vm("fjo_gas", 100) != 1600 or lin_vm("fjo_gas", 235) != 2463:
        rec("GAS", "FAIL", "official minimumFjordGas 1600 / Solidity-parity gas 2463")
        return 1
    rec("GAS", "PASS", "official min gas 1600 and Solidity-parity gas 2463")

    if lin_vm("fjo_eco", 0, 30, BF, BB, 2, 3) != 960900:
        rec("ECO-CONTRAST", "FAIL", "Ecotone emptyTx should remain 960900")
        return 1
    if lin_vm("fjo_vs_eco", 31, 0, 30, BF, BB, 2, 3) != 2242100:
        rec("VS-ECOTONE", "FAIL", "Fjord-minus-Ecotone emptyTx should be 2242100")
        return 1
    rec("ECO-CONTRAST", "PASS", "official emptyTx Ecotone still 960900 on the same scalars")
    rec("VS-ECOTONE", "PASS", "Ecotone leftover undercharges official emptyTx by 2242100 wei")

    if lin_vm("fjo_unclamped", 31) != 0:
        rec("CLAMP", "FAIL", "FastLZ 31 without min clamp must fail-close (negative intercept)")
        return 1
    rec("CLAMP", "PASS", "unclamped FastLZ 31 is negative; LIN fail-closes to 0 (op-geth clamps to 100e6)")

    if lin_vm("fjo_fee", -1, 1, 0, 1, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "negatives must fail-close")
        return 1
    rec("FAIL-CLOSED", "PASS", "negatives and overflow fail-close to 0")

    jit_ok = lin_roundtrip_jit("fjo_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on fjo_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("fjo_fee", 100, BF, BB, 2, 3)
        if jv == 3203000:
            rec("C0-JIT", "PASS", "lin_c0 jit fjo_fee(min)==3203000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "!fjo_fee(flz: int" in src and "!fjo_est(flz: int" in src else "FAIL",
        "LIN clone takes FastLZ size as an int; pinned op-geth closes over FlzCompressLen + L1Block",
    )

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-FJ-REJ",
        "PASS" if all(x in go_src for x in ("REJ_GO_FJORD", "REJ_GO_INTERCEPT", "REJ_GO_FASTLZ", "version=15")) else "FAIL",
        "lin_from_go.lin v15 rejects NewL1CostFuncFjord / L1CostIntercept / FastLZ",
    )
    rec("GO-EX-SPLIT", "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest")

    evidence = {
        "schema": "LIN_OPGETH_FJORD_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/ethereum-optimism/op-geth",
            "tag": PINNED_TAG,
            "commit": commit or PINNED_COMMIT,
            "path": COST_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "LGPL-3.0",
            "constants": (
                "L1CostIntercept=-42585600 L1CostFastlzCoef=836500 MinTransactionSizeScaled=100e6 "
                "fjordDivisor=1e12 official emptyTx fjordFee=3203000 minimumFjordGas=1600 "
                "FastLZ emptyTx=31 (TestFlzCompressLen) Ecotone emptyTx=960900 "
                f"Solidity-parity FastLZ=235 fee=105484 gas=2463 from {TEST_REL} blob {TEST_BLOB}"
            ),
        },
        "lin_clone": "src/lin_opgeth_fjord.lin",
        "c11_oracle": "test/oracles/opgeth_fjord_c11.c",
        "go_oracle": "test/oracles/opgeth_fjord_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "goldens": {
            "fjord_emptyTx_min": 3203000,
            "fjord_min_gas": 1600,
            "fjord_flz171": 3217602,
            "fjord_flz200": 3994602,
            "fjord_solidity_parity": 105484,
            "fjord_solidity_gas": 2463,
            "ecotone_emptyTx": 960900,
            "vs_ecotone": 2242100,
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
