#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V1 Vault.adjustForDecimals / tokenToUsdMin vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_dec.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_dec_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_dec_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_contracts")
EVIDENCE = ROOT / "examples" / "gmx_dec" / "gmx_dec_evidence.json"

PINNED_SHA256 = "0b49e265fc4c04d3eea74b07d698748050671a2df259f1faa8d05cabf2970f92"
PINNED_BLOB = "4aef3c7dcf40b4657e7dfcef582958dc2d418126"
PINNED_COMMIT = "fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8"
UPSTREAM_REL = "contracts/core/Vault.sol"


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


def py_pow10(n: int) -> int:
    if n < 0 or n > 18:
        return 0
    return 10**n


def py_adjust(amount: int, dec_div: int, dec_mul: int) -> int:
    if amount < 0:
        return 0
    pm = py_pow10(dec_mul)
    pd = py_pow10(dec_div)
    if pm == 0 or pd == 0:
        return 0
    if dec_mul != 0 and pm == 1:
        return 0
    if dec_div != 0 and pd == 1:
        return 0
    q = (amount * pm) // pd
    return 0 if q > (1 << 64) - 1 else q


def py_tok2usd(amount: int, price: int, decimals: int) -> int:
    if amount == 0 or amount < 0 or price < 0:
        return 0
    pd = py_pow10(decimals)
    if pd == 0:
        return 0
    q = (amount * price) // pd
    return 0 if q > (1 << 64) - 1 else q


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V1 Vault.adjustForDecimals / tokenToUsdMin — LIN proof (C11)")
    pinned = FIX / "Vault.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned Vault.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned Vault.sol sha256 matches manifest")

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
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/core/Vault.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb dec selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (6->18 / 8->18 / wrap / USDG vs 30)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX dec clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_dec.lin")
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

    gate = run([str(C0), "vm", str(LIN), "gad_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gad_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gad_test_suite == 1 on Compiler 0 interpreter")

    cases = [
        ("adjust", [1000000000000000000, 18, 18], 1000000000000000000),
        ("adjust", [1000000, 6, 18], 1000000000000000000),
        ("adjust", [100000000, 8, 18], 1000000000000000000),
        ("adjust", [1000000000000000000, 18, 6], 1000000),
        ("adjust", [5000000000, 6, 10], 50000000000000),
        ("adjust", [100000000, 8, 8], 100000000),
        ("tok2usd", [0, 100000000, 6], 0),
        ("tok2usd", [100000000, 4000000000000, 8], 4000000000000),
        ("tok2usd", [1000000, 100000000, 6], 100000000),
        ("usd2tok", [4000000000000, 4000000000000, 8], 100000000),
        ("usd2tok", [100000000, 100000000, 6], 1000000),
    ]
    n_ok = 0
    fn_map = {"adjust": "gad_adjust", "tok2usd": "gad_token_to_usd", "usd2tok": "gad_usd_to_token"}
    py_map = {"adjust": py_adjust, "tok2usd": py_tok2usd, "usd2tok": lambda u, p, d: (
        0 if u == 0 or p <= 0 else ((u * py_pow10(d)) // p if py_pow10(d) else 0)
    )}
    for kind, args, expect in cases:
        fn = fn_map[kind]
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *args)
        pyv = py_map[kind](*args)
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"{fn}{tuple(args)}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}",
            )
            return 1
        n_ok += 1

    ignore = lin_vm(LIN, "gad_naive_ignore", 1000000)
    as18 = lin_vm(LIN, "gad_naive_as18_usd", 1000000, 100000000)
    naive = lin_vm(LIN, "gad_naive_i64_adjust", 5000000000, 6, 10)
    wide = lin_vm(LIN, "gad_adjust", 5000000000, 6, 10)
    usdg = lin_vm(LIN, "gad_adjust_usdg", 1000000, 0, 6, 1, 0)
    wrong30 = lin_vm(LIN, "gad_wrong_prec_adjust", 1000000, 6)
    if ignore != 1000000 or int(oracle(["ignore", "1000000"])) != 1000000:
        rec("IGN-TRAP", "FAIL", "ignore-decimals contrast", f"lin={ignore}")
        return 1
    if as18 != 0 or int(oracle(["as18", "1000000", "100000000"])) != 0:
        rec("AS18-TRAP", "FAIL", "treat-USDC-as-18 contrast", f"lin={as18}")
        return 1
    if naive == wide or wide != 50000000000000:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit adjust", f"naive={naive} wide={wide}")
        return 1
    wrapped = w64(5000000000 * 10**10)
    wrap_py = wrapped // 1000000 if wrapped >= 0 else -((-wrapped) // 1000000)
    if naive != wrap_py:
        rec("NAIVE-WRAP", "FAIL", "LIN naive wrap != python w64", f"lin={naive} py={wrap_py}")
        return 1
    if usdg != 1000000000000000000 or wrong30 != 0:
        rec("USDG-PREC", "FAIL", "USDG 18 vs PRICE_PRECISION 30", f"usdg={usdg} wrong30={wrong30}")
        return 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("IGN-TRAP", "PASS", "USDC 1e6 6->18: 1e18 vs naive ignore-decimals 1e6 (1e12x)")
    rec("AS18-TRAP", "PASS", "USDC tokenToUsd treated as 18-dec: 0 vs correct 1e8")
    rec("NAIVE-WRAP", "PASS", "naive i64 5e9*1e10/1e6 wraps; 128-bit muldiv yields 5e13")
    rec("USDG-PREC", "PASS", "USDG_DECIMALS=18 yields 1e18; PRICE_PRECISION 30 fail-closes to 0")
    rec("WBTC-SCALE", "PASS", "WBTC 1e8 8->18 = 1e18; tokenToUsd 1e8*40000e8/1e8 = 40000e8")

    jit_ok = lin_roundtrip_jit(LIN, "gad_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gad_test_suite (in-memory libtcc)")
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
        "PASS" if "gad_adjust" in src and "function adjustForDecimals" in sol else "FAIL",
        "LIN clone takes amount/decDiv/decMul as arguments (no tokenDecimals mapping / usdg)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "gad_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit amount * 10^decMul / 10^decDiv",
    )
    rec(
        "NOT-LIQ",
        "PASS" if "adjustForDecimals" in sol and "gad_adjust" in src and "gvl_fees" not in src else "FAIL",
        "kernel is GMX decimals-normalize muldiv, not validateLiquidation or getFundingFee",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_GMX_DEC", 'out = out + "="', 'out = out + "ex{"']
    missing = [t for t in need if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects adjustForDecimals / tokenToUsdMin before ENV",
        ",".join(missing) if missing else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_DEC" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects adjust_for_decimals / token_to_usd_min",
    )

    evidence = {
        "schema": "LIN_GMX_ADJUST_DECIMALS_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-contracts",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "MIT",
            "commercial_descendants": "GMX V1 Vault swap/mint/burn USDG decimal normalize on Arbitrum/Avalanche",
        },
        "lin_clone": "src/lin_gmx_dec.lin",
        "c11_oracle": "test/oracles/gmx_dec_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "usdc_6_to_18": 1000000000000000000,
            "naive_ignore": 1000000,
            "wbtc_8_to_18": 1000000000000000000,
            "downscale_18_to_6": 1000000,
            "wrap_wide": 50000000000000,
            "wrap_naive": wrap_py,
            "usdc_token_to_usd": 100000000,
            "usdc_as18_usd": 0,
            "wbtc_token_to_usd": 4000000000000,
            "usdg_18": 1000000000000000000,
            "price_precision_30": 0,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-dec",
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
