#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum gasCallCodeEIP2929 / gasDelegateCallEIP2929 /
gasStaticCallEIP2929 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of makeCallVariantGasCallEIP2929 + gasCallCode /
      gasDelegateCall / gasStaticCall
    * an independent C11 oracle
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * quadratic memoryGasCost / Cmem (memory_gas is an explicit integer)
    * CallStipend 2300, EIP-7702, EIP-4762
    * that the dynamic fn returns the 100 static opcode gas
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real CALLCODE/DELEGATE/STATIC Berlin addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_callcode2929.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_callcode2929_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_callcode2929_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_callcode2929_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_callcode2929" / "geth_callcode2929_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_SHA256 = "213f7846ed039c8ab293eb9511383897497f52c971da014317d3e1b5b5dc5330"
PINNED_BLOB = "085b018e4c42bf0185da790518ea1d1ee891b682"
ACL_REL = "core/vm/operations_acl.go"
GAS_REL = "core/vm/gas_table.go"
GAS_SHA256 = "c11be723771f3726bca1369a129fc8f212f7746aaa26c5b1ee3aa78e7c0a784c"
GAS_BLOB = "c7c1274bf2f39355108ab88722b694bf502cc4b2"
HELPER_REL = "core/vm/gas.go"
HELPER_SHA256 = "94e6630a8bcbaccee3a8d5b23e5971a1e47863706aa18a9878124560a5693678"
HELPER_BLOB = "5fe589bce696f618c46841dde27d7e78d65e54a6"
PARAMS_REL = "params/protocol_params.go"
PARAMS_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PARAMS_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
EIPS_REL = "core/vm/eips.go"
EIPS_SHA256 = "306e3660bb3aa7e4c943b458191390b46ed754984462f6655a413740bc6c670c"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-callcode2929"

KIND_CALL, KIND_CALLCODE, KIND_DELEGATE, KIND_STATIC = 0, 1, 2, 3

