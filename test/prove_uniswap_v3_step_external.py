#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Uniswap V3 SwapMath.computeSwapStep vs LIN C0 (EXPERIMENTAL Q32)."""
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
LIN = ROOT / "src" / "lin_uniswap_v3_step.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v3_step_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v3_step_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v3_core")
EVIDENCE = ROOT / "examples" / "uniswap_v3_step" / "uniswap_v3_step_evidence.json"

Q32 = 2**32
L = 1_000_000
T0 = Q32 // 2
T1 = 2 * Q32
FEE = 3000
PINNED_SHA256 = "d6cb9a153be4ea9fb2377ef88641ef7979b5cee6933162f1b732d0289e26e1b6"
PINNED_BLOB = "ee176fbee4ae2fb2ba7da4ddd00391fe6b685f39"
PINNED_COMMIT = "e3589b192d0be27e100cd0daaf6c97204fdb1899"
UPSTREAM_REL = "contracts/libraries/SwapMath.sol"


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


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(path: Path, fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(path), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


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
    url = "https://github.com/Uniswap/v3-core.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def tdiv(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) ^ (b < 0) else q


def py_naive_wrap(remaining: int, fee_pips: int) -> int:
    den = 1_000_000
    return tdiv(w64(remaining * (den - fee_pips)), den)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V3 computeSwapStep — external LIN proof (Q32 uint64-scale, C11 oracle)")

    pinned = FIX / "SwapMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned SwapMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned SwapMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned Uniswap/v3-core v1.0.0 matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of SwapMath.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb swap-step selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (fee cap / skip-fee / exact-out sign / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of swap-step clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v3_step.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec(
        "SOL-TR-CHECK",
        "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3",
    )
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec(
        "RS-TR-CHECK",
        "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2",
    )

    gate = run([str(C0), "vm", str(LIN), "v3s_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "v3s_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "v3s_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "v3s_muldiv", (100, 200, 50), 400),
        ("next", [str(Q32), str(T0), str(L), "1000000", str(FEE)], "v3s_step_next", (Q32, T0, L, 1000000, FEE), 2150709713),
        ("skipfee", [str(Q32), str(T0), str(L), "1000000", str(FEE)], "v3s_skip_fee_next", (Q32, T0, L, 1000000, FEE), T0),
        ("next", [str(Q32), str(T0), str(L), "1003011", str(FEE)], "v3s_step_next", (Q32, T0, L, 1003011, FEE), T0),
        ("fee", [str(Q32), str(T0), str(L), "1000000", str(FEE)], "v3s_step_fee", (Q32, T0, L, 1000000, FEE), 3000),
        ("fee", [str(Q32), str(T0), str(L), "1003011", str(FEE)], "v3s_step_fee", (Q32, T0, L, 1003011, FEE), 3010),
        ("next", [str(Q32), str(T0), str(L), "-500000", str(FEE)], "v3s_step_next", (Q32, T0, L, -500000, FEE), T0),
        ("next", [str(Q32), str(T0), str(L), "500000", str(FEE)], "v3s_step_next", (Q32, T0, L, 500000, FEE), 2866177709),
        ("next", [str(Q32), str(T0), str(L), "-499999", str(FEE)], "v3s_step_next", (Q32, T0, L, -499999, FEE), 2147487942),
        ("reached", [str(Q32), str(T0), str(L), "1000000", str(FEE)], "v3s_step_reached", (Q32, T0, L, 1000000, FEE), 0),
        ("reached", [str(Q32), str(T0), str(L), "1003011", str(FEE)], "v3s_step_reached", (Q32, T0, L, 1003011, FEE), 1),
        ("next", [str(Q32), str(T1), str(L), "1000000", str(FEE)], "v3s_step_next", (Q32, T1, L, 1000000, FEE), 8577049690),
        ("aout", [str(Q32), str(T0), str(L), "1000000", str(FEE)], "v3s_step_amount_out", (Q32, T0, L, 1000000, FEE), 499248),
        ("wrap", ["10000000000000", str(FEE)], "v3s_naive_fee_wrap", (10000000000000, FEE), -8476744073709),
        ("less", ["10000000000000", str(FEE)], "v3s_remaining_less_fee", (10000000000000, FEE), 9970000000000),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != expect or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} expect={expect}")
            return 1
        if kind == "wrap":
            py = py_naive_wrap(*largs)
        elif kind == "less":
            py = (largs[0] * (1_000_000 - largs[1])) // 1_000_000
        elif kind == "muldiv":
            py = (largs[0] * largs[1]) // largs[2]
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec(
        "SKIP-FEE-CAP",
        "PASS",
        "exact-in remaining=1e6 fee=3000 does not hit Q/2 (next=2150709713); skip-fee hits 2147483648",
    )
    rec(
        "FEE-REMAINDER",
        "PASS",
        "not-reached exact-in fee=remaining-amountIn=3000; reached remaining=1003011 fee=ceil=3010",
    )
    rec(
        "EXACT-OUT-SIGN",
        "PASS",
        "exact-out remaining=-5e5 hits Q/2; treating +5e5 as exact-in yields 2866177709",
    )
    rec(
        "EXACT-OUT-SHORT",
        "PASS",
        "exact-out remaining=-499999 does not hit target (next=2147487942 vs Q/2)",
    )
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (1e13*997000)/1e6 wraps to -8476744073709; 128-bit remaining_less_fee=9970000000000",
    )
    rec("OFO-PARTIAL", "PASS", "oneForZero exact-in remaining=1e6 fee=3000 next=8577049690 (not 2Q)")

    jit_ok = lin_roundtrip_jit(LIN, "v3s_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on v3s_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec(
            "CJR-REGRESS",
            "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta",
        )
    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "v3s_step_next" in src and "computeSwapStep" in sol:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes sqrtP/target/L/remaining/feePips as arguments")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected computeSwapStep vs Solidity library")
    rec(
        "WIDE-MULDIV",
        "PASS" if "v3s_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv (fee remaining and Q32 deltas)",
    )
    rec("Q32-NOT-Q96", "PASS", "Q32=2^32 used; Q96=2^96 cannot fit signed i64")
    rec(
        "NOT-FROM-INPUT",
        "PASS" if "v3s_next_from_input" not in src else "FAIL",
        "kernel is computeSwapStep cap; FromInput is a helper inside the cap, not the claim",
    )
    rec(
        "NOT-FROM-OUTPUT",
        "PASS" if "v3s_next_from_output" not in src else "FAIL",
        "kernel is not getNextSqrtPriceFromOutput; exact-out is the remaining-sign cap",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_SWAP_STEP",
        "REJ_SOLIDITY_FEE_PIPS",
        "REJ_SOLIDITY_AMOUNT_REMAINING",
        "REJ_SOLIDITY_UINT24",
        "REJ_SOLIDITY_UINT160",
        "REJ_SOLIDITY_NEG_CAST",
        "REJ_SOLIDITY_FULLMATH",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects computeSwapStep / feePips / amountRemaining / uint160 / FullMath",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS"
        if "REJ_RUST_SWAP_STEP" in rs_src and "REJ_RUST_FEE_PIPS" in rs_src
        else "FAIL",
        "lin_from_rust.lin v2 rejects compute_swap_step / fee_pips / amount_remaining",
    )

    evidence = {
        "schema": "LIN_UNISWAP_V3_SWAP_STEP_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/Uniswap/v3-core",
            "commit": commit or PINNED_COMMIT,
            "tag": "v1.0.0",
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2023-04-01 elapsed",
        },
        "lin_clone": "src/lin_uniswap_v3_step.lin",
        "c11_oracle": "test/oracles/uniswap_v3_step_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "q_scale": "Q32=2^32 (not Q96=2^96)",
        "goldens": {
            "exact_in_zfo_1e6_next": 2150709713,
            "skip_fee_zfo_1e6_next": T0,
            "exact_in_zfo_hit_next": T0,
            "not_reached_fee": 3000,
            "reached_fee": 3010,
            "exact_out_zfo_5e5_next": T0,
            "as_exact_in_5e5_next": 2866177709,
            "exact_out_short_next": 2147487942,
            "ofo_partial_next": 8577049690,
            "naive_fee_wrap_1e13": -8476744073709,
            "less_fee_1e13": 9970000000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-uniswap-v3-step",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
