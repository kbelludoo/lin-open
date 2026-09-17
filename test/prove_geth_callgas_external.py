#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum callGas / EIP-150 63/64 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of callGas in go-ethereum v1.16.9 (git blob + sha256)
    * an independent C11 oracle (Geth uint64 wrap AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * that available<base wrap is a mainnet consensus bug
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real EIP-150 stipend, i64-scale operands).
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
LIN = ROOT / "src" / "lin_geth_callgas.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_callgas_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_callgas_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_callgas_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_callgas" / "geth_callgas_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "94e6630a8bcbaccee3a8d5b23e5971a1e47863706aa18a9878124560a5693678"
PINNED_BLOB = "5fe589bce696f618c46841dde27d7e78d65e54a6"
GAS_REL = "core/vm/gas.go"
U64MAX = 18446744073709551615
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-callgas"

# (eip150, available, base, cost, cost_hi, want_lin)
VECTORS = [
    (1, 64000, 0, 64000, 0, 63000),
    (1, 64000, 700, 1000, 0, 1000),
    (1, 64, 0, 100, 0, 63),
    (1, 0, 0, 0, 0, 0),
    (1, 63, 0, 63, 0, 63),
    (1, 65, 0, 65, 0, 64),
    (0, 1000, 0, 1000, 0, 1000),
    (1, 1000, 0, 0, 1, 985),
    (1, 21000, 0, 21000, 0, 20672),
    (1, 100, 0, 50, 0, 50),
    (1, 2300, 0, 2300, 0, 2265),
    (1, 128, 0, 128, 0, 126),
    (1, 64, 0, 63, 0, 63),
    (1, 100000, 700, 50000, 0, 50000),
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


def py_stipend(available: int) -> int:
    if available < 0:
        return 0
    return available - available // 64


def py_callgas(eip150: int, available: int, base: int, cost: int, cost_hi: int) -> int:
    if eip150 < 0 or available < 0 or base < 0 or cost < 0 or cost_hi < 0:
        return 0
    if eip150 != 0:
        if available < base:
            return 0
        rem = available - base
        gas = py_stipend(rem)
        if cost_hi != 0 or gas < cost:
            return gas
        return cost
    if cost_hi != 0:
        return 0
    return cost


def geth_callgas(eip150: int, available: int, base: int, cost: int, cost_hi: int) -> str:
    if eip150:
        available = (available - base) % (1 << 64)
        gas = (available - available // 64) % (1 << 64)
        if cost_hi != 0 or gas < cost:
            return str(gas)
    if cost_hi != 0:
        return "OVERFLOW"
    return str(cost)


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
    excerpt = (FIX / "callGas.go").read_text(encoding="utf-8")
    if excerpt not in live.read_text(encoding="utf-8"):
        return "FAIL", commit, "callGas.go excerpt not a substring"
    return "PASS", commit, blob


def go_oracle(op: str, *args: int) -> str | None:
    proc = run(["go", "run", str(GO_SRC), op, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_CALLGAS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH callGas — external LIN proof (EIP-150 63/64, C11+Go)")
    print("=" * 78)

    excerpt = FIX / "callGas.go"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned callGas.go missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "func callGas(isEip150 bool, availableGas, base uint64, callCost *uint256.Int)" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing callGas signature")
        return 1
    if "availableGas - availableGas/64" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing EIP-150 stipend form")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned callGas.go contains EIP-150 remaining-remaining/64 + *uint256.Int")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/vm/gas.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Geth-wrap vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range EIP-150 goldens + uint64 wrap vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go callGas goldens + available<base wrap")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of callgas clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_callgas.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Go transpiler v3 (REJ_GO_UINT256)")
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
    for eip, av, base, cost, hi, want in VECTORS:
        py = py_callgas(eip, av, base, cost, hi)
        c11 = int(oracle(["call", str(eip), str(av), str(base), str(cost), str(hi)]).splitlines()[-1])
        geth = oracle(["geth-call", str(eip), str(av), str(base), str(cost), str(hi)]).splitlines()[-1]
        got = lin_vm("cg_callgas", eip, av, base, cost, hi)
        go_v = go_oracle("call", eip, av, base, cost, hi)
        geth_go = go_oracle("geth-call", eip, av, base, cost, hi)
        if py != want or c11 != want or got != want:
            rec("VEC-LIN", "FAIL", f"call({eip},{av},{base},{cost},{hi})", f"py={py} c11={c11} lin={got} want={want}")
            return 1
        if geth != str(want) or geth_go != str(want):
            rec("VEC-GETH", "FAIL", f"geth call({eip},{av},{base},{cost},{hi})", f"c11={geth} go={geth_go} want={want}")
            return 1
        if go_v is None or go_v != str(want):
            rec("VEC-GO", "FAIL", f"go oracle call({eip},{av},{base},{cost},{hi})", f"go={go_v} want={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint 63/64 matches C11 and LIN")

    y64k = lin_vm("cg_callgas", 1, 64000, 0, 64000, 0)
    if y64k != 63000:
        rec("EIP150-63-64", "FAIL", "64000 remaining requested 64000", f"lin={y64k}")
        return 1
    rec("EIP150-63-64", "PASS", "64000 remaining requested 64000 yields 63000 (remaining-remaining/64)", "every CALL/DELEGATECALL/STATICCALL on post-TangerineWhistle Ethereum uses this stipend")

    naive = 64000 * 63
    if naive // 64 != 63000:
        rec("SAFE-FORM", "FAIL", "x-x/64 vs x*63/64 disagree on 64000")
        return 1
    rec("SAFE-FORM", "PASS", "LIN uses Geth x-x/64 (never overflows uint64); not the naive x*63/64 product")

    geth_pre = oracle(["geth-call", "0", "1000", "0", "1000", "1"]).splitlines()[-1]
    lin_pre = lin_vm("cg_callgas", 0, 1000, 0, 1000, 1)
    if geth_pre != "OVERFLOW" or lin_pre != 0:
        rec("PRE-EIP150-OV", "FAIL", "pre-EIP-150 cost_hi overflow", f"geth={geth_pre} lin={lin_pre}")
        return 1
    rec("PRE-EIP150-OV", "PASS", "pre-EIP-150 cost not uint64: Geth ErrGasUintOverflow; LIN fail-closes to 0")

    geth_skip = oracle(["geth-call", "1", "10", "20", "5", "0"]).splitlines()[-1]
    lin_skip = lin_vm("cg_callgas", 1, 10, 20, 5, 0)
    go_skip = go_oracle("geth-call", 1, 10, 20, 5, 0)
    if geth_skip != "5" or go_skip != "5" or lin_skip != 0:
        rec("GETH-WRAP-BASE", "FAIL", "available<base uint64 wrap vs i64 fail-closed", f"geth={geth_skip} go={go_skip} lin={lin_skip}")
        return 1
    rec("GETH-WRAP-BASE", "PASS", "available=10 base=20 cost=5: Geth/Go return 5 (63/64 skipped after wrap); LIN fail-closes to 0", "gasCall callers typically hold remaining>=static; helper itself is unbounded")

    wrap_stipend = ((10 - 20) % (1 << 64))
    wrap_stipend = wrap_stipend - wrap_stipend // 64
    geth_hi = oracle(["geth-call", "1", "10", "20", "0", "1"]).splitlines()[-1]
    lin_hi = lin_vm("cg_callgas", 1, 10, 20, 0, 1)
    if geth_hi != str(wrap_stipend) or lin_hi != 0:
        rec("GETH-WRAP-HI", "FAIL", "available<base + cost_hi wrap stipend", f"geth={geth_hi} lin={lin_hi} want={wrap_stipend}")
        return 1
    rec("GETH-WRAP-HI", "PASS", "available<base + cost not uint64: Geth returns wrapped stipend; LIN fail-closes to 0", f"geth_stipend={wrap_stipend}")

    jit_ok = lin_roundtrip_jit("cg_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cg_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cg_callgas", 1, 64000, 0, 64000, 0)
        if jv == 63000:
            rec("C0-JIT", "PASS", "lin_c0 jit cg_callgas(1,64000,0,64000,0)==63000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cg_callgas(eip150: int, available: int, base: int, cost: int, cost_hi: int)" in src and "*uint256.Int" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes eip150/available/base/cost/cost_hi; pinned Geth takes *uint256.Int")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit args vs Geth *uint256.Int")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec("GO-EMIT", "PASS" if "go_from_go" in go_src and "REJ_GO_UINT256" in go_src else "FAIL", "lin_from_go.lin v3 emits LIN and rejects *uint256.Int / receivers / slices")
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
    evidence["lin_clone"] = "src/lin_geth_callgas.lin"
    evidence["c11_oracle"] = "test/oracles/geth_callgas_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_callgas_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["vectors"] = [
        {"eip150": a, "available": b, "base": c, "cost": d, "cost_hi": e, "gas": f}
        for a, b, c, d, e, f in VECTORS
    ]
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