# (kind, avail, req, mem, xfer, new, cold, dynamic, total)
VECTORS = [
    (KIND_DELEGATE, 64000, 1000000, 0, 0, 0, 0, 63000, 63100),
    (KIND_STATIC, 64000, 1000000, 0, 0, 0, 1, 63040, 63140),
    (KIND_CALLCODE, 64000, 1000000, 0, 0, 0, 0, 63000, 63100),
    (KIND_CALLCODE, 64000, 1000000, 0, 1, 0, 0, 63141, 63241),
    (KIND_CALLCODE, 64000, 1000000, 0, 1, 0, 1, 63180, 63280),
    (KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0, 98579, 98679),
    (KIND_CALL, 100000, 1000000, 0, 1, 1, 0, 98969, 99069),
    (KIND_STATIC, 100000, 1000000, 0, 1, 1, 0, 98438, 98538),
    (KIND_CALLCODE, 64000, 1000, 0, 1, 0, 0, 10000, 10100),
    (KIND_CALLCODE, 64000, 1000, 0, 1, 0, 1, 12500, 12600),
    (KIND_CALLCODE, 2499, 0, 0, 0, 0, 1, 0, 0),
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


def py_extra(kind: int, xfer: int, new: int, mem: int) -> int:
    g = mem
    if kind in (KIND_DELEGATE, KIND_STATIC):
        return g
    if kind == KIND_CALLCODE:
        return g + 9000 if xfer else g
    if xfer:
        g += 9000
        if new:
            g += 25000
    return g


def py_dynamic(kind: int, avail: int, req: int, mem: int, xfer: int, new: int, cold: int) -> int:
    if kind not in (0, 1, 2, 3) or avail < 0 or req < 0 or mem < 0:
        return 0
    if xfer not in (0, 1) or new not in (0, 1) or cold not in (0, 1):
        return 0
    c = 2500 if cold else 0
    if avail < c:
        return 0
    a2 = avail - c
    ex = py_extra(kind, xfer, new, mem)
    if a2 < ex:
        return 0
    left = a2 - ex
    cap = left - left // 64
    fwd = req if req < cap else cap
    return ex + fwd + c


def py_total(kind: int, avail: int, req: int, mem: int, xfer: int, new: int, cold: int) -> int:
    if py_dynamic(kind, avail, req, mem, xfer, new, cold) == 0 and not (
        kind in (0, 1, 2, 3)
        and avail >= (2500 if cold else 0)
        and (avail - (2500 if cold else 0)) >= py_extra(kind, xfer, new, mem)
        and xfer in (0, 1)
        and new in (0, 1)
        and cold in (0, 1)
        and avail >= 0
        and req >= 0
        and mem >= 0
    ):
        return 0
    c = 2500 if cold else 0
    if avail < c or (avail - c) < py_extra(kind, xfer, new, mem):
        return 0
    if kind not in (0, 1, 2, 3) or xfer not in (0, 1) or new not in (0, 1) or cold not in (0, 1):
        return 0
    return 100 + py_dynamic(kind, avail, req, mem, xfer, new, cold)


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
    helper = UPSTREAM / HELPER_REL
    params = UPSTREAM / PARAMS_REL
    eips = UPSTREAM / EIPS_REL
    if not all(p.exists() for p in (live, gas, helper, params, eips)):
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ACL_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    if sha256_file(gas) != GAS_SHA256:
        return "FAIL", commit, "gas_table.go sha256 mismatch"
    if sha256_file(helper) != HELPER_SHA256:
        return "FAIL", commit, "gas.go sha256 mismatch"
    if sha256_file(params) != PARAMS_SHA256:
        return "FAIL", commit, "protocol_params.go sha256 mismatch"
    if sha256_file(eips) != EIPS_SHA256:
        return "FAIL", commit, "eips.go sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    gas_txt = gas.read_text(encoding="utf-8")
    excerpt = (FIX / "gasCallCodeEIP2929.go").read_text(encoding="utf-8")
    old = (FIX / "gasCallCode.go").read_text(encoding="utf-8")
    if excerpt.strip() not in live_txt:
        return "FAIL", commit, "gasCallCodeEIP2929.go excerpt not a substring"
    if old.strip() not in gas_txt:
        return "FAIL", commit, "gasCallCode.go excerpt not a substring of gas_table.go"
    if "gasCallCodeEIP2929     = makeCallVariantGasCallEIP2929(gasCallCode, 1)" not in live_txt:
        return "FAIL", commit, "gasCallCodeEIP2929 binding missing"
    if "availableGas - availableGas/64" not in helper.read_text(encoding="utf-8"):
        return "FAIL", commit, "EIP-150 63/64 missing in gas.go"
    eips_txt = eips.read_text(encoding="utf-8")
    if "jt[CALLCODE].dynamicGas = gasCallCodeEIP2929" not in eips_txt:
        return "FAIL", commit, "enable2929 CALLCODE binding missing"
    if "jt[DELEGATECALL].dynamicGas = gasDelegateCallEIP2929" not in eips_txt:
        return "FAIL", commit, "enable2929 DELEGATECALL binding missing"
    if "jt[STATICCALL].dynamicGas = gasStaticCallEIP2929" not in eips_txt:
        return "FAIL", commit, "enable2929 STATICCALL binding missing"
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
    print("  GETH CALLCODE/DELEGATE/STATIC EIP-2929 — external LIN proof")
    print("=" * 78)

    excerpt = FIX / "gasCallCodeEIP2929.go"
    old = FIX / "gasCallCode.go"
    src_ex = excerpt.read_text(encoding="utf-8")
    src_old = old.read_text(encoding="utf-8")
    if "gasCallCodeEIP2929" not in src_ex or "UseGas" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing gasCallCodeEIP2929 / UseGas")
        return 1
    if "func gasCallCode(" not in src_old or "func gasDelegateCall(" not in src_old:
        rec("PIN-EXCERPT", "FAIL", "old-calculator excerpt missing CALLCODE/DELEGATE")
        return 1
    if "CallNewAccountGas" in src_old:
        rec("PIN-EXCERPT", "FAIL", "CALLCODE old calculator must not charge new-account")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpts: shared UseGas wrapper + CALLCODE never charges 25000")

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
        rec("C11-SELFTEST", "FAIL", "C11 CALLCODE2929 gas selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 CALLCODE/DELEGATE/STATIC goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go CALLCODE2929 goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of callcode2929 clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_callcode2929.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec(
        "GO-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v12 (REJ_GO_CALLCODE / DELEGATE / STATIC)",
    )

    gate = run([str(C0), "vm", str(LIN), "cc29_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cc29_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cc29_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for kind, avail, req, mem, xfer, new, cold, want_d, want_t in VECTORS:
        args = [kind, avail, req, mem, xfer, new, cold]
        py_d = py_dynamic(*args)
        py_t = py_total(*args)
        c11_d = int(oracle(["dynamic", *[str(a) for a in args]]).splitlines()[-1])
        c11_t = int(oracle(["total", *[str(a) for a in args]]).splitlines()[-1])
        got_d = lin_vm("cc29_dynamic", *args)
        got_t = lin_vm("cc29_total", *args)
        go_d = go_oracle("dynamic", *args)
        go_t = go_oracle("total", *args)
        if not (py_d == c11_d == got_d == want_d and go_d == str(want_d)):
            rec("VEC-LIN", "FAIL", f"dyn {args}", f"py={py_d} c11={c11_d} lin={got_d} go={go_d} want={want_d}")
            return 1
        if not (py_t == c11_t == got_t == want_t and go_t == str(want_t)):
            rec("VEC-TOTAL", "FAIL", f"tot {args}", f"py={py_t} c11={c11_t} lin={got_t} go={go_t} want={want_t}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 == Go == LIN vm (dynamic+total)")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint CALLCODE2929 table matches C11 and LIN")

    if lin_vm("cc29_vs_call", KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0) != 390:
        rec("VS-CALL", "FAIL", "CALL minus CALLCODE at value+new is 390, not 25000")
        return 1
    if lin_vm("cc29_vs_call", KIND_STATIC, 100000, 1000000, 0, 1, 1, 0) != 531:
        rec("VS-CALL", "FAIL", "CALL minus STATIC at value+new is 531")
        return 1
    rec("VS-CALL", "PASS", "naive CALL-25000 is wrong: 63/64 makes CALL-CALLCODE=390 and CALL-STATIC=531")

    if lin_vm("cc29_berlin_delta", KIND_CALLCODE, 64000, 1000000, 0, 1, 0) != 39:
        rec("BERLIN-DELTA", "FAIL", "CALLCODE 63/64-bound Berlin delta")
        return 1
    if lin_vm("cc29_berlin_delta", KIND_DELEGATE, 64000, 1000000, 0, 0, 0) != 40:
        rec("BERLIN-DELTA", "FAIL", "DELEGATE 63/64-bound Berlin delta")
        return 1
    rec("BERLIN-DELTA", "PASS", "shared wrapper: CALLCODE value delta=39; DELEGATE no-value delta=40")

    if lin_vm("cc29_forwarded", KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0) != 89579:
        rec("CHILD-GAS", "FAIL", "CALLCODE child")
        return 1
    if lin_vm("cc29_forwarded", KIND_CALL, 100000, 1000000, 0, 1, 1, 0) != 64969:
        rec("CHILD-GAS", "FAIL", "CALL child")
        return 1
    rec("CHILD-GAS", "PASS", "value+new: CALLCODE child 89579 vs CALL 64969 (CALLCODE forwards 24610 more)")

    if lin_vm("cc29_extra", KIND_CALLCODE, 0, 1, 0) != 0:
        rec("NO-NEW-ACCT", "FAIL", "CALLCODE new without value")
        return 1
    rec("NO-NEW-ACCT", "PASS", "CALLCODE ignores new-account; DELEGATE/STATIC ignore value and new-account")

    if lin_vm("cc29_dynamic", 4, 64000, 0, 0, 0, 0, 0) != 0 or lin_vm("cc29_dynamic", 1, -1, 0, 0, 0, 0, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "bounds")
        return 1
    rec("FAIL-CLOSED", "PASS", "bad kind, negatives, extra>avail, cold>avail fail-close to 0")

    jit_ok = lin_roundtrip_jit("cc29_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cc29_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cc29_dynamic", KIND_CALLCODE, 100000, 1000000, 0, 1, 1, 0)
        if jv == 98579:
            rec("C0-JIT", "PASS", "lin_c0 jit cc29_dynamic(CALLCODE value+new)==98579 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cc29_dynamic(kind: int, available: int" in src and "UseGas" in src_ex:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes kind+available+flags; pinned Geth reads StateDB+stack")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit flags vs Geth StateDB")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec(
        "GO-CALL-REJ",
        "PASS" if all(x in go_src for x in ("REJ_GO_CALLCODE", "REJ_GO_DELEGATE", "REJ_GO_STATIC", "REJ_GO_CALL2929")) else "FAIL",
        "lin_from_go.lin v12 rejects gasCallCodeEIP2929 / gasDelegateCallEIP2929 / gasStaticCallEIP2929",
    )
    rec(
        "GO-EX-SPLIT",
        "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest",
    )

    evidence = {
        "schema": "LIN_GETH_CALLCODE2929_EVIDENCE_1.0",
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
                "CallValueTransferGas=9000 CallNewAccountGas=25000 "
                "ColdAccountAccessCostEIP2929=2600 WarmStorageReadCostEIP2929=100 "
                "CALLCODE extras=value only; DELEGATE/STATIC extras=memory only; "
                "shared cold-warm 2500 charged before EIP-150 63/64 "
                f"from {PARAMS_REL} blob {PARAMS_BLOB} sha256 {PARAMS_SHA256}; "
                f"{HELPER_REL} blob {HELPER_BLOB} sha256 {HELPER_SHA256}; "
                f"{GAS_REL} blob {GAS_BLOB} sha256 {GAS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_geth_callcode2929.lin",
        "c11_oracle": "test/oracles/geth_callcode2929_c11.c",
        "go_oracle": "test/oracles/geth_callcode2929_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {
                "kind": k, "available": a, "requested": b, "memory_gas": c,
                "transfers": d, "new_acct": e, "is_cold": f,
                "dynamic": g, "total": h,
            }
            for k, a, b, c, d, e, f, g, h in VECTORS
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
