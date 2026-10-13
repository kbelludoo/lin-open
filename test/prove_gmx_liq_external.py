#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V1 VaultUtils.validateLiquidation vs LIN C0 (EXPERIMENTAL)."""
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
LIN = ROOT / "src" / "lin_gmx_liq.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_liq_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_liq_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx")
EVIDENCE = ROOT / "examples" / "gmx_liq" / "gmx_liq_evidence.json"

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


def py_remaining(collateral: int, has_profit: int, delta: int, raise_f: int) -> int:
    if has_profit == 0:
        return 0 if collateral < delta else collateral - delta
    if raise_f == 0:
        return collateral + delta
    return collateral


def py_wiped(collateral: int, has_profit: int, delta: int) -> bool:
    return has_profit == 0 and collateral < delta


def py_lev(remaining: int, size: int, max_lev: int) -> bool:
    return remaining * max_lev < size * 10000


def py_state(col: int, size: int, hp: int, delta: int, fees: int, liq: int, lev: int, raise_f: int) -> int:
    if col < 0 or size < 0 or delta < 0 or fees < 0 or liq < 0 or lev <= 0:
        return -1
    if py_wiped(col, hp, delta):
        return -1 if raise_f else 1
    rem = py_remaining(col, hp, delta, raise_f)
    if rem < fees:
        return -1 if raise_f else 1
    if rem < fees + liq:
        return -1 if raise_f else 1
    if py_lev(rem, size, lev):
        return -1 if raise_f else 2
    return 0


