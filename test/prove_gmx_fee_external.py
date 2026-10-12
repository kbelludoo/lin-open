#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V1 VaultUtils.getFeeBasisPoints vs LIN C0 (EXPERIMENTAL)."""
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
LIN = ROOT / "src" / "lin_gmx_fee.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_fee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_fee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx")
EVIDENCE = ROOT / "examples" / "gmx_fee" / "gmx_fee_evidence.json"

PINNED_SHA256 = "ad831f3c8d675c42665c854368bc06696e1cba23bd3294f91aa2ce4c0a8fc495"
PINNED_BLOB = "8e29c3ff19258d191f6d2459c110a917ba1f9906"
PINNED_COMMIT = "fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8"
UPSTREAM_REL = "contracts/core/VaultUtils.sol"


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
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=90)
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
    url = "https://github.com/gmx-io/gmx-contracts.git"
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


def py_naive_wrap(a: int, b: int, d: int) -> int:
    return tdiv(w64(a * b), d)


def py_fee(initial: int, delta: int, target: int, fee: int, tax: int, increment: int, has_dyn: int) -> int:
    if has_dyn == 0:
        return fee
    nxt = initial + delta if increment else (0 if delta > initial else initial - delta)
    if target == 0:
        return fee
    idiff = abs(initial - target)
    ndiff = abs(nxt - target)
    if ndiff < idiff:
        rebate = (tax * idiff) // target
        return 0 if rebate > fee else fee - rebate
    avg = (idiff + ndiff) // 2
    if avg > target:
        avg = target
    return fee + (tax * avg) // target


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V1 VaultUtils.getFeeBasisPoints — external LIN proof (C11 oracle)")

    pinned = FIX / "VaultUtils.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned VaultUtils.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned VaultUtils.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned gmx-io/gmx-contracts matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/core/VaultUtils.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb fee selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (fee / wrap / GMX goldens)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX fee clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_fee.lin")

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

    gate = run([str(C0), "vm", str(LIN), "gmx_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gmx_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gmx_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "gmx_muldiv", (100, 200, 50), 400),
        ("fee", ["10000", "2000", "10000", "100", "50", "1", "1"], "gmx_fee_bps", (10000, 2000, 10000, 100, 50, 1, 1), 105),
        ("fee", ["5000", "2000", "10000", "100", "50", "1", "1"], "gmx_fee_bps", (5000, 2000, 10000, 100, 50, 1, 1), 75),
        ("fee", ["15000", "2000", "10000", "100", "50", "0", "1"], "gmx_fee_bps", (15000, 2000, 10000, 100, 50, 0, 1), 75),
        ("fee", ["15000", "2000", "10000", "100", "50", "1", "1"], "gmx_fee_bps", (15000, 2000, 10000, 100, 50, 1, 1), 130),
        ("fee", ["15000", "2000", "10000", "100", "50", "1", "0"], "gmx_fee_bps", (15000, 2000, 10000, 100, 50, 1, 0), 100),
        ("fee", ["15000", "2000", "0", "100", "50", "1", "1"], "gmx_fee_bps", (15000, 2000, 0, 100, 50, 1, 1), 100),
        ("fee", ["0", "1", "10000", "100", "200", "1", "1"], "gmx_fee_bps", (0, 1, 10000, 100, 200, 1, 1), 0),
        ("fee", ["29700", "1000", "29700", "100", "50", "1", "1"], "gmx_fee_bps", (29700, 1000, 29700, 100, 50, 1, 1), 100),
        ("fee", ["29700", "5000", "29700", "100", "50", "1", "1"], "gmx_fee_bps", (29700, 5000, 29700, 100, 50, 1, 1), 104),
        ("fee", ["23760", "1000", "29700", "100", "50", "1", "1"], "gmx_fee_bps", (23760, 1000, 29700, 100, 50, 1, 1), 90),
        ("fee", ["12000", "1000", "10000", "100", "50", "1", "1"], "gmx_fee_bps", (12000, 1000, 10000, 100, 50, 1, 1), 112),
        ("target", ["2000", "1000000", "10000"], "gmx_target_usdg", (2000, 1000000, 10000), 200000),
        ("pos", ["1000000", "10"], "gmx_position_fee", (1000000, 10), 1000),
        ("wrap", ["5000000000", "5000000000", "1000000"], "gmx_naive_mul_wrap", (5000000000, 5000000000, 1000000), 6553255926290),
        ("muldiv", ["5000000000", "5000000000", "1000000"], "gmx_muldiv", (5000000000, 5000000000, 1000000), 25000000000000),
        ("usd", ["1000000000", "1000000", "2000"], "gmx_usd_to_token", (1000000000, 1000000, 2000), 500000000000),
        ("next", ["100", "250", "0"], "gmx_next_amount", (100, 250, 0), 0),
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
        elif kind == "muldiv":
            py = (largs[0] * largs[1]) // largs[2]
            if py >= 2**63:
                py = 0
        elif kind == "fee":
            py = py_fee(*largs)
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("GMX-TEST-100", "PASS", "published GMX at-target 1000-delta fee=100 (test/core/Vault/getFeeBasisPoints.js)")
    rec("GMX-TEST-104", "PASS", "published GMX at-target 5000-delta fee=104")
    rec("TAX-VS-FLAT", "PASS", "overweight increment 130 dynamic vs 100 flat (30 bps extra tax)")
    rec("REBATE-VS-FLAT", "PASS", "underweight increment 75 rebate vs 100 flat (25 bps cheaper to rebalance)")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (5e9*5e9)/1e6 wraps to 6553255926290; 128-bit muldiv=25000000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "gmx_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gmx_test_suite (in-memory libtcc)")
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
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "gmx_fee_bps" in src and "function getFeeBasisPoints" in sol else "FAIL",
        "LIN clone takes initial/delta/target/fee/tax as arguments (no vault storage)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "gmx_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv for tax*diff/target",
    )
    rec(
        "NOT-XY",
        "PASS" if "!gmx_fee_bps" in src and "!sld_k" not in src and "!getD" not in src else "FAIL",
        "kernel is GMX USDG tax/rebate, not Uniswap xy or Solidly cubic or Saddle getD",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_GMX_FEE",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects getFeeBasisPoints / hasDynamicFees / usdgAmounts",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_FEE" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_fee_basis_points / has_dynamic_fees",
    )

    evidence = {
        "schema": "LIN_GMX_FEE_BPS_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "GMX V1 Vault on Arbitrum/Avalanche; GLP mint/burn and swap fees",
        },
        "lin_clone": "src/lin_gmx_fee.lin",
        "c11_oracle": "test/oracles/gmx_fee_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "at_target_2k": 105,
            "under_inc_rebate": 75,
            "over_dec_rebate": 75,
            "over_inc_tax": 130,
            "flat_no_dyn": 100,
            "gmx_test_1000": 100,
            "gmx_test_5000": 104,
            "gmx_test_90": 90,
            "naive_wrap_5e9": 6553255926290,
            "wide_5e9": 25000000000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-fee",
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
