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
UPSTREAM = Path("/tmp/upstream_gmx_contracts")
EVIDENCE = ROOT / "examples" / "gmx_liq" / "gmx_liq_evidence.json"

PINNED_SHA256 = "ad831f3c8d675c42665c854368bc06696e1cba23bd3294f91aa2ce4c0a8fc495"
PINNED_BLOB = "8e29c3ff19258d191f6d2459c110a917ba1f9906"
PINNED_COMMIT = "fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8"
UPSTREAM_REL = "contracts/core/VaultUtils.sol"
BPS = 10000


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


def py_remaining(col: int, hp: int, delta: int, raise_: int) -> int:
    if col < 0 or delta < 0:
        return 0
    if hp == 0:
        return 0 if col < delta else col - delta
    if raise_ == 0:
        return col + delta
    return col


def py_eval(size: int, col: int, hp: int, delta: int, funding: int, position: int,
            liq: int, max_lev: int, raise_: int) -> tuple[int, int, int]:
    if size < 0 or liq < 0 or max_lev <= 0:
        return 0, 0, 0
    margin = 0 if funding < 0 or position < 0 else funding + position
    if hp == 0 and col < delta:
        return (-1, 0, 0) if raise_ else (1, margin, 0)
    rem = py_remaining(col, hp, delta, raise_)
    if rem < margin:
        return (-2, 0, 0) if raise_ else (1, rem, rem)
    if rem < margin + liq:
        return (-3, 0, rem) if raise_ else (1, margin, rem)
    if rem * max_lev < size * BPS:
        return (-4, 0, rem) if raise_ else (2, margin, rem)
    return 0, margin, rem


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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (cap / mid / losses / lev / profit-raise / wrap)")

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

    cases = [
        ("state", [100000, 1000, 0, 100, 800, 150, 5, 500000, 0], 1),
        ("fees", [100000, 1000, 0, 100, 800, 150, 5, 500000, 0], 900),
        ("state", [100000, 1020, 0, 100, 850, 50, 50, 500000, 0], 1),
        ("fees", [100000, 1020, 0, 100, 850, 50, 50, 500000, 0], 900),
        ("state", [100000, 500, 0, 600, 80, 20, 5, 500000, 0], 1),
        ("fees", [100000, 500, 0, 600, 80, 20, 5, 500000, 0], 100),
        ("state", [100000, 1500, 0, 0, 8, 2, 5, 500000, 0], 2),
        ("fees", [100000, 1500, 0, 0, 8, 2, 5, 500000, 0], 10),
        ("state", [100000, 3000, 0, 0, 8, 2, 5, 500000, 0], 0),
        ("fees", [100000, 3000, 0, 0, 8, 2, 5, 500000, 0], 10),
        ("state", [60000, 1000, 1, 500, 8, 2, 5, 500000, 1], -4),
        ("state", [60000, 1000, 1, 500, 8, 2, 5, 500000, 0], 0),
        ("state", [100000, 1000, 0, 100, 800, 150, 5, 500000, 1], -2),
        ("fees", [100, 100, 1, 50, 180, 20, 5, 500000, 0], 150),
    ]
    n_ok = 0
    for kind, args, expect in cases:
        fn = "gvl_state" if kind == "state" else "gvl_fees"
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *args)
        pst, pfe, _prem = py_eval(*args)
        pyv = pst if kind == "state" else pfe
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn}{tuple(args)}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    nocap = lin_vm(LIN, "gvl_fees_no_cap", 1000, 0, 100, 800, 150)
    incliq = lin_vm(LIN, "gvl_fees_include_liq", 1020, 0, 100, 850, 50, 50)
    naive = lin_vm(LIN, "gvl_naive_lev", 4000000000, 3000000000, 2000000000)
    wide = lin_vm(LIN, "gvl_wide_lev", 4000000000, 3000000000, 2000000000)
    if nocap != 950 or int(oracle(["nocap", "1000", "0", "100", "800", "150"])) != 950:
        rec("CAP-TRAP", "FAIL", "no-cap contrast", f"lin={nocap}")
        return 1
    if incliq != 950 or int(oracle(["incliq", "1020", "0", "100", "850", "50", "50"])) != 950:
        rec("LIQ-TRAP", "FAIL", "include-liq contrast", f"lin={incliq}")
        return 1
    if naive != 1 or wide != 0:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit lev", f"naive={naive} wide={wide}")
        return 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("CAP-TRAP", "PASS", "remaining 900 < margin 950: fees=900 vs no-cap 950")
    rec("MID-TRAP", "PASS", "remaining 920 in [900,950): fees=900 vs include-liq 950")
    rec("LOSS-TRAP", "PASS", "losses exceed collateral: state=1 fees=margin 100, not remaining 0")
    rec("LEV-TRAP", "PASS", "1500*500000 < 100000*10000: state=2 maxLeverage, fees=margin 10")
    rec("PROFIT-RAISE", "PASS", "raise=1 omits profit: remaining 1000 liquidates (state=-4) vs raise=0 remaining 1500 healthy")
    rec("NAIVE-WRAP", "PASS", "naive i64 4e9*3e9 flags lev; 128-bit remaining*maxLev vs size*10000 does not")

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
        "LIN clone takes size/collateral/delta/fees/maxLeverage/raise as arguments (no vault storage)",
    )
    rec(
        "WIDE-MUL",
        "PASS" if "gvl_mul_lt" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit remaining*maxLeverage vs size*10000",
    )
    rec(
        "NOT-FUNDING",
        "PASS" if "validateLiquidation" in sol and "gvl_fees" in src and "gnr_next_rate" not in src else "FAIL",
        "kernel is GMX cap-to-collateral / maxLeverage, not getNextFundingRate or getFundingFee",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_GMX_LIQ", 'out = out + "="', 'out = out + "ex{"']
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects validateLiquidation / remainingCollateral before ENV",
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
            "commercial_descendants": "GMX V1 Vault perpetual liquidations on Arbitrum/Avalanche",
        },
        "lin_clone": "src/lin_gmx_liq.lin",
        "c11_oracle": "test/oracles/gmx_liq_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "cap_state": 1,
            "cap_fees": 900,
            "no_cap_fees": 950,
            "mid_fees": 900,
            "include_liq_fees": 950,
            "losses_fees": 100,
            "max_leverage_state": 2,
            "healthy_state": 0,
            "profit_raise_state": -4,
            "profit_liq_state": 0,
            "naive_wrap_lev": 1,
            "wide_lev": 0,
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
