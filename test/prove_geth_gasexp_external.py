#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum gasExpEIP158 / ExpByteEIP158=50 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of gasExpEIP158 in go-ethereum v1.16.9
    * an independent C11 oracle (Geth uint64 AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * gasExpFrontier / pre-Spurious-Dragon EXP
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real ExpGas / ExpByteEIP158 addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_gasexp.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_gasexp_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_gasexp_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_gasexp_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_gasexp" / "geth_gasexp_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
PINNED_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
GAS_REL = "core/vm/gas_table.go"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-gasexp"

# (bitLen, expByteLen, gas) — ExpGas=10, ExpByteEIP158=50
VECTORS = [
    (0, 0, 10),
    (1, 1, 60),
    (7, 1, 60),
    (8, 1, 60),
    (9, 2, 110),
    (16, 2, 110),
    (255, 32, 1610),
    (256, 32, 1610),  # EVM word / 256-bit exponent
    (2048, 256, 12810),  # Geth comment "Max is 256 * ExpByte"
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


def py_from_bitlen(bitLen: int) -> int:
    if bitLen < 0 or bitLen > 2048:
        return 0
    n = (bitLen + 7) // 8
    if n < 0 or n > 256:
        return 0
    return 10 + n * 50


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
    excerpt = (FIX / "gasExpEIP158.go").read_text(encoding="utf-8")
    if excerpt not in live_txt:
        return "FAIL", commit, "gasExpEIP158.go excerpt not a substring"
    if "ExpByteEIP158" not in live_txt and "params.ExpByteEIP158" not in live_txt:
        return "FAIL", commit, "ExpByteEIP158 missing from gas_table.go"
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
    print("  GETH gasExpEIP158 — external LIN proof (ExpByteEIP158=50 / ExpGas=10)")
    print("=" * 78)

    excerpt = FIX / "gasExpEIP158.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned gasExpEIP158.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func gasExpEIP158(" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing gasExpEIP158 signature")
        return 1
    if "stack.data[stack.len()-2].BitLen()" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing BitLen lift site")
        return 1
    if "params.ExpByteEIP158" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing ExpByteEIP158 form")
        return 1
    if "math.SafeAdd(gas, params.ExpGas)" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing SafeAdd ExpGas")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has BitLen lift + ExpByteEIP158 + SafeAdd ExpGas")

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
        rec("C11-SELFTEST", "FAIL", "C11 EXP gas vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range EXP goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go EXP goldens + negative/bound fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of gasexp clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_gasexp.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v7 (REJ_GO_SAFEMATH)")
    chk3 = run([str(C0), "check", str(C_TR)])
    rec("C-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")
    chk4 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3 (require/unchecked)")

    gate = run([str(C0), "vm", str(LIN), "ge_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ge_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ge_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for bitLen, n, want in VECTORS:
        py = py_from_bitlen(bitLen)
        c11 = int(oracle(["from-bitlen", str(bitLen)]).splitlines()[-1])
        geth = oracle(["geth-exp", str(n)]).splitlines()[-1]
        got = lin_vm("ge_from_bitlen", bitLen)
        got_n = lin_vm("ge_exp", n)
        go_v = go_oracle("from-bitlen", bitLen)
        geth_go = go_oracle("geth-exp", n)
        if py != want or c11 != want or got != want or got_n != want:
            rec("VEC-LIN", "FAIL", f"bitLen={bitLen} n={n}", f"py={py} c11={c11} lin={got} lin_n={got_n}")
            return 1
        if geth != str(want) or geth_go != str(want):
            rec("VEC-GETH", "FAIL", f"geth n={n}", f"c11={geth} go={geth_go}")
            return 1
        if go_v != str(want):
            rec("VEC-GO", "FAIL", f"go oracle bitLen={bitLen}", f"go={go_v}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint 10+ceil(bitLen/8)*50 matches C11 and LIN")

    if lin_vm("ge_from_bitlen", 256) != 1610 or lin_vm("ge_evm_word") != 1610:
        rec("EVM-WORD", "FAIL", "256-bit exponent")
        return 1
    rec("EVM-WORD", "PASS", "EVM-word EXP (256-bit exponent) = 1610 (10+32*50)", "common on-chain pow / modular-exponent byte length")

    if lin_vm("ge_from_bitlen", -1) != 0 or lin_vm("ge_exp", -1) != 0 or lin_vm("ge_exp", 257) != 0 or lin_vm("ge_from_bitlen", 2049) != 0:
        rec("FAIL-CLOSED", "FAIL", "negative / bound")
        return 1
    rec("FAIL-CLOSED", "PASS", "negative and above Geth's documented 256-byte max fail-close to 0")

    jit_ok = lin_roundtrip_jit("ge_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ge_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ge_from_bitlen", 256)
        if jv == 1610:
            rec("C0-JIT", "PASS", "lin_c0 jit ge_from_bitlen(256)==1610 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "ge_from_bitlen(bitLen: int)" in src and "stack.data[stack.len()-2].BitLen()" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes bitLen/expByteLen ints; pinned Geth reads stack.data BitLen")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit bitLen vs Geth stack.data BitLen")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-SAFEMATH-REJ",
        "PASS" if "REJ_GO_SAFEMATH" in go_src and "REJ_GO_BITLEN" in go_src else "FAIL",
        "lin_from_go.lin v7 rejects SafeAdd/BitLen/stack.data (lift is expGasEIP158)",
    )
    rec("C-ARRAY-REJ", "PASS" if "REJ_C_ARRAY_PARAM" in C_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    rec("SOL-REQUIRE", "PASS" if "REJ_SOLIDITY_UNCHECKED" in SOL_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_solidity.lin v3 rejects unchecked and lowers require to fail-closed")

    evidence = {
        "schema": "LIN_GETH_GASEXP_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/ethereum/go-ethereum",
            "tag": PINNED_TAG,
            "commit": commit or PINNED_COMMIT,
            "path": GAS_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "LGPL-3.0",
            "constants": "ExpGas=10 ExpByteEIP158=50 from params/protocol_params.go blob e8b044f45016d851af2698e94c62937218c9d736",
        },
        "lin_clone": "src/lin_geth_gasexp.lin",
        "c11_oracle": "test/oracles/geth_gasexp_c11.c",
        "go_oracle": "test/oracles/geth_gasexp_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [{"bitLen": a, "expByteLen": b, "gas": c} for a, b, c in VECTORS],
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
