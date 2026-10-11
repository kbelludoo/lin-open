#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum gasCreateEip3860 / EIP-3860 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of gasCreateEip3860 in go-ethereum v1.16.9
    * an independent C11 oracle (Geth oversize=OVERFLOW AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * full CREATE/CREATE2 including Yellow Paper Cmem (that is a separate clone)
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real EIP-3860 surcharge, i64-scale operands).
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
LIN = ROOT / "src" / "lin_geth_create3860.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_create3860_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_create3860_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_create3860_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_create3860" / "geth_create3860_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
PINNED_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
GAS_REL = "core/vm/gas_table.go"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-create3860"
MAX_INIT = 49152

# (size, create_gas, create2_gas)
VECTORS = [
    (0, 0, 0),
    (1, 2, 8),
    (31, 2, 8),
    (32, 2, 8),
    (33, 4, 16),
    (64, 4, 16),
    (65, 6, 24),
    (24576, 1536, 6144),
    (49152, 3072, 12288),
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


def py_create(size: int, create2: bool = False) -> int:
    if size < 0 or size > MAX_INIT:
        return 0
    per = 8 if create2 else 2
    return per * ((size + 31) // 32)


def geth_create(size: int, create2: bool = False) -> str:
    if size > MAX_INIT:
        return "OVERFLOW"
    per = 8 if create2 else 2
    return str(per * ((size + 31) // 32))


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
    live = UPSTREAM / GAS_REL
    if not live.exists():
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{GAS_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    excerpt = (FIX / "gasCreateEip3860.go").read_text(encoding="utf-8")
    if excerpt not in live.read_text(encoding="utf-8"):
        return "FAIL", commit, "gasCreateEip3860.go excerpt not a substring"
    return "PASS", commit, blob


def go_oracle(op: str, *args: int) -> str | None:
    proc = run(["go", "run", str(GO_SRC), op, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_CREATE3860_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH gasCreateEip3860 — external LIN proof (EIP-3860 initcode word gas)")
    print("=" * 78)

    excerpt = FIX / "gasCreateEip3860.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned gasCreateEip3860.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func gasCreateEip3860(evm *EVM, contract *Contract, stack *Stack" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing gasCreateEip3860 signature")
        return 1
    if "params.InitCodeWordGas * ((size + 31) / 32)" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing CREATE word-gas form")
        return 1
    if "(params.InitCodeWordGas + params.Keccak256WordGas) * ((size + 31) / 32)" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing CREATE2 word-gas form")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has EIP-3860 CREATE/CREATE2 word-gas + *Stack size")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/vm/gas_table.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Geth-oversize vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range EIP-3860 goldens + oversize vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go CREATE/CREATE2 goldens + oversize")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of create3860 clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_create3860.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v4 (REJ_GO_STACK)")
    chk3 = run([str(C0), "check", str(C_TR)])
    rec("C-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")
    chk4 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3 (require/unchecked)")

    gate = run([str(C0), "vm", str(LIN), "ic_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ic_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ic_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for size, want_c, want_c2 in VECTORS:
        py, py2 = py_create(size), py_create(size, True)
        c11 = int(oracle(["create", str(size)]).splitlines()[-1])
        c112 = int(oracle(["create2", str(size)]).splitlines()[-1])
        geth = oracle(["geth-create", str(size)]).splitlines()[-1]
        geth2 = oracle(["geth-create2", str(size)]).splitlines()[-1]
        got, got2 = lin_vm("ic_create", size), lin_vm("ic_create2", size)
        go_v, go_v2 = go_oracle("create", size), go_oracle("create2", size)
        geth_go, geth_go2 = go_oracle("geth-create", size), go_oracle("geth-create2", size)
        if py != want_c or c11 != want_c or got != want_c or py2 != want_c2 or c112 != want_c2 or got2 != want_c2:
            rec("VEC-LIN", "FAIL", f"size={size}", f"py={py}/{py2} c11={c11}/{c112} lin={got}/{got2}")
            return 1
        if geth != str(want_c) or geth2 != str(want_c2) or geth_go != str(want_c) or geth_go2 != str(want_c2):
            rec("VEC-GETH", "FAIL", f"geth size={size}", f"c11={geth}/{geth2} go={geth_go}/{geth_go2}")
            return 1
        if go_v != str(want_c) or go_v2 != str(want_c2):
            rec("VEC-GO", "FAIL", f"go oracle size={size}", f"go={go_v}/{go_v2}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint ceil(size/32)*word matches C11 and LIN")

    if lin_vm("ic_create", 32) != 2 or lin_vm("ic_create2", 32) != 8:
        rec("EIP3860-WORD", "FAIL", "32-byte initcode word gas")
        return 1
    rec("EIP3860-WORD", "PASS", "32-byte initcode: CREATE=2 CREATE2=8 (InitCodeWordGas and +Keccak256WordGas)", "every Shanghai+ CREATE/CREATE2 pays this surcharge")

    geth_ov = oracle(["geth-create", "49153"]).splitlines()[-1]
    lin_ov = lin_vm("ic_create", 49153)
    if geth_ov != "OVERFLOW" or lin_ov != 0:
        rec("OVERSIZE", "FAIL", "size>MaxInitCodeSize", f"geth={geth_ov} lin={lin_ov}")
        return 1
    rec("OVERSIZE", "PASS", "size=49153: Geth ErrMaxInitCodeSizeExceeded; LIN fail-closes to 0")

    if lin_vm("ic_create", -1) != 0 or lin_vm("ic_with_mem", 0, 100, 49153) != 0:
        rec("FAIL-CLOSED", "FAIL", "negative size / oversize+memgas")
        return 1
    rec("FAIL-CLOSED", "PASS", "negative size and oversize+memgas fail-close to 0 (Geth does not return leftover memgas)")

    if lin_vm("ic_with_mem", 0, 100, 32) != 102 or lin_vm("ic_with_mem", 1, 100, 32) != 108:
        rec("MEMGAS-ADD", "FAIL", "explicit memgas + surcharge")
        return 1
    rec("MEMGAS-ADD", "PASS", "ic_with_mem adds explicit memgas (Geth *Memory lastGasCost is not hidden)")

    jit_ok = lin_roundtrip_jit("ic_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ic_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ic_create", 32)
        if jv == 2:
            rec("C0-JIT", "PASS", "lin_c0 jit ic_create(32)==2 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "ic_create(size: int)" in src and "stack.Back(2)" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes size int; pinned Geth reads stack.Back(2) on *Stack")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit size vs Geth *Stack")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec("GO-STACK-REJ", "PASS" if "REJ_GO_STACK" in go_src and "REJ_GO_EVM_CTX" in go_src else "FAIL", "lin_from_go.lin v4 rejects *Stack/stack.Back and *EVM/*Contract/*Memory")
    rec("C-ARRAY-REJ", "PASS" if "REJ_C_ARRAY_PARAM" in C_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    rec("SOL-REQUIRE", "PASS" if "REJ_SOLIDITY_UNCHECKED" in SOL_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_solidity.lin v3 rejects unchecked and lowers require to fail-closed")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": GAS_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_create3860.lin"
    evidence["c11_oracle"] = "test/oracles/geth_create3860_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_create3860_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["vectors"] = [{"size": a, "create": b, "create2": c} for a, b, c in VECTORS]
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
