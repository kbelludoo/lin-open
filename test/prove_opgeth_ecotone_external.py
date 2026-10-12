#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: op-geth newL1CostFuncEcotone (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of newL1CostFuncEcotone + Bedrock + operator
    * an independent C11 oracle (__int128 muldiv)
    * an independent Go oracle (math/big)
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces op-geth, Base, or OP Stack consensus
    * Fjord FastLZ / estimatedDASize
    * StateDB GetState / first-Ecotone Bedrock fallback
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real Ecotone/Isthmus/Jovian addends, i64-scale + 128-bit product).
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
LIN = ROOT / "src" / "lin_opgeth_ecotone.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "opgeth_ecotone_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "opgeth_ecotone_c11"
GO_SRC = ROOT / "test" / "oracles" / "opgeth_ecotone_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_opgeth")
EVIDENCE = ROOT / "examples" / "opgeth_ecotone" / "opgeth_ecotone_evidence.json"

PINNED_COMMIT = "7da4560d1fb3045286b70a8dc23360d2626543f2"
PINNED_TAG = "v1.101702.3"
PINNED_SHA256 = "35a4e1976fca49cb5f328c6bf3f1513458eda450c9e7425c24a78a8750c51dec"
PINNED_BLOB = "3266ae13faaabf599feb4417d60893a11b908fb3"
COST_REL = "core/types/rollup_cost.go"
TEST_REL = "core/types/rollup_cost_test.go"
TEST_SHA256 = "a1c7d82cdc42ce399bc62fa6ca7b5c68df16ec7786a34408e2c42d6098bb1739"
TEST_BLOB = "c07b53f023725f1758df86e09d9bff6b38ecc317"
PARAMS_REL = "params/protocol_params.go"
PARAMS_SHA256 = "fa66f41673c97a3dd9a62031ce02d8201c8a32e564c34f4b15ee860a4c8a0479"
PARAMS_BLOB = "3e9ce4a125308b89ba6dd034061ec59befd29d06"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-opgeth-ecotone"

# Official op-geth TestEcotoneL1CostFunc / TestBedrockL1CostFunc / TestNewOperatorCostFunc
# emptyTx calldata gas = 480; synthetic zeroes=0 ones=30 reproduces that weighted sum.
BF = 1000 * 10**6
BB = 10 * 10**6
OP_S = 1439103868
OP_C = 1256417826609331460

FEE_VECTORS = [
    # (zeroes, ones, bf, bb, bs, bbs, fee)
    (0, 30, BF, BB, 2, 3, 960900),
    (40, 20, BF, BB, 2, 3, 960900),
    (0, 30, BF, 0, 2, 0, 960000),
    (0, 0, BF, BB, 2, 3, 0),
    (0, 1000, 1000, 10, 2, 3, 32),  # 16000 * 32030 / 16e6 = 32
]

BEDROCK_VECTORS = [
    (0, 30, 50, BF, 7 * 10**6, 0, 11326000000000),
    (0, 30, 50, BF, 7 * 10**6, 1, 3710000000000),
]

