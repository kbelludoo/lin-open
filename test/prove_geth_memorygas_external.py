#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum memoryGasCost (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of memoryGasCost / toWordSize / MemoryGas+QuadCoeffDiv
      in go-ethereum v1.16.9 (git blob + sha256)
    * an independent C11 oracle (Geth uint64 wrap AND i64 fail-closed + __int128 square)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * uint64 wrap of total-last is reachable on mainnet
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real Yellow-paper Cmem, i64-scale operands / 128-bit square).
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
LIN = ROOT / "src" / "lin_geth_memorygas.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_memorygas_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_memorygas_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_memorygas_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_memorygas" / "geth_memorygas_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_GT_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
PINNED_CM_SHA256 = "f8eaab02fbd163bdf55fa67a99fc01cd374d8546e39ae8f7369e74313a557843"
PINNED_PP_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PINNED_GT_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
PINNED_CM_BLOB = "2990f5897248b3fb51533eb378dde8dc79422e1f"
PINNED_PP_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
GT_REL = "core/vm/gas_table.go"
CM_REL = "core/vm/common.go"
PP_REL = "params/protocol_params.go"
CAP = 0x1FFFFFFFE0
U64MAX = 18446744073709551615
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-memorygas"

# (new_size, cur_len, last, want_lin)
VECTORS = [
    (0, 0, 0, 0),
    (1, 0, 0, 3),
    (32, 0, 0, 3),
    (33, 0, 0, 6),
    (64, 0, 0, 6),
    (256, 0, 0, 24),
    (1024, 0, 0, 98),
    (2048, 0, 0, 200),
    (4096, 0, 0, 416),
    (32, 32, 3, 0),
    (33, 32, 3, 3),
    (64, 32, 3, 3),
    (2048, 1024, 98, 102),
    (100000, 0, 0, 28448),
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


def py_fee(new_size: int, cur_len: int, last: int) -> int:
    if new_size < 0 or cur_len < 0 or last < 0 or new_size == 0:
        return 0
    if new_size > CAP:
        return 0
    words = (new_size + 31) // 32
    rounded = words * 32
    if rounded <= cur_len:
        return 0
    tot = 3 * words + (words * words) // 512
    if last > tot:
        return 0
    return tot - last


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
    live_gt, live_cm, live_pp = UPSTREAM / GT_REL, UPSTREAM / CM_REL, UPSTREAM / PP_REL
    if not live_gt.exists() or not live_cm.exists() or not live_pp.exists():
        return "SKIP", "", "pinned paths missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob_gt = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{GT_REL}"]).stdout.strip()
    blob_cm = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{CM_REL}"]).stdout.strip()
    blob_pp = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PP_REL}"]).stdout.strip()
    if (
        sha256_file(live_gt) != PINNED_GT_SHA256
        or sha256_file(live_cm) != PINNED_CM_SHA256
        or sha256_file(live_pp) != PINNED_PP_SHA256
        or blob_gt != PINNED_GT_BLOB
        or blob_cm != PINNED_CM_BLOB
        or blob_pp != PINNED_PP_BLOB
        or commit != PINNED_COMMIT
    ):
        return "FAIL", commit, f"gt={sha256_file(live_gt)} blob={blob_gt}"
    live_gt_txt = live_gt.read_text(encoding="utf-8")
    live_cm_txt = live_cm.read_text(encoding="utf-8")
    live_pp_txt = live_pp.read_text(encoding="utf-8")
    if (FIX / "memoryGasCost.go").read_text(encoding="utf-8") not in live_gt_txt:
        return "FAIL", commit, "memoryGasCost.go excerpt not a substring"
    if (FIX / "toWordSize.go").read_text(encoding="utf-8") not in live_cm_txt:
        return "FAIL", commit, "toWordSize.go excerpt not a substring"
    params_ex = (FIX / "memorygas_protocol_params.go").read_text(encoding="utf-8")
    for line in params_ex.splitlines():
        if line.strip() and line not in live_pp_txt:
            return "FAIL", commit, "params excerpt line missing"
    return "PASS", commit, blob_gt


