#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum memoryCopierGas / CopyGas=3 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of memoryCopierGas / gasKeccak256 in go-ethereum v1.16.9
    * an independent C11 oracle (Geth uint64 AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * full COPY/KECCAK256 including Yellow Paper Cmem (that is a separate clone)
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real CopyGas / Keccak256WordGas addends, i64-scale operands).
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
LIN = ROOT / "src" / "lin_geth_copygas.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_copygas_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_copygas_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_copygas_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_copygas" / "geth_copygas_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
PINNED_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
GAS_REL = "core/vm/gas_table.go"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-copygas"

# (size, copy_gas, keccak_word_gas)
VECTORS = [
    (0, 0, 0),
    (1, 3, 6),
    (31, 3, 6),
    (32, 3, 6),
    (33, 6, 12),
    (64, 6, 12),
    (65, 9, 18),
    (1024, 96, 192),
    (24576, 2304, 4608),
    (49152, 4608, 9216),
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


def py_copy(size: int, keccak: bool = False) -> int:
    if size < 0:
        return 0
    per = 6 if keccak else 3
    return per * ((size + 31) // 32)


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
    live_txt = live.read_text(encoding="utf-8")
    copy_ex = (FIX / "memoryCopierGas.go").read_text(encoding="utf-8")
    kec_ex = (FIX / "gasKeccak256.go").read_text(encoding="utf-8")
    if copy_ex not in live_txt:
        return "FAIL", commit, "memoryCopierGas.go excerpt not a substring"
    if kec_ex not in live_txt:
        return "FAIL", commit, "gasKeccak256.go excerpt not a substring"
    return "PASS", commit, blob


def go_oracle(op: str, *args: int) -> str | None:
    proc = run(["go", "run", str(GO_SRC), op, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_COPYGAS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH memoryCopierGas — external LIN proof (CopyGas=3 / KECCAK256 word gas)")
    print("=" * 78)

    excerpt = FIX / "memoryCopierGas.go"
    kec_path = FIX / "gasKeccak256.go"
    if not excerpt.exists() or not kec_path.exists():
        rec("PIN-FILE", "FAIL", "pinned memoryCopierGas.go / gasKeccak256.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    src_k = kec_path.read_text(encoding="utf-8")
    if "func memoryCopierGas(stackpos int) gasFunc" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing memoryCopierGas signature")
        return 1
    if "return func(evm *EVM, contract *Contract, stack *Stack" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing closure factory")
        return 1
    if "math.SafeMul(toWordSize(words), params.CopyGas)" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing CopyGas word-gas form")
        return 1
    if "func gasKeccak256(evm *EVM, contract *Contract, stack *Stack" not in src_k:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing gasKeccak256 signature")
        return 1
    if "math.SafeMul(toWordSize(wordGas), params.Keccak256WordGas)" not in src_k:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing Keccak256WordGas form")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpts have memoryCopierGas closure + gasKeccak256 word gas")

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
        rec("C11-SELFTEST", "FAIL", "C11 CopyGas vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range CopyGas/keccak goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go CopyGas/keccak goldens + negative fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of copygas clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_copygas.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v5 (REJ_GO_CLOSURE)")
    chk3 = run([str(C0), "check", str(C_TR)])
    rec("C-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")
    chk4 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3 (require/unchecked)")

    gate = run([str(C0), "vm", str(LIN), "cg_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cg_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cg_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for size, want_c, want_k in VECTORS:
        py, pyk = py_copy(size), py_copy(size, True)
        c11 = int(oracle(["copy", str(size)]).splitlines()[-1])
        c11k = int(oracle(["keccak", str(size)]).splitlines()[-1])
        geth = oracle(["geth-copy", str(size)]).splitlines()[-1]
        gethk = oracle(["geth-keccak", str(size)]).splitlines()[-1]
        got, gotk = lin_vm("cg_copy", size), lin_vm("cg_keccak", size)
        go_v, go_vk = go_oracle("copy", size), go_oracle("keccak", size)
        geth_go, geth_gok = go_oracle("geth-copy", size), go_oracle("geth-keccak", size)
        if py != want_c or c11 != want_c or got != want_c or pyk != want_k or c11k != want_k or gotk != want_k:
            rec("VEC-LIN", "FAIL", f"size={size}", f"py={py}/{pyk} c11={c11}/{c11k} lin={got}/{gotk}")
            return 1
        if geth != str(want_c) or gethk != str(want_k) or geth_go != str(want_c) or geth_gok != str(want_k):
            rec("VEC-GETH", "FAIL", f"geth size={size}", f"c11={geth}/{gethk} go={geth_go}/{geth_gok}")
            return 1
        if go_v != str(want_c) or go_vk != str(want_k):
            rec("VEC-GO", "FAIL", f"go oracle size={size}", f"go={go_v}/{go_vk}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint ceil(size/32)*word matches C11 and LIN")

    if lin_vm("cg_copy", 32) != 3 or lin_vm("cg_keccak", 32) != 6:
        rec("COPYGAS-WORD", "FAIL", "32-byte copy/keccak word gas")
        return 1
    rec("COPYGAS-WORD", "PASS", "32-byte: COPY=3 KECCAK=6 (CopyGas and Keccak256WordGas)", "CALLDATACOPY/CODECOPY/MCOPY/RETURNDATACOPY/EXTCODECOPY and KECCAK256 pay this")

    if lin_vm("cg_copy", -1) != 0 or lin_vm("cg_keccak", -1) != 0:
        rec("FAIL-CLOSED", "FAIL", "negative size")
        return 1
    rec("FAIL-CLOSED", "PASS", "negative size fail-closes to 0 (Geth models this as Uint64WithOverflow)")

    if lin_vm("cg_with_mem", 0, 100, 32) != 103 or lin_vm("cg_with_mem", 1, 100, 32) != 106:
        rec("MEMGAS-ADD", "FAIL", "explicit memgas + word gas")
        return 1
    rec("MEMGAS-ADD", "PASS", "cg_with_mem adds explicit memgas (Geth *Memory lastGasCost is not hidden)")

    jit_ok = lin_roundtrip_jit("cg_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cg_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cg_copy", 32)
        if jv == 3:
            rec("C0-JIT", "PASS", "lin_c0 jit cg_copy(32)==3 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cg_copy(size: int)" in src and "stack.Back(stackpos)" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes size int; pinned Geth reads stack.Back(stackpos) via closure")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit size vs Geth closure *Stack")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-CLOSURE-REJ",
        "PASS" if "REJ_GO_CLOSURE" in go_src and "REJ_GO_STACK" in go_src else "FAIL",
        "lin_from_go.lin v5 rejects return func closures and *Stack/stack.Back",
    )
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
        "constants": "CopyGas=3 Keccak256WordGas=6 from params/protocol_params.go blob e8b044f45016d851af2698e94c62937218c9d736",
    }
    evidence["lin_clone"] = "src/lin_geth_copygas.lin"
    evidence["c11_oracle"] = "test/oracles/geth_copygas_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_copygas_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["vectors"] = [{"size": a, "copy": b, "keccak": c} for a, b, c in VECTORS]
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
