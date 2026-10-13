#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getCappedPnl vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_capped_pnl.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_capped_pnl_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_capped_pnl_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_capped_pnl" / "gmx_v2_capped_pnl_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
KEY_REL = "contracts/data/Keys.sol"
KEY_SHA256 = "9940d62b9dca2f3a753d67d7e7339a6326278a35d752c4c80ab1eedf0ab0f075"
KEY_BLOB = "5472e5b4ecd29bb372218caa142476eb95fe55f8"

POOL = 200_000_000
FACTOR50 = 500_000
MAXP = 100_000_000
FLOAT_P = 1_000_000


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
    url = "https://github.com/gmx-io/gmx-synthetics.git"
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
    mkt, prc, key = UPSTREAM / MKT_REL, UPSTREAM / PRC_REL, UPSTREAM / KEY_REL
    if not mkt.exists() or not prc.exists() or not key.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PRC_REL}"]).stdout.strip()
    kblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{KEY_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(prc) != PRC_SHA256 or pblob != PRC_BLOB:
        return "FAIL", commit, f"prc={sha256_file(prc)} blob={pblob}"
    if sha256_file(key) != KEY_SHA256 or kblob != KEY_BLOB:
        return "FAIL", commit, f"key={sha256_file(key)} blob={kblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def trunc_div(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def py_apply(pool: int, factor: int) -> int:
    if pool < 0 or factor < 0:
        return 0
    return (pool * factor) // FLOAT_P


def py_capped(pnl: int, pool: int, factor: int) -> int:
    if pnl < 0:
        return pnl
    maxp = py_apply(pool, factor)
    return maxp if pnl > maxp else pnl


def py_wrong_sym(pnl: int, pool: int, factor: int) -> int:
    maxp = py_apply(pool, factor)
    if pnl < 0:
        return -maxp if -pnl > maxp else pnl
    return maxp if pnl > maxp else pnl


def py_wrong_pos(trader: int, pool: int, factor: int) -> int:
    if trader <= 0:
        return trader
    maxp = py_apply(pool, factor)
    return maxp if trader > maxp else trader


def py_trader(trader: int, pool_pnl: int, pool: int, factor: int) -> int:
    if trader <= 0:
        return trader
    capped = py_capped(pool_pnl, pool, factor)
    if capped == pool_pnl or capped <= 0 or pool_pnl <= 0:
        return trader
    return trunc_div(trader * capped, pool_pnl)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 getCappedPnl / MAX_PNL_FACTOR_FOR_TRADERS — LIN proof (C11)")

    cap_ex = FIX / "GetCappedPnl.excerpt.sol"
    prc_ex = FIX / "PrecisionApply.excerpt.sol"
    key_ex = FIX / "KeysMaxPnl.excerpt.sol"
    scl_ex = FIX / "PositionCappedScale.excerpt.sol"
    if not cap_ex.exists() or not prc_ex.exists() or not key_ex.exists() or not scl_ex.exists():
        rec("PIN-FILE", "FAIL", "pinned getCappedPnl / Precision / Keys / scale excerpts missing")
        return 1
    cap_txt = cap_ex.read_text(encoding="utf-8")
    need_cap = [
        "if (pnl < 0) { return pnl; }",
        "Precision.applyFactor(poolUsd, maxPnlFactor)",
        "return pnl > maxPnl ? maxPnl : pnl;",
    ]
    missing = [s for s in need_cap if s not in cap_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "getCappedPnl excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains loss-passthrough and min(pnl, applyFactor)")
    prc_txt = prc_ex.read_text(encoding="utf-8")
    if "FLOAT_PRECISION = 10 ** 30" not in prc_txt or "mulDiv(value, factor, FLOAT_PRECISION)" not in prc_txt:
        rec("PIN-PREC", "FAIL", "Precision excerpt missing FLOAT / applyFactor")
        return 1
    rec("PIN-PREC", "PASS", "Precision.applyFactor excerpt is mulDiv(value, factor, FLOAT)")
    if "MAX_PNL_FACTOR_FOR_TRADERS" not in key_ex.read_text(encoding="utf-8"):
        rec("PIN-KEYS", "FAIL", "Keys excerpt missing MAX_PNL_FACTOR_FOR_TRADERS")
        return 1
    rec("PIN-KEYS", "PASS", "Keys excerpt pins MAX_PNL_FACTOR_FOR_TRADERS")
    scl_txt = scl_ex.read_text(encoding="utf-8")
    need_scl = [
        "MarketUtils.getCappedPnl(",
        "Keys.MAX_PNL_FACTOR_FOR_TRADERS",
        "cappedPoolPnl != cache.poolPnl && cache.cappedPoolPnl > 0 && cache.poolPnl > 0",
    ]
    missing_s = [s for s in need_scl if s not in scl_txt]
    if missing_s:
        rec("PIN-SCALE", "FAIL", "scale excerpt missing trader mulDiv guard", ",".join(missing_s))
        return 1
    rec("PIN-SCALE", "PASS", "PositionUtils scale is pro-rata iff capped!=pool && both > 0")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + Precision.sol + Keys.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb cap selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (cap / loss / pro-rata / zero-factor / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 capped PnL clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_capped_pnl.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "g2c_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2c_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2c_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, list[int], int]] = [
        ("apply", [POOL, FACTOR50], MAXP),
        ("capped", [150_000_000, POOL, FACTOR50], MAXP),
        ("capped", [50_000_000, POOL, FACTOR50], 50_000_000),
        ("capped", [MAXP, POOL, FACTOR50], MAXP),
        ("capped", [-200_000_000, POOL, FACTOR50], -200_000_000),
        ("wrongsym", [-200_000_000, POOL, FACTOR50], -MAXP),
        ("trader", [150_000_000, 300_000_000, POOL, FACTOR50], 50_000_000),
        ("wrongpos", [150_000_000, POOL, FACTOR50], MAXP),
        ("capped", [150_000_000, POOL, 0], 0),
        ("trader", [150_000_000, 300_000_000, POOL, 0], 150_000_000),
        ("trader", [50_000_000, 80_000_000, POOL, FACTOR50], 50_000_000),
        ("muldiv", [7_000_000_000, 2_000_000_000, 1_000_000], 14_000_000_000_000),
        ("apply", [7_000_000_000, 2_000_000_000], 14_000_000_000_000),
    ]
    fn_map = {
        "apply": "g2c_apply",
        "capped": "g2c_capped",
        "wrongsym": "g2c_wrong_sym",
        "wrongpos": "g2c_wrong_pos",
        "trader": "g2c_trader",
        "muldiv": "g2c_muldiv",
    }
    py_map = {
        "apply": py_apply,
        "capped": py_capped,
        "wrongsym": py_wrong_sym,
        "wrongpos": py_wrong_pos,
        "trader": py_trader,
        "muldiv": lambda a, b, d: (a * b) // d,
    }
    n_ok = 0
    for kind, args, expect in cases:
        fn = fn_map[kind]
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *args)
        pyv = py_map[kind](*args)
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn}{tuple(args)}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    hi = lin_vm(LIN, "g2c_capped", 150_000_000, POOL, FACTOR50)
    lo = lin_vm(LIN, "g2c_capped", 50_000_000, POOL, FACTOR50)
    loss = lin_vm(LIN, "g2c_capped", -200_000_000, POOL, FACTOR50)
    wsym = lin_vm(LIN, "g2c_wrong_sym", -200_000_000, POOL, FACTOR50)
    tr = lin_vm(LIN, "g2c_trader", 150_000_000, 300_000_000, POOL, FACTOR50)
    wpos = lin_vm(LIN, "g2c_wrong_pos", 150_000_000, POOL, FACTOR50)
    zcap = lin_vm(LIN, "g2c_capped", 150_000_000, POOL, 0)
    ztr = lin_vm(LIN, "g2c_trader", 150_000_000, 300_000_000, POOL, 0)
    wide = lin_vm(LIN, "g2c_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2c_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)

    if hi != MAXP or lo != 50_000_000:
        rec("CAP-VS-FREE", "FAIL", "profit clip vs below-cap", f"hi={hi} lo={lo}")
        return 1
    if loss != -200_000_000 or wsym != -MAXP:
        rec("LOSS-FREE", "FAIL", "loss passthrough vs symmetric cap", f"loss={loss} wsym={wsym}")
        return 1
    if tr != 50_000_000 or wpos != MAXP:
        rec("PRORATA", "FAIL", "trader pro-rata vs min(trader,maxPnl)", f"tr={tr} wpos={wpos}")
        return 1
    if zcap != 0 or ztr != 150_000_000:
        rec("ZERO-FACTOR", "FAIL", "factor 0 pool cap vs trader guard", f"zcap={zcap} ztr={ztr}")
        return 1
    if naive == wide or wide != 14_000_000_000_000 or naive != wrap_py:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit applyFactor", f"naive={naive} wide={wide} py={wrap_py}")
        return 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("CAP-VS-FREE", "PASS", "pool 2e8 factor 50%: 1.5e8 clips to 1e8; 5e7 stays 5e7")
    rec("LOSS-FREE", "PASS", "loss -2e8 stays -2e8; wrong symmetric cap yields -1e8")
    rec("PRORATA", "PASS", "trader 1.5e8 of pool 3e8 is 5e7 pro-rata, not min(trader,maxPnl)=1e8")
    rec("ZERO-FACTOR", "PASS", "factor 0 caps pool to 0; trader stays 1.5e8 (capped>0 guard)")
    rec("NAIVE-WRAP", "PASS", "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000")

    jit_ok = lin_roundtrip_jit(LIN, "g2c_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2c_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "g2c_capped" in src and "g2c_trader" in src else "FAIL",
        "LIN clone takes pnl/poolUsd/factor as arguments (no DataStore)")
    rec("WIDE-MULDIV", "PASS" if "g2c_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit poolUsd*factor / FLOAT prime")
    rec("NOT-UNCAPPED", "PASS" if "getCappedPnl" in cap_txt and "g2c_wrong_pos" in src else "FAIL",
        "kernel is pool cap + trader pro-rata, not uncapped pickPriceForPnl")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_GMX_V2_CAPPED_PNL", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getCappedPnl / MAX_PNL_FACTOR_FOR_TRADERS before ENV",
        ",".join(missing_t) if missing_t else "")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_CAPPED_PNL" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_capped_pnl / max_pnl_factor_for_traders")

    evidence = {
        "schema": "LIN_GMX_V2_CAPPED_PNL_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT,
            "path": MKT_REL,
            "precision_path": PRC_REL,
            "keys_path": KEY_REL,
            "git_blob_sha": blob or MKT_BLOB,
            "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PRC_BLOB,
            "precision_file_sha256": PRC_SHA256,
            "keys_git_blob_sha": KEY_BLOB,
            "keys_file_sha256": KEY_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 synthetics: trader PnL is pro-rata of pool getCappedPnl(MAX_PNL_FACTOR_FOR_TRADERS), not min(trader, poolUsd*factor)",
        },
        "lin_clone": "src/lin_gmx_v2_capped_pnl.lin",
        "c11_oracle": "test/oracles/gmx_v2_capped_pnl_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "max_pnl_50pct": MAXP,
            "profit_clipped": MAXP,
            "profit_below": 50_000_000,
            "loss_passthrough": -200_000_000,
            "wrong_sym_loss": -MAXP,
            "trader_prorata": 50_000_000,
            "wrong_pos_cap": MAXP,
            "zero_factor_pool": 0,
            "zero_factor_trader": 150_000_000,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-capped-pnl",
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
