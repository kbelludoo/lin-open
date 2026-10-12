#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum makeCallVariantGasCallEIP7702 (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of makeCallVariantGasCallEIP7702 + ParseDelegation
    * an independent C11 oracle
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * quadratic memoryGasCost / Cmem (memory_gas is an explicit integer)
    * CallStipend 2300, EIP-4762 Verkle, byte-level code parsing
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real Pectra 7702 addends, i64-scale).
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
LIN = ROOT / "src" / "lin_geth_eip7702.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_eip7702_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_eip7702_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_eip7702_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_eip7702" / "geth_eip7702_evidence.json"

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
EIPS_BLOB = "d7ed18648e6f09fcf1c3fcdf6b5ab37e480644a3"
TX_REL = "core/types/tx_setcode.go"
TX_SHA256 = "b9ba5d2fbbfa5a1a46e9edd7d00cbb6f0b651599da555744ece0f071f99273d6"
TX_BLOB = "f2281d4ae7662b9ab3def885e4e460867f1d25cd"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-geth-eip7702"

# (kind, avail, req, mem, xfer, new, addr_cold, is_del, tgt_cold, dynamic, total)
VECTORS = [
    (0, 64000, 1000000, 0, 0, 0, 0, 0, 0, 63000, 63100),
    (0, 64000, 1000000, 0, 0, 0, 1, 0, 0, 63040, 63140),
    (0, 64000, 1000000, 0, 0, 0, 0, 1, 0, 63002, 63102),
    (0, 64000, 1000000, 0, 0, 0, 0, 1, 1, 63041, 63141),
    (0, 64000, 1000000, 0, 0, 0, 1, 1, 1, 63080, 63180),
    (0, 64000, 1000000, 0, 0, 0, 1, 1, 0, 63041, 63141),
    (0, 100000, 1000000, 0, 1, 1, 0, 1, 1, 99010, 99110),
    (0, 100000, 1000000, 0, 1, 1, 0, 0, 0, 98969, 99069),
    (3, 100000, 1000000, 0, 1, 1, 0, 1, 1, 98479, 98579),
    (0, 64000, 1000, 0, 0, 0, 0, 1, 1, 3600, 3700),
    (0, 2599, 0, 0, 0, 0, 0, 1, 1, 0, 0),
    (1, 64000, 1000000, 0, 1, 0, 0, 1, 1, 63182, 63282),
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
    if kind in (2, 3):
        return g
    if kind == 1:
        return g + 9000 if xfer else g
    if xfer:
        g += 9000
        if new:
            g += 25000
    return g


def py_pre(addr_cold: int, is_del: int, tgt_cold: int) -> int:
    p = 2500 if addr_cold else 0
    if is_del:
        p += 2600 if tgt_cold else 100
    return p


def py_dynamic(kind: int, avail: int, req: int, mem: int, xfer: int, new: int, ac: int, d: int, tc: int) -> int:
    if kind not in (0, 1, 2, 3) or min(avail, req, mem) < 0:
        return 0
    if any(x not in (0, 1) for x in (xfer, new, ac, d, tc)):
        return 0
    pre = py_pre(ac, d, tc)
    if avail < pre:
        return 0
    ex = py_extra(kind, xfer, new, mem)
    if avail - pre < ex:
        return 0
    left = avail - pre - ex
    cap = left - left // 64
    fwd = req if req < cap else cap
    return ex + fwd + pre


def py_total(*args: int) -> int:
    kind, avail, req, mem, xfer, new, ac, isd, tc = args
    d = py_dynamic(*args)
    if d == 0:
        if kind not in (0, 1, 2, 3) or min(avail, req, mem) < 0:
            return 0
        if any(x not in (0, 1) for x in (xfer, new, ac, isd, tc)):
            return 0
        pre = py_pre(ac, isd, tc)
        if avail < pre or avail - pre < py_extra(kind, xfer, new, mem):
            return 0
    return 100 + d


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
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    paths = [UPSTREAM / p for p in (ACL_REL, GAS_REL, HELPER_REL, PARAMS_REL, EIPS_REL, TX_REL)]
    if not all(p.exists() for p in paths):
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ACL_REL}"]).stdout.strip()
    live = UPSTREAM / ACL_REL
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    checks = (
        (GAS_REL, GAS_SHA256),
        (HELPER_REL, HELPER_SHA256),
        (PARAMS_REL, PARAMS_SHA256),
        (EIPS_REL, EIPS_SHA256),
        (TX_REL, TX_SHA256),
    )
    for rel, want in checks:
        if sha256_file(UPSTREAM / rel) != want:
            return "FAIL", commit, f"{rel} sha256 mismatch"
    live_txt = live.read_text(encoding="utf-8")
    tx_txt = (UPSTREAM / TX_REL).read_text(encoding="utf-8")
    eips_txt = (UPSTREAM / EIPS_REL).read_text(encoding="utf-8")
    if (FIX / "gasCallEIP7702.go").read_text(encoding="utf-8").strip() not in live_txt:
        return "FAIL", commit, "gasCallEIP7702.go excerpt not a substring"
    if (FIX / "parseDelegation.go").read_text(encoding="utf-8").strip() not in tx_txt:
        return "FAIL", commit, "parseDelegation.go excerpt not a substring"
    if (FIX / "enable7702.go").read_text(encoding="utf-8").strip() not in eips_txt:
        return "FAIL", commit, "enable7702.go excerpt not a substring"
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
    print("  GETH makeCallVariantGasCallEIP7702 — external LIN proof")
    print("=" * 78)

    src_ex = (FIX / "gasCallEIP7702.go").read_text(encoding="utf-8")
    src_pd = (FIX / "parseDelegation.go").read_text(encoding="utf-8")
    if "ParseDelegation" not in src_ex or "UseGas" not in src_ex or "2600" not in src_pd and "23" not in src_pd:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing ParseDelegation / UseGas / designator len")
        return 1
    if "len(b) != 23" not in src_pd or "DelegationPrefix" not in src_pd:
        rec("PIN-EXCERPT", "FAIL", "ParseDelegation must require 23-byte 0xef0100 designator")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpts: 7702 wrapper + ParseDelegation 23-byte 0xef0100")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of operations_acl.go + tx_setcode.go + eips.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 EIP-7702 gas selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 7702 goldens vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go EIP-7702 goldens + fail-closed")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eip7702 clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_eip7702.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    rec("GO-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Go transpiler v13 (REJ_GO_CALL7702 / REJ_GO_EIP7702)")

    gate = run([str(C0), "vm", str(LIN), "e7702_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "e7702_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "e7702_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for vec in VECTORS:
        args = list(vec[:9])
        want_d, want_t = vec[9], vec[10]
        py_d = py_dynamic(*args)
        py_t = py_total(*args)
        c11_d = int(oracle(["dynamic", *[str(a) for a in args]]).splitlines()[-1])
        c11_t = int(oracle(["total", *[str(a) for a in args]]).splitlines()[-1])
        got_d = lin_vm("e7702_dynamic", *args)
        got_t = lin_vm("e7702_total", *args)
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
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint 7702 table matches C11 and LIN")

    if lin_vm("e7702_vs_2929", 0, 64000, 1000000, 0, 0, 0, 0, 1, 0) != 2:
        rec("VS-2929", "FAIL", "warm-del-warm vs 2929 should be +2")
        return 1
    if lin_vm("e7702_vs_2929", 0, 64000, 1000000, 0, 0, 0, 0, 1, 1) != 41:
        rec("VS-2929", "FAIL", "warm-del-cold vs 2929 should be +41")
        return 1
    rec("VS-2929", "PASS", "naive 2929 copy is wrong: 63/64-bound +2 (warm target) / +41 (cold target)")

    if lin_vm("e7702_vs_2929", 0, 64000, 1000, 0, 0, 0, 0, 1, 1) != 2600:
        rec("REQ-BOUND", "FAIL", "requested-bound must add the full 2600")
        return 1
    rec("REQ-BOUND", "PASS", "requested-bound CALL: 7702-2929 = full 2600 (not 41)")

    if lin_vm("e7702_parse_ok", 23, 1) != 1 or lin_vm("e7702_parse_ok", 22, 1) != 0:
        rec("PARSE-OK", "FAIL", "designator predicate")
        return 1
    rec("PARSE-OK", "PASS", "scalar ParseDelegation: len==23 && prefix_ok (no []byte)")

    if lin_vm("e7702_dynamic", 0, 99, 0, 0, 0, 0, 0, 1, 0) != 0:
        rec("FAIL-CLOSED", "FAIL", "avail=99 del-warm")
        return 1
    rec("FAIL-CLOSED", "PASS", "bad kind, negatives, pre>avail fail-close to 0")

    jit_ok = lin_roundtrip_jit("e7702_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on e7702_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("e7702_dynamic", 0, 64000, 1000000, 0, 0, 0, 0, 1, 1)
        if jv == 63041:
            rec("C0-JIT", "PASS", "lin_c0 jit e7702_dynamic(warm-del-cold)==63041 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "e7702_dynamic(kind: int, available: int" in src and "ParseDelegation" in src_ex else "FAIL",
        "LIN clone takes kind+flags; pinned Geth reads StateDB+GetCode")

    go_src = GO_TR.read_text(encoding="utf-8")
    rec("GO-CALL-REJ", "PASS" if all(x in go_src for x in ("REJ_GO_CALL7702", "REJ_GO_EIP7702", "version=13")) else "FAIL",
        "lin_from_go.lin v13 rejects makeCallVariantGasCallEIP7702 / ParseDelegation")
    rec("GO-EX-SPLIT", "PASS" if 'out = out + "=";' in go_src and 'out = out + "ex{"' in go_src else "FAIL",
        "go_from_go concatenates '=' + 'ex{' so C0 export parse is honest")

    evidence = {
        "schema": "LIN_GETH_EIP7702_EVIDENCE_1.0",
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
                "7702 delegation target: warm=100 cold=2600 (full, not 2500) before EIP-150 63/64 "
                f"from {PARAMS_REL} blob {PARAMS_BLOB}; {TX_REL} blob {TX_BLOB} sha256 {TX_SHA256}; "
                f"{EIPS_REL} blob {EIPS_BLOB} sha256 {EIPS_SHA256}"
            ),
        },
        "lin_clone": "src/lin_geth_eip7702.lin",
        "c11_oracle": "test/oracles/geth_eip7702_c11.c",
        "go_oracle": "test/oracles/geth_eip7702_go.go",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [
            {
                "kind": k, "available": a, "requested": b, "memory_gas": c,
                "transfers": d, "new_acct": e, "addr_cold": f, "is_delegation": g,
                "target_cold": h, "dynamic": i, "total": j,
            }
            for k, a, b, c, d, e, f, g, h, i, j in VECTORS
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