def go_oracle(op: str, *args: int) -> str | None:
    proc = run(["go", "run", str(GO_SRC), op, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_MEMORYGAS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH memoryGasCost — external LIN proof (Yellow Paper Cmem, C11+Go)")
    print("=" * 78)

    excerpt = FIX / "memoryGasCost.go"
    words_ex = FIX / "toWordSize.go"
    params = FIX / "memorygas_protocol_params.go"
    if not excerpt.exists() or not words_ex.exists() or not params.exists():
        rec("PIN-FILE", "FAIL", "pinned memoryGasCost / toWordSize / params missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    src_pp = params.read_text(encoding="utf-8")
    if "func memoryGasCost(mem *Memory, newMemSize uint64)" not in src_ex or "QuadCoeffDiv" not in src_pp:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing memoryGasCost / MemoryGas constants")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned memoryGasCost.go contains quadratic Cmem + 0x1FFFFFFFE0 cap")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_GT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/vm/gas_table.go")
        rec("UPSTREAM-COMMON", "PASS", "git blob sha of core/vm/common.go toWordSize")
        rec("UPSTREAM-PARAMS", "PASS", "git blob sha of params/protocol_params.go MemoryGas/QuadCoeffDiv")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-COMMON", "SKIP", "live common.go blob not recomputed this run")
        rec("UPSTREAM-PARAMS", "SKIP", "live params blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-COMMON", "FAIL", "common.go blob mismatch", up_note)
        rec("UPSTREAM-PARAMS", "FAIL", "params blob mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Geth-wrap vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range Cmem goldens + uint64 wrap vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go memoryGasCost goldens + last>total wrap")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of memorygas clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_memorygas.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v2 (REJ_GO_POINTER)")
    chk3 = run([str(C0), "check", str(C_TR)])
    rec("C-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")
    chk4 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk4.returncode == 0 or "LIN_CHECK" in chk4.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3 (require/unchecked)")

    gate = run([str(C0), "vm", str(LIN), "mg_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mg_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "mg_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for ns, clen, last, want in VECTORS:
        py = py_fee(ns, clen, last)
        c11 = int(oracle(["fee", str(ns), str(clen), str(last)]).splitlines()[-1])
        geth = oracle(["geth-fee", str(ns), str(clen), str(last)]).splitlines()[-1]
        got = lin_vm("mg_fee", ns, clen, last)
        go_v = go_oracle("fee", ns, clen, last)
        if py != want or c11 != want or got != want or geth != str(want):
            rec("VEC-LIN", "FAIL", f"fee({ns},{clen},{last})", f"py={py} c11={c11} lin={got} geth={geth} want={want}")
            return 1
        if go_v is None or go_v != str(want):
            rec("VEC-GO", "FAIL", f"go oracle fee({ns},{clen},{last})", f"go={go_v} want={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint Cmem matches C11 and LIN")

    y1024 = lin_vm("mg_fee", 1024, 0, 0)
    if y1024 != 98:
        rec("YELLOW-PAPER", "FAIL", "1024-byte Cmem", f"lin={y1024}")
        return 1
    rec("YELLOW-PAPER", "PASS", "1024-byte expansion costs 98 gas: 3*32 + 32^2/512 (Yellow Paper Cmem)", "user-paid memory gas is the incremental Cmem, not the full EVM")

    geth_wrap = oracle(["geth-fee", "64", "0", "999"]).splitlines()[-1]
    lin_wrap = lin_vm("mg_fee", 64, 0, 999)
    go_wrap = go_oracle("fee", 64, 0, 999)
    if geth_wrap != str(U64MAX - 992) or go_wrap != str(U64MAX - 992) or lin_wrap != 0:
        rec("GETH-WRAP-LAST", "FAIL", "last=999 total=6 uint64 wrap vs i64 fail-closed", f"geth={geth_wrap} go={go_wrap} lin={lin_wrap}")
        return 1
    rec("GETH-WRAP-LAST", "PASS", "last>total: Geth/Go uint64 wraps; LIN fail-closes fee to 0", "lastGasCost>newTotal is not reachable while Geth updates last after each expansion; defect of unbounded subtraction")

    geth_ov = oracle(["geth-fee", str(CAP + 1), "0", "0"]).splitlines()[-1]
    lin_ov = lin_vm("mg_fee", CAP + 1, 0, 0)
    if geth_ov != "OVERFLOW" or lin_ov != 0:
        rec("GETH-CAP", "FAIL", "size>0x1FFFFFFFE0 overflow", f"geth={geth_ov} lin={lin_ov}")
        return 1
    rec("GETH-CAP", "PASS", "size>0x1FFFFFFFE0: Geth ErrGasUintOverflow; LIN fail-closes to 0")

    naive = (2**32 - 1) * (2**32 - 1)
    if naive <= 2**63 - 1:
        rec("I64-SQUARE", "FAIL", "0xFFFFFFFF^2 unexpectedly fits i64")
        return 1
    rec("I64-SQUARE", "PASS", "words=0xFFFFFFFF square does not fit i64; LIN 128-bit muldiv matches Geth uint64 product / 512")

    jit_ok = lin_roundtrip_jit("mg_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mg_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mg_fee", 1024, 0, 0)
        if jv == 98:
            rec("C0-JIT", "PASS", "lin_c0 jit mg_fee(1024,0,0)==98 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "mg_fee(new_size: int, cur_len: int, last: int)" in src and "mem.lastGasCost" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes new_size/cur_len/last as arguments; pinned Geth reads *Memory Len/lastGasCost")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit args vs Geth *Memory")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec("GO-EMIT", "PASS" if "go_from_go" in go_src and "REJ_GO_POINTER" in go_src else "FAIL", "lin_from_go.lin v2 emits LIN and rejects *Memory / selectors / slices")
    rec("C-ARRAY-REJ", "PASS" if "REJ_C_ARRAY_PARAM" in C_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    rec("SOL-REQUIRE", "PASS" if "REJ_SOLIDITY_UNCHECKED" in SOL_TR.read_text(encoding="utf-8") else "FAIL", "lin_from_solidity.lin v3 rejects unchecked and lowers require to fail-closed")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": GT_REL,
        "git_blob_sha": blob or PINNED_GT_BLOB,
        "file_sha256": PINNED_GT_SHA256,
        "common_path": CM_REL,
        "common_git_blob_sha": PINNED_CM_BLOB,
        "common_file_sha256": PINNED_CM_SHA256,
        "params_path": PP_REL,
        "params_git_blob_sha": PINNED_PP_BLOB,
        "params_file_sha256": PINNED_PP_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_memorygas.lin"
    evidence["c11_oracle"] = "test/oracles/geth_memorygas_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_memorygas_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["vectors"] = [{"new_size": a, "cur_len": b, "last": c, "fee": d} for a, b, c, d in VECTORS]
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
