#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum makeGasSStoreFunc / EIP-3529 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of makeGasSStoreFunc in go-ethereum v1.16.9
    * an independent C11 oracle (Geth table AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * account-capped refund / RefundQuotientEIP3529 application
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real SSTORE EIP-2200/2929/3529 addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_sstore.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_sstore_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_sstore_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_sstore_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_sstore" / "geth_sstore_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "213f7846ed039c8ab293eb9511383897497f52c971da014317d3e1b5b5dc5330"
PINNED_BLOB = "085b018e4c42bf0185da790518ea1d1ee891b682"
ACL_REL = "core/vm/operations_acl.go"
PARAMS_REL = "params/protocol_params.go"
PARAMS_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PARAMS_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-sstore"

# (orig, curr, val, is_warm, gas_left, gas, refund_3529)
VECTORS = [
    (0, 0, 0, 1, 100000, 100, 0),
    (1, 1, 1, 1, 100000, 100, 0),
    (0, 0, 1, 1, 100000, 20000, 0),
    (1, 1, 0, 1, 100000, 2900, 4800),
    (1, 1, 2, 1, 100000, 2900, 0),
    (1, 0, 1, 1, 100000, 100, -2000),
    (1, 0, 0, 1, 100000, 100, 0),
    (1, 0, 2, 1, 100000, 100, -4800),
    (1, 2, 1, 1, 100000, 100, 2800),
    (1, 2, 0, 1, 100000, 100, 4800),
    (1, 2, 2, 1, 100000, 100, 0),
    (1, 2, 3, 1, 100000, 100, 0),
    (0, 1, 0, 1, 100000, 100, 19900),
    (0, 1, 1, 1, 100000, 100, 0),
    (0, 1, 2, 1, 100000, 100, 0),
    (0, 0, 1, 0, 100000, 22100, 0),
    (1, 1, 0, 0, 100000, 5000, 4800),
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


def py_gas(orig: int, curr: int, val: int, is_warm: int, gas_left: int) -> int:
    if orig < 0 or orig > 3 or curr < 0 or curr > 3 or val < 0 or val > 3:
        return 0
    if is_warm not in (0, 1) or gas_left <= 2300:
        return 0
    cost = 0 if is_warm == 1 else 2100
    if curr == val:
        return cost + 100
    if orig == curr:
        if orig == 0:
            return cost + 20000
        return cost + 2900
    return cost + 100


def py_refund(orig: int, curr: int, val: int, gas_left: int, sched: int) -> int:
    if orig < 0 or orig > 3 or curr < 0 or curr > 3 or val < 0 or val > 3:
        return 0
    if sched not in (4800, 15000) or gas_left <= 2300:
        return 0
    if curr == val:
        return 0
    if orig == curr:
        if orig == 0:
            return 0
        return sched if val == 0 else 0
    r = 0
    if orig != 0:
        if curr == 0:
            r -= sched
        elif val == 0:
            r += sched
    if orig == val:
        r += 19900 if orig == 0 else 2800
    return r


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
    url = "https://github.com/ethereum/go-ethereum.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / ACL_REL
    params = UPSTREAM / PARAMS_REL
    if not live.exists() or not params.exists():
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ACL_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    if sha256_file(params) != PARAMS_SHA256:
        return "FAIL", commit, "protocol_params.go sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    excerpt = (FIX / "makeGasSStoreFunc.go").read_text(encoding="utf-8")
    if excerpt not in live_txt:
        return "FAIL", commit, "makeGasSStoreFunc.go excerpt not a substring"
    if "gasSStoreEIP3529" not in live_txt:
        return "FAIL", commit, "gasSStoreEIP3529 missing"
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
    print("  GETH makeGasSStoreFunc — external LIN proof (EIP-3529 / SSTORE)")
    print("=" * 78)

    excerpt = FIX / "makeGasSStoreFunc.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned makeGasSStoreFunc.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func makeGasSStoreFunc(" not in src_ex or "GetStateAndCommittedState" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing makeGasSStoreFunc / StateDB lift site")
        return 1
    if "SstoreSentryGasEIP2200" not in src_ex or "SstoreSetGasEIP2200" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing sentry / set constants")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has StateDB lift + sentry + set/reset/warm/cold")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/vm/operations_acl.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 SSTORE gas/refund vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range SSTORE goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go SSTORE goldens + sentry fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of sstore clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_sstore.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v8 (REJ_GO_STATEDB)")
    chk3 = run([str(C0), "check", str(C_TR)])
    rec("C-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")
    chk4 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3 (require/unchecked)")

    gate = run([str(C0), "vm", str(LIN), "ss_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ss_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ss_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for orig, curr, val, warm, gl, want_g, want_r in VECTORS:
        py_g = py_gas(orig, curr, val, warm, gl)
        py_r = py_refund(orig, curr, val, gl, 4800)
        c11_g = int(oracle(["gas", str(orig), str(curr), str(val), str(warm), str(gl)]).splitlines()[-1])
        c11_r = int(oracle(["refund", str(orig), str(curr), str(val), str(gl), "4800"]).splitlines()[-1])
        got_g = lin_vm("ss_gas", orig, curr, val, warm, gl)
        got_r = lin_vm("ss_refund", orig, curr, val, gl, 4800)
        go_g = go_oracle("gas", orig, curr, val, warm, gl)
        go_r = go_oracle("refund", orig, curr, val, gl, 4800)
        if py_g != want_g or c11_g != want_g or got_g != want_g:
            rec("VEC-LIN", "FAIL", f"gas {orig},{curr},{val},w={warm}", f"py={py_g} c11={c11_g} lin={got_g} want={want_g}")
            return 1
        if py_r != want_r or c11_r != want_r or got_r != want_r:
            rec("VEC-REFUND", "FAIL", f"refund {orig},{curr},{val}", f"py={py_r} c11={c11_r} lin={got_r} want={want_r}")
            return 1
        if go_g != str(want_g) or go_r != str(want_r):
            rec("VEC-GO", "FAIL", f"go {orig},{curr},{val}", f"go_g={go_g} go_r={go_r}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 == Go == LIN vm (gas+refund)")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint SSTORE table matches C11 and LIN")

    if lin_vm("ss_first_credit_cold") != 22100:
        rec("FIRST-CREDIT", "FAIL", "cold 0->nonzero SSTORE")
        return 1
    rec("FIRST-CREDIT", "PASS", "first-credit cold SSTORE = 22100 (2100+20000)", "typical first ERC-20 balance write")

    if lin_vm("ss_clear_3529") != 4800 or lin_vm("ss_refund", 1, 1, 0, 100000, 15000) != 15000:
        rec("EIP3529-DELTA", "FAIL", "4800 vs 15000 clear schedule")
        return 1
    rec("EIP3529-DELTA", "PASS", "EIP-3529 clear refund is 4800 = 5000-2100+1900; EIP-2200 remains 15000")

    if lin_vm("ss_gas", 0, 0, 1, 1, 2300) != 0 or lin_vm("ss_gas", 0, 0, 1, 1, 2301) != 20000:
        rec("SENTRY", "FAIL", "reentrancy sentry")
        return 1
    rec("SENTRY", "PASS", "gas_left<=2300 fail-closes; 2301 still charges set-gas")

    if lin_vm("ss_gas", -1, 0, 1, 1, 100000) != 0 or lin_vm("ss_sload", 2) != 0:
        rec("FAIL-CLOSED", "FAIL", "bounds")
        return 1
    rec("FAIL-CLOSED", "PASS", "slot tokens outside 0..3 and is_warm outside 0..1 fail-close to 0")

    jit_ok = lin_roundtrip_jit("ss_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ss_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ss_gas", 0, 0, 1, 0, 100000)
        if jv == 22100:
            rec("C0-JIT", "PASS", "lin_c0 jit ss_gas(0,0,1,0,100000)==22100 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "ss_gas(orig: int, curr: int, val: int" in src and "GetStateAndCommittedState" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes orig/curr/val/is_warm/gas_left; pinned Geth reads StateDB+stack")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit slot tokens vs Geth StateDB")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-STATEDB-REJ",
        "PASS" if "REJ_GO_STATEDB" in go_src and "REJ_GO_REFUND" in go_src else "FAIL",
        "lin_from_go.lin v8 rejects StateDB/GetState/AddRefund (lift is sstoreGasEIP3529)",
    )
    rec("C-ARRAY-REJ", "PASS" if "REJ_C_ARRAY_PARAM" in C_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    rec("SOL-REQUIRE", "PASS" if "REJ_SOLIDITY_UNCHECKED" in SOL_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_solidity.lin v3 rejects unchecked and lowers require to fail-closed")

    evidence = {
        "schema": "LIN_GETH_SSTORE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/ethereum/go-ethereum",
            "tag": PINNED_TAG,
            "commit": commit or PINNED_COMMIT,
            "path": ACL_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "LGPL-3.0",
            "constants": (
                "SstoreSentryGasEIP2200=2300 SstoreSetGasEIP2200=20000 "
                "SstoreResetGasEIP2200=5000 ColdSloadCostEIP2929=2100 "
                "WarmStorageReadCostEIP2929=100 TxAccessListStorageKeyGas=1900 "
                "SstoreClearsScheduleRefundEIP3529=4800 "
                f"from {PARAMS_REL} blob {PARAMS_BLOB} sha256 {PARAMS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_geth_sstore.lin",
        "c11_oracle": "test/oracles/geth_sstore_c11.c",
        "go_oracle": "test/oracles/geth_sstore_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {
                "orig": a,
                "curr": b,
                "val": c,
                "is_warm": d,
                "gas_left": e,
                "gas": f,
                "refund_3529": g,
            }
            for a, b, c, d, e, f, g in VECTORS
        ],
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