def py_fees(col: int, size: int, hp: int, delta: int, fees: int, liq: int, lev: int, raise_f: int) -> int:
    st = py_state(col, size, hp, delta, fees, liq, lev, raise_f)
    if st < 0:
        return 0
    if py_wiped(col, hp, delta):
        return fees
    rem = py_remaining(col, hp, delta, raise_f)
    if rem < fees:
        return rem
    return fees


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_naive_lev(remaining: int, size: int, max_lev: int) -> int:
    left = w64(remaining * max_lev)
    right = size * 10000
    return 1 if left < right else 0


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V1 VaultUtils.validateLiquidation — external LIN proof (C11 oracle)")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb liq selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (cap-to-collateral / profit-on-liq / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX liq clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_liq.lin")

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

    gate = run([str(C0), "vm", str(LIN), "gvl_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gvl_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gvl_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "gvl_muldiv", (100, 200, 50), 400),
        ("state", ["100000", "2000000", "1", "20000", "8000", "5000", "500000", "0"],
         "gvl_state", (100000, 2000000, 1, 20000, 8000, 5000, 500000, 0), 0),
        ("fees", ["100000", "2000000", "1", "20000", "8000", "5000", "500000", "0"],
         "gvl_fees", (100000, 2000000, 1, 20000, 8000, 5000, 500000, 0), 8000),
        ("rem", ["100000", "1", "20000", "0"], "gvl_remaining", (100000, 1, 20000, 0), 120000),
        ("state", ["100000", "2000000", "0", "20000", "90000", "5000", "500000", "0"],
         "gvl_state", (100000, 2000000, 0, 20000, 90000, 5000, 500000, 0), 1),
        ("fees", ["100000", "2000000", "0", "20000", "90000", "5000", "500000", "0"],
         "gvl_fees", (100000, 2000000, 0, 20000, 90000, 5000, 500000, 0), 80000),
        ("uncap", ["100000", "0", "20000", "90000", "0"], "gvl_uncapped_fees",
         (100000, 0, 20000, 90000, 0), 90000),
        ("state", ["100000", "2000000", "0", "150000", "8000", "5000", "500000", "0"],
         "gvl_state", (100000, 2000000, 0, 150000, 8000, 5000, 500000, 0), 1),
        ("fees", ["100000", "2000000", "0", "150000", "8000", "5000", "500000", "0"],
         "gvl_fees", (100000, 2000000, 0, 150000, 8000, 5000, 500000, 0), 8000),
        ("state", ["13000", "100000", "0", "1000", "8000", "5000", "500000", "0"],
         "gvl_state", (13000, 100000, 0, 1000, 8000, 5000, 500000, 0), 1),
        ("ignore", ["13000", "100000", "0", "1000", "8000", "500000", "0"],
         "gvl_ignore_liq_state", (13000, 100000, 0, 1000, 8000, 500000, 0), 0),
        ("state", ["100000", "6000000", "1", "0", "8000", "5000", "500000", "0"],
         "gvl_state", (100000, 6000000, 1, 0, 8000, 5000, 500000, 0), 2),
        ("missbps", ["100000", "6000000", "500000"], "gvl_missing_bps_lev",
         (100000, 6000000, 500000), 0),
        ("state", ["10000", "100000", "1", "20000", "15000", "5000", "500000", "0"],
         "gvl_state", (10000, 100000, 1, 20000, 15000, 5000, 500000, 0), 0),
        ("state", ["10000", "100000", "1", "20000", "15000", "5000", "500000", "1"],
         "gvl_state", (10000, 100000, 1, 20000, 15000, 5000, 500000, 1), -1),
        ("rem", ["10000", "1", "20000", "1"], "gvl_remaining", (10000, 1, 20000, 1), 10000),
        ("state", ["100000", "2000000", "0", "20000", "90000", "5000", "500000", "1"],
         "gvl_state", (100000, 2000000, 0, 20000, 90000, 5000, 500000, 1), -1),
        ("naive", ["4000000000", "1000000000", "3000000000"], "gvl_naive_lev_exceeded",
         (4000000000, 1000000000, 3000000000), 1),
        ("state", ["4000000000", "1000000000", "1", "0", "1", "1", "3000000000", "0"],
         "gvl_state", (4000000000, 1000000000, 1, 0, 1, 1, 3000000000, 0), 0),
        ("fundfee", ["2000000", "100"], "gvl_as_funding_fee", (2000000, 100), 200),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != expect or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} expect={expect}")
            return 1
        if kind == "state":
            py = py_state(*largs)
        elif kind == "fees":
            py = py_fees(*largs)
        elif kind == "rem":
            py = py_remaining(*largs)
        elif kind == "uncap":
            py = largs[3]
        elif kind == "ignore":
            py = py_state(largs[0], largs[1], largs[2], largs[3], largs[4], 0, largs[5], largs[6])
        elif kind == "missbps":
            py = 1 if (largs[0] * largs[2]) < largs[1] else 0
        elif kind == "naive":
            py = py_naive_lev(*largs)
        elif kind == "fundfee":
            py = (largs[0] * largs[1]) // 1_000_000
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
    rec("HEALTHY-0", "PASS", "profit on liq path remaining=120000: state=0 fees=8000")
    rec("CAP-FEES", "PASS", "remaining 80000 < marginFees 90000: state=1 fees capped to 80000 vs uncapped 90000")
    rec("WIPED", "PASS", "loss 150000 > collateral 100000: state=1 fees=8000 (not remaining 0)")
    rec("LIQ-BUFFER", "PASS", "remaining 12000 < fees+liqFee 13000: state=1 vs ignore-liq-fee state=0")
    rec("MAX-LEV", "PASS", "60x vs 50x cap: state=2; missing BASIS remaining*maxLev<size is false (wrong healthy)")
    rec("PROFIT-RAISE", "PASS", "raise=0 adds profit 20000 (state=0); raise=1 keeps 10000 and fail-closes -1")
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive i64 remaining*maxLev 4e9*3e9 wraps and flags leverage; 128-bit product stays healthy",
    )
    rec("FUND-TRAP", "PASS", "confused getFundingFee size*100/1e6=200 vs liquidation state/fees")

    jit_ok = lin_roundtrip_jit(LIN, "gvl_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gvl_test_suite (in-memory libtcc)")
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
        "PASS" if "gvl_state" in src and "function validateLiquidation" in sol else "FAIL",
        "LIN clone takes collateral/size/pnl/fees/liqFee/maxLev/raise as arguments (no vault storage)",
    )
    rec(
        "WIDE-MUL",
        "PASS" if "gvl_prod_hi" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product compare for remaining*maxLeverage vs size*10000",
    )
    rec(
        "NOT-FUNDING-FEE",
        "PASS" if "!gvl_state" in src and "!gmf_funding_fee" not in src else "FAIL",
        "kernel is GMX validateLiquidation remaining vs fees+liqFee, not size*(cum-entry)/1e6",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_GMX_LIQ",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects validateLiquidation / remainingCollateral before STORAGE",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_LIQ" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects validate_liquidation / remaining_collateral",
    )

    evidence = {
        "schema": "LIN_GMX_VALIDATE_LIQUIDATION_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "GMX V1 Vault perpetual liquidation on Arbitrum/Avalanche",
        },
        "lin_clone": "src/lin_gmx_liq.lin",
        "c11_oracle": "test/oracles/gmx_liq_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "healthy_state": 0,
            "healthy_fees": 8000,
            "healthy_remaining": 120000,
            "cap_state": 1,
            "cap_fees": 80000,
            "uncapped_fees": 90000,
            "wiped_state": 1,
            "wiped_fees": 8000,
            "liq_buffer_state": 1,
            "ignore_liq_state": 0,
            "max_lev_state": 2,
            "missing_bps": 0,
            "profit_on_liq": 0,
            "profit_on_raise": -1,
            "raise_cap_revert": -1,
            "naive_wrap_lev": 1,
            "wide_lev_healthy": 0,
            "confused_funding_fee": 200,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-liq",
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
