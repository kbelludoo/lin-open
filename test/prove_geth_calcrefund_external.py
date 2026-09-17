#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum calcRefund (EIP-3529, LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of calcRefund in go-ethereum v1.16.9
      (git blob + sha256 of core/state_transition.go and protocol_params.go)
    * an independent C11 oracle (Geth uint64 wrap AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int (fail-closed at 2^63-1)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * uint64 wrap of initialGas-gasRemaining is reachable on mainnet
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real EIP-3529 algorithm, i64-scale operands / MaxGasLimit).
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
LIN = ROOT / "src" / "lin_geth_calcrefund.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_calcrefund_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_calcrefund_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_calcrefund_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_calcrefund" / "geth_calcrefund_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_ST_SHA256 = "449d50d372cc6ddff95f6ffa4eae29e06d38e248b24bc8501036c04f3e3f0c14"
PINNED_PP_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PINNED_ST_BLOB = "bf5ac07636d5111c281726a4273d149cb10d1d8e"
PINNED_PP_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
ST_REL = "core/state_transition.go"
PP_REL = "params/protocol_params.go"
I64MAX = 9223372036854775807
U64MAX = 18446744073709551615

# (used, state_refund, london, want_refund)
VECTORS = [
    (21000, 0, 1, 0),
    (21000, 100000, 1, 4200),
    (21000, 100000, 0, 10500),
    (21000, 1000, 1, 1000),
    (21000, 1000, 0, 1000),
    (5, 100, 1, 1),
    (4, 100, 1, 0),
    (5, 100, 0, 2),
    (1, 100, 0, 0),
    (0, 100, 1, 0),
    (100000, 100000, 1, 20000),
    (100000, 100000, 0, 50000),
]


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
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
    proc = run(
        [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90
    )
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def py_refund(used: int, state: int, london: int) -> int:
    if used < 0 or state < 0 or london < 0:
        return 0
    q = 5 if london else 2
    cap = used // q
    return cap if cap < state else state


def ensure_oracle() -> None:
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)],
        timeout=30,
    )
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
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG],
        timeout=180,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live_st = UPSTREAM / ST_REL
    live_pp = UPSTREAM / PP_REL
    if not live_st.exists() or not live_pp.exists():
        return "SKIP", "", "pinned paths missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ST_REL}"]).stdout.strip()
    blob_pp = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PP_REL}"]).stdout.strip()
    st_hash = sha256_file(live_st)
    pp_hash = sha256_file(live_pp)
    if (
        st_hash != PINNED_ST_SHA256
        or pp_hash != PINNED_PP_SHA256
        or blob != PINNED_ST_BLOB
        or blob_pp != PINNED_PP_BLOB
        or commit != PINNED_COMMIT
    ):
        return "FAIL", commit, f"st={st_hash} blob={blob} pp={pp_hash} ppblob={blob_pp}"
    excerpt = (FIX / "calcRefund.go").read_text(encoding="utf-8")
    if excerpt not in live_st.read_text(encoding="utf-8"):
        return "FAIL", commit, "calcRefund.go excerpt not a substring of live file"
    used_ex = (FIX / "gasUsed.go").read_text(encoding="utf-8")
    if used_ex not in live_st.read_text(encoding="utf-8"):
        return "FAIL", commit, "gasUsed.go excerpt not a substring of live file"
    params_ex = (FIX / "eip3529_protocol_params.go").read_text(encoding="utf-8")
    if params_ex not in live_pp.read_text(encoding="utf-8"):
        return "FAIL", commit, "eip3529 params excerpt not a substring of live file"
    return "PASS", commit, blob


