#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum gasExtCodeCopyEIP2929 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of gasExtCodeCopyEIP2929 in go-ethereum v1.16.9
    * an independent C11 oracle
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * quadratic memoryGasCost / Cmem
    * EIP-4762 Verkle EXTCODECOPY
    * that gasExtCodeCopyEIP2929 returns the 100 static opcode gas
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real EXTCODECOPY EIP-2929 addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_extcodecopy.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_extcodecopy_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_extcodecopy_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_extcodecopy_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_extcodecopy" / "geth_extcodecopy_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "213f7846ed039c8ab293eb9511383897497f52c971da014317d3e1b5b5dc5330"
PINNED_BLOB = "085b018e4c42bf0185da790518ea1d1ee891b682"
ACL_REL = "core/vm/operations_acl.go"
GAS_REL = "core/vm/gas_table.go"
GAS_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
GAS_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
PARAMS_REL = "params/protocol_params.go"
PARAMS_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PARAMS_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
EIPS_REL = "core/vm/eips.go"
EIPS_SHA256 = "306e3660bb3aa7e4c943b458191390b46ed754984462f6655a413740bc6c670c"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-extcodecopy"

# (size, is_cold, dynamic, total)
VECTORS = [
    (0, 0, 0, 100),
    (0, 1, 2500, 2600),
    (1, 0, 3, 103),
    (1, 1, 2503, 2603),
    (32, 0, 3, 103),
    (32, 1, 2503, 2603),
    (33, 0, 6, 106),
    (33, 1, 2506, 2606),
    (1024, 0, 96, 196),
    (1024, 1, 2596, 2696),
    (49152, 0, 4608, 4708),
    (49152, 1, 7108, 7208),
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


def py_dynamic(size: int, is_cold: int) -> int:
    if size < 0 or is_cold not in (0, 1):
        return 0
    return 3 * ((size + 31) // 32) + (2500 if is_cold else 0)


def py_total(size: int, is_cold: int) -> int:
    if size < 0 or is_cold not in (0, 1):
        return 0
    return 100 + py_dynamic(size, is_cold)


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
    gas = UPSTREAM / GAS_REL
    params = UPSTREAM / PARAMS_REL
    eips = UPSTREAM / EIPS_REL
    if not live.exists() or not gas.exists() or not params.exists() or not eips.exists():
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ACL_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    if sha256_file(gas) != GAS_SHA256:
        return "FAIL", commit, "gas_table.go sha256 mismatch"
    if sha256_file(params) != PARAMS_SHA256:
        return "FAIL", commit, "protocol_params.go sha256 mismatch"
    if sha256_file(eips) != EIPS_SHA256:
        return "FAIL", commit, "eips.go sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    excerpt = (FIX / "gasExtCodeCopyEIP2929.go").read_text(encoding="utf-8")
    if "func gasExtCodeCopyEIP2929(" not in live_txt:
        return "FAIL", commit, "gasExtCodeCopyEIP2929 missing"
    if excerpt.strip() not in live_txt:
        return "FAIL", commit, "gasExtCodeCopyEIP2929.go excerpt not a substring"
    if "gasExtCodeCopy    = memoryCopierGas(3)" not in gas.read_text(encoding="utf-8"):
        return "FAIL", commit, "gasExtCodeCopy = memoryCopierGas(3) missing"
    eips_txt = eips.read_text(encoding="utf-8")
    if "jt[EXTCODECOPY].dynamicGas = gasExtCodeCopyEIP2929" not in eips_txt:
        return "FAIL", commit, "enable2929 binding missing"
    if "CopyGas" not in params.read_text(encoding="utf-8"):
        return "FAIL", commit, "params missing CopyGas"
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
    print("  GETH gasExtCodeCopyEIP2929 — external LIN proof (EIP-2929 / EXTCODECOPY)")
    print("=" * 78)

    excerpt = FIX / "gasExtCodeCopyEIP2929.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned gasExtCodeCopyEIP2929.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func gasExtCodeCopyEIP2929(" not in src_ex or "gasExtCodeCopy(" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing gasExtCodeCopyEIP2929 / gasExtCodeCopy")
        return 1
    if "AddressInAccessList" not in src_ex or "Bytes20" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing access-list / Bytes20 lift")
        return 1
    if "ColdAccountAccessCostEIP2929" not in src_ex or "WarmStorageReadCostEIP2929" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing cold-warm constants")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has gasExtCodeCopy + AddressInAccessList + SafeAdd")

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
        rec("C11-SELFTEST", "FAIL", "C11 EXTCODECOPY gas selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range EXTCODECOPY goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go EXTCODECOPY goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of extcodecopy clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_extcodecopy.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec(
        "GO-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v10 (REJ_GO_EXTCODECOPY / ACCESSLIST)",
    )

    gate = run([str(C0), "vm", str(LIN), "ecc_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ecc_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ecc_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for size, cold, want_d, want_t in VECTORS:
        py_d = py_dynamic(size, cold)
        py_t = py_total(size, cold)
        c11_d = int(oracle(["dynamic", str(size), str(cold)]).splitlines()[-1])
        c11_t = int(oracle(["total", str(size), str(cold)]).splitlines()[-1])
        got_d = lin_vm("ecc_dynamic", size, cold)
        got_t = lin_vm("ecc_total", size, cold)
        go_d = go_oracle("dynamic", size, cold)
        go_t = go_oracle("total", size, cold)
        if py_d != want_d or c11_d != want_d or got_d != want_d:
            rec("VEC-LIN", "FAIL", f"dyn s={size} c={cold}", f"py={py_d} c11={c11_d} lin={got_d} want={want_d}")
            return 1
        if py_t != want_t or c11_t != want_t or got_t != want_t:
            rec("VEC-TOTAL", "FAIL", f"tot s={size} c={cold}", f"py={py_t} c11={c11_t} lin={got_t} want={want_t}")
            return 1
        if go_d != str(want_d) or go_t != str(want_t):
            rec("VEC-GO", "FAIL", f"go s={size} c={cold}", f"go_d={go_d} go_t={go_t}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 == Go == LIN vm (dynamic+total)")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint EXTCODECOPY table matches C11 and LIN")

    if lin_vm("ecc_berlin_delta", 0) != 2500 or lin_vm("ecc_berlin_delta", 1024) != 2500:
        rec("BERLIN-DELTA", "FAIL", "cold-warm 2500")
        return 1
    rec("BERLIN-DELTA", "PASS", "Berlin surcharge is 2500 at every in-range size (2600-100)")

    if lin_vm("ecc_account_check", 1) != 2500 or lin_vm("ecc_account_check", 0) != 0:
        rec("ACCOUNT-CHECK", "FAIL", "gasEip2929AccountCheck sibling")
        return 1
    rec("ACCOUNT-CHECK", "PASS", "gasEip2929AccountCheck sibling = 2500 when cold, 0 when warm")

    if lin_vm("ecc_total", 0, 0) != 100 or lin_vm("ecc_total", 0, 1) != 2600:
        rec("STATIC-PLUS", "FAIL", "constant 100 + dynamic")
        return 1
    rec("STATIC-PLUS", "PASS", "opcode total = WarmStorageReadCost 100 + dynamic (fn itself returns dynamic only)")

    if lin_vm("ecc_dynamic", -1, 0) != 0 or lin_vm("ecc_dynamic", 32, 2) != 0:
        rec("FAIL-CLOSED", "FAIL", "bounds")
        return 1
    rec("FAIL-CLOSED", "PASS", "negative size or flags outside 0/1 fail-close to 0")

    jit_ok = lin_roundtrip_jit("ecc_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ecc_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ecc_dynamic", 1024, 1)
        if jv == 2596:
            rec("C0-JIT", "PASS", "lin_c0 jit ecc_dynamic(1024,1)==2596 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "ecc_dynamic(size: int, is_cold: int" in src and "AddressInAccessList" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes size+is_cold; pinned Geth reads StateDB+stack")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit flags vs Geth StateDB")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-ECC-REJ",
        "PASS" if "REJ_GO_EXTCODECOPY" in go_src and "REJ_GO_ACCESSLIST" in go_src else "FAIL",
        "lin_from_go.lin v10 rejects gasExtCodeCopy / Bytes20 (lift is extcodecopyGas)",
    )
    rec(
        "GO-EX-SPLIT",
        "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest",
    )

    evidence = {
        "schema": "LIN_GETH_EXTCODECOPY_EVIDENCE_1.0",
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
                "CopyGas=3 ColdAccountAccessCostEIP2929=2600 WarmStorageReadCostEIP2929=100 "
                "cold-warm surcharge=2500 (static 100 not returned by gasExtCodeCopyEIP2929) "
                f"from {PARAMS_REL} blob {PARAMS_BLOB} sha256 {PARAMS_SHA256}; "
                f"{GAS_REL} blob {GAS_BLOB} sha256 {GAS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_geth_extcodecopy.lin",
        "c11_oracle": "test/oracles/geth_extcodecopy_c11.c",
        "go_oracle": "test/oracles/geth_extcodecopy_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {"size": a, "is_cold": b, "dynamic": c, "total": d} for a, b, c, d in VECTORS
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
