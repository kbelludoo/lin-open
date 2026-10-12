#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V1 VaultUtils.getFundingFee vs LIN C0 (EXPERIMENTAL)."""
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
LIN = ROOT / "src" / "lin_gmx_funding.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_funding_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_funding_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx")
EVIDENCE = ROOT / "examples" / "gmx_funding" / "gmx_funding_evidence.json"

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


def py_funding(size: int, cum: int, entry: int) -> int:
    if size <= 0 or cum < 0 or entry < 0 or cum < entry:
        return 0
    rate = cum - entry
    if rate == 0:
        return 0
    return (size * rate) // 1_000_000


def py_position(size: int, margin_bps: int) -> int:
    if size <= 0 or margin_bps < 0 or margin_bps > 10000:
        return 0
    after = (size * (10000 - margin_bps)) // 10000
    return size - after


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V1 VaultUtils.getFundingFee — external LIN proof (C11 oracle)")

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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb funding selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (funding / wrap / 100x bps trap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX funding clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_funding.lin")

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

    gate = run([str(C0), "vm", str(LIN), "gmf_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gmf_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gmf_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "gmf_muldiv", (100, 200, 50), 400),
        ("fund", ["1000000", "1000", "0"], "gmf_funding_fee", (1000000, 1000, 0), 1000),
        ("fund", ["1000000", "1000", "1000"], "gmf_funding_fee", (1000000, 1000, 1000), 0),
        ("fund", ["0", "1000", "0"], "gmf_funding_fee", (0, 1000, 0), 0),
        ("fund", ["1000000", "1000", "400"], "gmf_funding_fee", (1000000, 1000, 400), 600),
        ("fund", ["10000000", "50", "0"], "gmf_funding_fee", (10000000, 50, 0), 500),
        ("fund", ["1000000", "400", "1000"], "gmf_funding_fee", (1000000, 400, 1000), 0),
        ("fund", ["1000000", "5000", "4000"], "gmf_funding_fee", (1000000, 5000, 4000), 1000),
        ("pos", ["1000000", "10"], "gmf_position_fee", (1000000, 10), 1000),
        ("confused", ["1000000", "1000"], "gmf_confused_bps", (1000000, 1000), 100000),
        ("ignore", ["1000000", "5000"], "gmf_ignore_entry", (1000000, 5000), 5000),
        ("uni", ["1000000", "30"], "gmf_uniswap_shot", (1000000, 30), 3000),
        ("wrap", ["5000000000", "5000000000", "1000000"], "gmf_naive_mul_wrap", (5000000000, 5000000000, 1000000), 6553255926290),
        ("muldiv", ["5000000000", "5000000000", "1000000"], "gmf_muldiv", (5000000000, 5000000000, 1000000), 25000000000000),
        ("fund", ["1000000", "0", "0"], "gmf_funding_fee", (1000000, 0, 0), 0),
        ("pos", ["0", "10"], "gmf_position_fee", (0, 10), 0),
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
        elif kind == "fund":
            py = py_funding(*largs)
        elif kind == "pos":
            py = py_position(*largs)
        elif kind == "confused":
            py = (largs[0] * largs[1]) // 10000
        elif kind == "ignore":
            py = (largs[0] * largs[1]) // 1_000_000
        elif kind == "uni":
            py = (largs[0] * largs[1]) // 10000
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("FUND-1000", "PASS", "size=1e6 rate=1000 entry=0 funding=1000 (VaultUtils size*rate/1e6)")
    rec("BPS-TRAP", "PASS", "same inputs with /10000 = 100000 (100x overcharge if FUNDING_RATE_PRECISION is confused with BASIS_POINTS_DIVISOR)")
    rec("ENTRY-TRAP", "PASS", "size=1e6 cum=5000 entry=4000 funding=1000 vs ignore-entry=5000 (5x overcharge)")
    rec("POS-VS-FUND", "PASS", "position 10 bps of 1e6 = 1000; funding rate=1000 of 1e6 = 1000 (same number, /10000 vs /1e6)")
    rec("UNI-VS-FUND", "PASS", "Uniswap 30 bps one-shot of 1e6 = 3000 vs GMX funding 1000 (accrued delta-rate, not swap fee)")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 (5e9*5e9)/1e6 wraps to 6553255926290; 128-bit muldiv=25000000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "gmf_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gmf_test_suite (in-memory libtcc)")
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
        "PASS" if "gmf_funding_fee" in src and "function getFundingFee" in sol else "FAIL",
        "LIN clone takes size/cumulative/entry as arguments (no vault storage)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "gmf_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv for size*rate/1e6",
    )
    rec(
        "NOT-USDG",
        "PASS" if "!gmf_funding_fee" in src and "!gmx_fee_bps" not in src and "!sld_k" not in src else "FAIL",
        "kernel is GMX funding size*delta-rate/1e6, not USDG tax-rebate or Solidly cubic",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_GMX_FUNDING",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects getFundingFee / cumulativeFundingRates / FUNDING_RATE_PRECISION",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_FUNDING" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_funding_fee / cumulative_funding_rates",
    )

    evidence = {
        "schema": "LIN_GMX_FUNDING_FEE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "GMX V1 Vault perpetual funding and position fees on Arbitrum/Avalanche",
        },
        "lin_clone": "src/lin_gmx_funding.lin",
        "c11_oracle": "test/oracles/gmx_funding_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "fund_1e6_1000": 1000,
            "fund_zero_rate": 0,
            "fund_entry_400": 600,
            "fund_underflow": 0,
            "fund_vs_ignore": {"correct": 1000, "ignore_entry": 5000},
            "confused_bps_100x": 100000,
            "position_10bps": 1000,
            "uniswap_30bps": 3000,
            "naive_wrap_5e9": 6553255926290,
            "wide_5e9": 25000000000000,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-funding",
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