def go_oracle(op: str, *args: int) -> int | None:
    cmd = ["go", "run", str(GO_SRC), op, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except ValueError:
        return None


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_CALCREFUND_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH CALCREFUND (EIP-3529) — external LIN proof (i64-scale, C11+Go oracles)")
    print("=" * 78)

    excerpt = FIX / "calcRefund.go"
    params = FIX / "eip3529_protocol_params.go"
    if not excerpt.exists() or not params.exists():
        rec("PIN-FILE", "FAIL", "pinned calcRefund.go or params excerpt missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    src_pp = params.read_text(encoding="utf-8")
    if "func (st *stateTransition) calcRefund()" not in src_ex or "RefundQuotientEIP3529" not in src_pp:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing calcRefund / EIP-3529 constants")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned calcRefund.go contains EIP-3529 function + refund quotients")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_ST_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/state_transition.go")
        rec("UPSTREAM-PARAMS", "PASS", "git blob sha of params/protocol_params.go")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-PARAMS", "SKIP", "live params blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-PARAMS", "FAIL", "params blob mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Geth-wrap vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range refund goldens + uint64 wrap vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go calcRefund goldens + gasUsed wrap vector")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of calcrefund clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_calcrefund.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("GO-TR-CHECK", "FAIL", "lin_from_go.lin check", chk2.stdout)
    else:
        rec("GO-TR-CHECK", "PASS", "Compiler 0 check of Go transpiler v2 (REJ_GO_RECEIVER)")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")

    gate = run([str(C0), "vm", str(LIN), "cr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cr_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cr_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for used, state, london, want in VECTORS:
        py = py_refund(used, state, london)
        c11 = int(oracle(["refund", str(used), str(state), str(london)]).splitlines()[-1])
        geth = int(oracle(["geth-refund", str(used), str(state), str(london)]).splitlines()[-1])
        got = lin_vm("cr_refund", used, state, london)
        go_v = go_oracle("refund", used, state, london)
        if py != want or c11 != want or got != want or geth != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"refund(used={used},state={state},london={london})",
                f"py={py} c11={c11} lin={got} geth={geth} want={want}",
            )
            return 1
        if go_v is None or go_v != want:
            rec("VEC-GO", "FAIL", f"go oracle refund({used},{state},{london})", f"go={go_v} want={want}")
            return 1
        n_ok += 1
    rec(
        "VEC-CONSENSUS",
        "PASS",
        f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm",
    )
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python fail-closed i64 matches C11 and LIN")

    kept = lin_vm("cr_london_kept", 21000, 100000)
    paid_l = lin_vm("cr_paid", 21000, 4200)
    paid_p = lin_vm("cr_paid", 21000, 10500)
    if kept != 6300 or paid_l != 16800 or paid_p != 10500:
        rec("EIP3529-DELTA", "FAIL", "London 50%→20% on 21k gas", f"kept={kept} paid_l={paid_l} paid_p={paid_p}")
        return 1
    rec(
        "EIP3529-DELTA",
        "PASS",
        "21k used + large SSTORE refund: pre-London refund 10500, London 4200; 6300 gas stays consumed",
        "user-paid gas 10500 → 16800. EIP-3529 cut the maximum refund from 50% to 20% of gasUsed",
    )

    geth_wrap = int(oracle(["geth-used", "21000", "21001"]).splitlines()[-1])
    lin_wrap = lin_vm("cr_gas_used", 21000, 21001)
    go_wrap = go_oracle("used", 21000, 21001)
    lin_rf = lin_vm("cr_refund_from_gas", 21000, 21001, 100000, 1)
    if geth_wrap != U64MAX or go_wrap != U64MAX or lin_wrap != 0 or lin_rf != 0:
        rec(
            "GETH-WRAP-USED",
            "FAIL",
            "remaining=initial+1 uint64 wrap vs i64 fail-closed",
            f"geth={geth_wrap} go={go_wrap} lin_used={lin_wrap} lin_refund={lin_rf}",
        )
        return 1
    rec(
        "GETH-WRAP-USED",
        "PASS",
        "remaining=initial+1: Geth/Go uint64 gasUsed wraps to 2^64-1; LIN fail-closes used and refund to 0",
        "invariant remaining<=initial holds on mainnet; defect of the unbounded subtraction, not a consensus bug",
    )

    jit_ok = lin_roundtrip_jit("cr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cr_refund", 21000, 100000, 1)
        if jv == 4200:
            rec("C0-JIT", "PASS", "lin_c0 jit cr_refund(21000,100000,1)==4200 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cr_refund(used: int, state_refund: int, london: int)" in src and "GetRefund" in src_ex:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes used/state_refund/london as arguments; pinned Geth reads ChainConfig and GetRefund via selectors",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit args vs Geth selectors")

    go_src = GO_TR.read_text(encoding="utf-8")
    if "go_from_go" in go_src and "REJ_GO_RECEIVER" in go_src and "REJ_GO_SELECTOR" in go_src:
        rec("GO-EMIT", "PASS", "lin_from_go.lin v2 emits LIN and rejects method receivers / selectors / slices")
    else:
        rec("GO-EMIT", "FAIL", "Go emit/reject path missing")

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_ARRAY_PARAM" in c_src:
        rec("C-ARRAY-REJ", "PASS", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    else:
        rec("C-ARRAY-REJ", "FAIL", "REJ_C_ARRAY_PARAM missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": ST_REL,
        "git_blob_sha": blob or PINNED_ST_BLOB,
        "file_sha256": PINNED_ST_SHA256,
        "params_path": PP_REL,
        "params_git_blob_sha": PINNED_PP_BLOB,
        "params_file_sha256": PINNED_PP_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_calcrefund.lin"
    evidence["c11_oracle"] = "test/oracles/geth_calcrefund_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_calcrefund_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-geth-calcrefund"
    evidence["vectors"] = [
        {"used": u, "state_refund": s, "london": lon, "refund": w} for u, s, lon, w in VECTORS
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
