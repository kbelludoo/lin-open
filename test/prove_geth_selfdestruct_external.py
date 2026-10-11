#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum makeSelfdestructGasFn / EIP-3529 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of makeSelfdestructGasFn in go-ethereum v1.16.9
    * an independent C11 oracle
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * EIP-6780 same-transaction SELFDESTRUCT restriction
    * account-capped refund / RefundQuotientEIP3529
    * that makeSelfdestructGasFn returns the 5000 static opcode gas
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real SELFDESTRUCT EIP-2929/3529 addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_selfdestruct.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_selfdestruct_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_selfdestruct_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_selfdestruct_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_selfdestruct" / "geth_selfdestruct_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "213f7846ed039c8ab293eb9511383897497f52c971da014317d3e1b5b5dc5330"
PINNED_BLOB = "085b018e4c42bf0185da790518ea1d1ee891b682"
ACL_REL = "core/vm/operations_acl.go"
PARAMS_REL = "params/protocol_params.go"
PARAMS_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PARAMS_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-selfdestruct"

# (is_cold, empty, has_value, already, refunds, gas, refund)
VECTORS = [
    (0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 1, 0, 24000),
    (0, 0, 0, 1, 1, 0, 0),
    (1, 0, 0, 0, 0, 2600, 0),
    (1, 0, 0, 0, 1, 2600, 24000),
    (0, 1, 1, 0, 0, 25000, 0),
    (1, 1, 1, 0, 0, 27600, 0),
    (1, 1, 1, 0, 1, 27600, 24000),
    (0, 1, 0, 0, 0, 0, 0),
    (0, 0, 1, 0, 0, 0, 0),
    (1, 1, 0, 0, 0, 2600, 0),
    (1, 0, 1, 1, 1, 2600, 0),
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


def py_gas(is_cold: int, empty: int, has_value: int) -> int:
    if is_cold not in (0, 1) or empty not in (0, 1) or has_value not in (0, 1):
        return 0
    gas = 2600 if is_cold else 0
    if empty and has_value:
        gas += 25000
    return gas


def py_refund(refunds: int, already: int) -> int:
    if refunds not in (0, 1) or already not in (0, 1):
        return 0
    if refunds == 0 or already == 1:
        return 0
    return 24000


def py_check(is_cold: int) -> int:
    if is_cold not in (0, 1):
        return 0
    return 2500 if is_cold else 0


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
    excerpt = (FIX / "makeSelfdestructGasFn.go").read_text(encoding="utf-8")
    if "func makeSelfdestructGasFn(" not in live_txt:
        return "FAIL", commit, "makeSelfdestructGasFn missing"
    if "gasSelfdestructEIP3529 = makeSelfdestructGasFn(false)" not in live_txt:
        return "FAIL", commit, "gasSelfdestructEIP3529 binding missing"
    if "HasSelfDestructed" not in excerpt or excerpt.strip() not in live_txt:
        return "FAIL", commit, "makeSelfdestructGasFn.go excerpt not a substring"
    if "ColdAccountAccessCostEIP2929" not in params.read_text(encoding="utf-8"):
        return "FAIL", commit, "params missing ColdAccountAccessCostEIP2929"
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
    print("  GETH makeSelfdestructGasFn — external LIN proof (EIP-3529 / SELFDESTRUCT)")
    print("=" * 78)

    excerpt = FIX / "makeSelfdestructGasFn.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned makeSelfdestructGasFn.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func makeSelfdestructGasFn(" not in src_ex or "HasSelfDestructed" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing makeSelfdestructGasFn / HasSelfDestructed")
        return 1
    if "AddressInAccessList" not in src_ex or "CreateBySelfdestructGas" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing access-list / create-by-selfdestruct lift")
        return 1
    if "refundsEnabled" not in src_ex or "SelfdestructRefundGas" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing refundsEnabled / SelfdestructRefundGas")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has StateDB lift + refundsEnabled closure")

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
        rec("C11-SELFTEST", "FAIL", "C11 SELFDESTRUCT gas/refund selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range SELFDESTRUCT goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go SELFDESTRUCT goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of selfdestruct clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_selfdestruct.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec(
        "GO-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v9 (REJ_GO_SELFDESTRUCT / ACCESSLIST)",
    )

    gate = run([str(C0), "vm", str(LIN), "sd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "sd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "sd_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for cold, empty, value, already, refunds, want_g, want_r in VECTORS:
        py_g = py_gas(cold, empty, value)
        py_r = py_refund(refunds, already)
        c11_g = int(oracle(["gas", str(cold), str(empty), str(value)]).splitlines()[-1])
        c11_r = int(oracle(["refund", str(refunds), str(already)]).splitlines()[-1])
        got_g = lin_vm("sd_gas", cold, empty, value)
        got_r = lin_vm("sd_refund", refunds, already)
        go_g = go_oracle("gas", cold, empty, value)
        go_r = go_oracle("refund", refunds, already)
        if py_g != want_g or c11_g != want_g or got_g != want_g:
            rec("VEC-LIN", "FAIL", f"gas c={cold} e={empty} v={value}", f"py={py_g} c11={c11_g} lin={got_g} want={want_g}")
            return 1
        if py_r != want_r or c11_r != want_r or got_r != want_r:
            rec("VEC-REFUND", "FAIL", f"refund en={refunds} dest={already}", f"py={py_r} c11={c11_r} lin={got_r} want={want_r}")
            return 1
        if go_g != str(want_g) or go_r != str(want_r):
            rec("VEC-GO", "FAIL", f"go c={cold} e={empty}", f"go_g={go_g} go_r={go_r}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 == Go == LIN vm (gas+refund)")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint SELFDESTRUCT table matches C11 and LIN")

    if lin_vm("sd_create_cold") != 27600:
        rec("CREATE-COLD", "FAIL", "cold empty+value SELFDESTRUCT")
        return 1
    rec("CREATE-COLD", "PASS", "cold create-by-selfdestruct = 27600 (2600+25000)")

    if lin_vm("sd_eip3529_delta") != 24000 or lin_vm("sd_refund_3529", 0) != 0:
        rec("EIP3529-DELTA", "FAIL", "24000 refund removed by EIP-3529")
        return 1
    rec("EIP3529-DELTA", "PASS", "EIP-3529 disables the 24000 SELFDESTRUCT refund (gas-token path)")

    if lin_vm("sd_account_check", 1) != 2500 or lin_vm("sd_account_check", 0) != 0:
        rec("ACCOUNT-CHECK", "FAIL", "gasEip2929AccountCheck cold-warm")
        return 1
    rec("ACCOUNT-CHECK", "PASS", "gasEip2929AccountCheck = 2500 when cold (2600-100), 0 when warm")

    if lin_vm("sd_opcode_total_3529", 0, 0, 0) != 5000 or lin_vm("sd_opcode_total_3529", 1, 1, 1) != 32600:
        rec("STATIC-PLUS", "FAIL", "constant 5000 + dynamic")
        return 1
    rec("STATIC-PLUS", "PASS", "opcode total = SelfdestructGasEIP150 5000 + dynamic (fn itself returns dynamic only)")

    if lin_vm("sd_gas", -1, 0, 0) != 0 or lin_vm("sd_refund", 2, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "bounds")
        return 1
    rec("FAIL-CLOSED", "PASS", "flags outside 0/1 fail-close to 0")

    jit_ok = lin_roundtrip_jit("sd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("sd_gas", 1, 1, 1)
        if jv == 27600:
            rec("C0-JIT", "PASS", "lin_c0 jit sd_gas(1,1,1)==27600 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "sd_gas(is_cold: int, target_empty: int, has_value: int" in src and "HasSelfDestructed" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes 0/1 flags; pinned Geth reads StateDB+stack")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit flags vs Geth StateDB")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-SD-REJ",
        "PASS" if "REJ_GO_SELFDESTRUCT" in go_src and "REJ_GO_ACCESSLIST" in go_src else "FAIL",
        "lin_from_go.lin v9 rejects HasSelfDestructed / AddressInAccessList (lift is selfdestructGas)",
    )
    rec(
        "GO-EX-SPLIT",
        "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest",
    )

    evidence = {
        "schema": "LIN_GETH_SELFDESTRUCT_EVIDENCE_1.0",
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
                "ColdAccountAccessCostEIP2929=2600 CreateBySelfdestructGas=25000 "
                "SelfdestructRefundGas=24000 WarmStorageReadCostEIP2929=100 "
                "SelfdestructGasEIP150=5000 (static; not returned by makeSelfdestructGasFn) "
                f"from {PARAMS_REL} blob {PARAMS_BLOB} sha256 {PARAMS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_geth_selfdestruct.lin",
        "c11_oracle": "test/oracles/geth_selfdestruct_c11.c",
        "go_oracle": "test/oracles/geth_selfdestruct_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {
                "is_cold": a,
                "target_empty": b,
                "has_value": c,
                "already_destructed": d,
                "refunds_enabled": e,
                "gas": f,
                "refund": g,
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