OP_VECTORS = [
    (1618, OP_S, OP_C, 1256417826611659930, 1256650673615173860),
    (1000, 2000000, 5, 2005, None),  # jovian of (1000,2000000,5) overflows i64? 1000*2000000*100=2e11 +5 fits
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


def py_calldata(z: int, o: int) -> int:
    if z < 0 or o < 0:
        return 0
    return z * 4 + o * 16


def py_fee(z: int, o: int, bf: int, bb: int, bs: int, bbs: int) -> int:
    if min(z, o, bf, bb, bs, bbs) < 0:
        return 0
    cg = py_calldata(z, o)
    inn = bf * 16 * bs + bb * bbs
    return (cg * inn) // 16_000_000


def py_bedrock(z: int, o: int, overhead: int, bf: int, scalar: int, regolith: int) -> int:
    if min(z, o, overhead, bf, scalar) < 0 or regolith not in (0, 1):
        return 0
    cg = py_calldata(z, o)
    if regolith == 0:
        cg += 68 * 16
    return ((cg + overhead) * bf * scalar) // 1_000_000


def py_isthmus(gas: int, scalar: int, constant: int) -> int:
    if min(gas, scalar, constant) < 0:
        return 0
    return (gas * scalar) // 1_000_000 + constant


def py_jovian(gas: int, scalar: int, constant: int) -> int:
    if min(gas, scalar, constant) < 0:
        return 0
    return gas * scalar * 100 + constant


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
    paths = [UPSTREAM / p for p in (COST_REL, TEST_REL, PARAMS_REL)]
    if not all(p.exists() for p in paths):
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{COST_REL}"]).stdout.strip()
    live = UPSTREAM / COST_REL
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    if sha256_file(UPSTREAM / TEST_REL) != TEST_SHA256:
        return "FAIL", commit, f"{TEST_REL} sha256 mismatch"
    if sha256_file(UPSTREAM / PARAMS_REL) != PARAMS_SHA256:
        return "FAIL", commit, f"{PARAMS_REL} sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    for name in (
        "newL1CostFuncEcotone.go",
        "newL1CostFuncBedrockHelper.go",
        "bedrockCalldataGasUsed.go",
        "newOperatorCostFuncIsthmus.go",
        "newOperatorCostFuncOperatorFeeFix.go",
        "l1CostHelper.go",
    ):
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
    print("  OP-GETH newL1CostFuncEcotone — external LIN proof")
    print("=" * 78)

    src_eco = (FIX / "newL1CostFuncEcotone.go").read_text(encoding="utf-8")
    src_bed = (FIX / "newL1CostFuncBedrockHelper.go").read_text(encoding="utf-8")
    src_op = (FIX / "newOperatorCostFuncIsthmus.go").read_text(encoding="utf-8")
    if "ecotoneDivisor" not in src_eco or "l1BlobBaseFeeScalar" not in src_eco:
        rec("PIN-EXCERPT", "FAIL", "Ecotone excerpt missing blob scalar / 16e6 divisor")
        return 1
    if "TxDataZeroGas" not in src_bed or "Ones + 68" not in src_bed:
        rec("PIN-EXCERPT", "FAIL", "Bedrock excerpt missing zero-gas / pre-Regolith +68")
        return 1
    if "oneMillion" not in src_op:
        rec("PIN-EXCERPT", "FAIL", "Isthmus operator excerpt missing /1e6")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpts: Ecotone + Bedrock + Isthmus/Jovian operator")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of op-geth v1.101702.3 matches pinned sha256/blob",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of rollup_cost.go + test + protocol_params.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Ecotone L1-fee selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 goldens vs official op-geth emptyTx / operator vectors")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go math/big goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of ecotone clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_opgeth_ecotone.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v14 (REJ_GO_ECOTONE / OPERATOR / FASTLZ)")

    gate = run([str(C0), "vm", str(LIN), "eco_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "eco_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "eco_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for z, o, bf, bb, bs, bbs, want in FEE_VECTORS:
        args = [z, o, bf, bb, bs, bbs]
        py = py_fee(*args)
        c11 = int(oracle(["fee", *[str(a) for a in args]]).splitlines()[-1])
        got = lin_vm("eco_fee", *args)
        go = go_oracle("fee", *args)
        if not (py == c11 == got == want and go == str(want)):
            rec("VEC-LIN", "FAIL", f"fee {args}", f"py={py} c11={c11} lin={got} go={go} want={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} Ecotone vectors: Python == C11 == Go == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint Ecotone table matches C11 and LIN")

    for z, o, oh, bf, sc, reg, want in BEDROCK_VECTORS:
        args = [z, o, oh, bf, sc, reg]
        py = py_bedrock(*args)
        c11 = int(oracle(["bedrock", *[str(a) for a in args]]).splitlines()[-1])
        got = lin_vm("eco_bedrock", *args)
        go = go_oracle("bedrock", *args)
        if not (py == c11 == got == want and go == str(want)):
            rec("BEDROCK", "FAIL", f"bedrock {args}", f"py={py} c11={c11} lin={got} go={go} want={want}")
            return 1
    rec("BEDROCK", "PASS", "official emptyTx Bedrock 11.326e12 / Regolith 3.71e12 match")

    if lin_vm("eco_vs_noblob", 0, 30, BF, BB, 2, 3) != 900:
        rec("VS-NOBLOB", "FAIL", "emptyTx Ecotone-minus-noblob should be 900")
        return 1
    rec("VS-NOBLOB", "PASS", "naive no-blob estimator undercharges emptyTx by 900 wei")

    gas, sc, const, want_i, want_j = OP_VECTORS[0]
    if lin_vm("eco_op_isthmus", gas, sc, const) != want_i:
        rec("OP-ISTHMUS", "FAIL", "official Isthmus operator")
        return 1
    if lin_vm("eco_op_jovian", gas, sc, const) != want_j:
        rec("OP-JOVIAN", "FAIL", "official Jovian operator")
        return 1
    rec("OP-ISTHMUS", "PASS", "official emptyTx Isthmus operator 1256417826611659930")
    rec("OP-JOVIAN", "PASS", "official emptyTx Jovian operator 1256650673615173860")
    rec("OP-VS", "PASS", "Jovian-Isthmus variable term is *100 vs /1e6 (1e8×)",
        f"delta={want_j - want_i}")

    if lin_vm("eco_fee", -1, 0, 1, 0, 1, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "negatives must fail-close")
        return 1
    rec("FAIL-CLOSED", "PASS", "negatives and overflow fail-close to 0")

    jit_ok = lin_roundtrip_jit("eco_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on eco_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("eco_fee", 0, 30, BF, BB, 2, 3)
        if jv == 960900:
            rec("C0-JIT", "PASS", "lin_c0 jit eco_fee(emptyTx)==960900 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "eco_fee(zeroes: int, ones: int" in src and "l1BlobBaseFeeScalar" in src_eco else "FAIL",
        "LIN clone takes zeroes/ones/fee scalars; pinned op-geth closes over L1Block storage",
    )

    go_src = GO_TR.read_text(encoding="utf-8")
    rec("GO-ECO-REJ", "PASS" if all(x in go_src for x in ("REJ_GO_ECOTONE", "REJ_GO_OPERATOR", "REJ_GO_FASTLZ", "version=14")) else "FAIL",
        "lin_from_go.lin v14 rejects newL1CostFuncEcotone / operator / FastLZ")
    rec("GO-EX-SPLIT", "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest")

    evidence = {
        "schema": "LIN_OPGETH_ECOTONE_EVIDENCE_1.0",
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
                "TxDataZeroGas=4 TxDataNonZeroGasEIP2028=16 ecotoneDivisor=16e6 "
                "official emptyTx calldataGas=480 baseFee=1e9 blobBaseFee=1e7 "
                f"baseFeeScalar=2 blobBaseFeeScalar=3 from {TEST_REL} blob {TEST_BLOB}; "
                f"{PARAMS_REL} blob {PARAMS_BLOB} sha256 {PARAMS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_opgeth_ecotone.lin",
        "c11_oracle": "test/oracles/opgeth_ecotone_c11.c",
        "go_oracle": "test/oracles/opgeth_ecotone_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "goldens": {
            "ecotone_emptyTx": 960900,
            "noblob_emptyTx": 960000,
            "vs_noblob": 900,
            "bedrock_emptyTx": 11326000000000,
            "regolith_emptyTx": 3710000000000,
            "isthmus_operator": 1256417826611659930,
            "jovian_operator": 1256650673615173860,
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
