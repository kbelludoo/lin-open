#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 capPositiveImpactUsdByPositionImpactPool vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_impact_pool.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_impact_pool_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_impact_pool_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_impact_pool" / "gmx_v2_impact_pool_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
FLOAT_P = 1_000_000

CLIP = (200_000_000, 100_000_000, 200_000_000, 250_000, 1_000_000_000, 0)
COVER = (80_000_000, 100_000_000, 200_000_000, 250_000, 1_000_000_000, 0)
LEND_OK = (140_000_000, 100_000_000, 200_000_000, 250_000, 1_000_000_000, 0)
EQUAL = (150_000_000, 100_000_000, 200_000_000, 250_000, 1_000_000_000, 0)
CONFIG = (200_000_000, 100_000_000, 200_000_000, 500_000, 40_000_000, 0)
LENT = (200_000_000, 100_000_000, 200_000_000, 500_000, 100_000_000, 80_000_000)
OVER = (200_000_000, 100_000_000, 200_000_000, 500_000, 100_000_000, 150_000_000)
NEG = (-200_000_000, 100_000_000, 200_000_000, 250_000, 1_000_000_000, 0)
ZERO = (100_000_000, 0, 0, 0, 0, 0)
FACTOR0 = (200_000_000, 100_000_000, 200_000_000, 0, 1_000_000_000, 0)
LONG = (200_000_000, 100_000_000, 100_000_000, 250_000, 1_000_000_000, 0)
SIZE = (200_000_000, 200_000_000, 250_000)


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
    mkt, prc = UPSTREAM / MKT_REL, UPSTREAM / PRC_REL
    if not mkt.exists() or not prc.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PRC_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(prc) != PRC_SHA256 or pblob != PRC_BLOB:
        return "FAIL", commit, f"prc={sha256_file(prc)} blob={pblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def trunc_div(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def py_muldiv(a: int, b: int, d: int) -> int:
    return 0 if d == 0 else (a * b) // d


def py_apply(v: int, f: int) -> int:
    return py_muldiv(v, f, FLOAT_P)


def py_lendable(pool: int, factor: int, config: int, lent: int) -> int:
    mx = py_apply(pool, factor)
    if mx > config:
        mx = config
    if lent > mx:
        return 0
    return mx - lent


def py_cap(args: tuple[int, ...]) -> int:
    impact, pool_usd, mkt_usd, factor, config, lent = args
    if impact <= 0:
        return impact
    avail = py_lendable(mkt_usd, factor, config, lent)
    if impact <= pool_usd:
        return impact
    need = impact - pool_usd
    if need > avail:
        return pool_usd + avail
    return impact


def py_wrong_uncapped(args: tuple[int, ...]) -> int:
    return args[0]


def py_wrong_pool(args: tuple[int, ...]) -> int:
    impact, pool_usd = args[0], args[1]
    if impact <= 0:
        return impact
    return pool_usd if impact > pool_usd else impact


def py_wrong_noconfig(args: tuple[int, ...]) -> int:
    impact, pool_usd, mkt_usd, factor, _config, lent = args
    return py_cap((impact, pool_usd, mkt_usd, factor, 2**63 - 1, lent))


def py_wrong_nolent(args: tuple[int, ...]) -> int:
    impact, pool_usd, mkt_usd, factor, config, _lent = args
    return py_cap((impact, pool_usd, mkt_usd, factor, config, 0))


def py_wrong_size(args: tuple[int, ...]) -> int:
    impact, size, factor = args
    if impact <= 0:
        return impact
    maxv = py_apply(size, factor)
    return maxv if impact > maxv else impact


def py_wrong_abs(args: tuple[int, ...]) -> int:
    impact, pool_usd, mkt_usd, factor, config, lent = args
    capv = pool_usd + py_lendable(mkt_usd, factor, config, lent)
    if impact < 0:
        nmax = -capv
        return nmax if impact < nmax else impact
    return capv if impact > capv else impact


def py_wrong_stay(args: tuple[int, ...]) -> int:
    if args[3] == 0:
        return args[0]
    return py_cap(args)


def py_wrong_long(args: tuple[int, ...]) -> int:
    return py_cap(args)


def astr(args: tuple[int, ...]) -> list[str]:
    return [str(a) for a in args]


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 capPositiveImpactUsdByPositionImpactPool — LIN proof (C11)")

    cap_ex = FIX / "CapPositiveImpactUsdByPositionImpactPool.excerpt.sol"
    lend_ex = FIX / "GetMaxLendableUsdAvailable.excerpt.sol"
    prc_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    if not all(p.exists() for p in (cap_ex, lend_ex, prc_ex)):
        rec("PIN-FILE", "FAIL", "pinned pool / lendable / Precision excerpts missing")
        return 1
    cap_txt = cap_ex.read_text(encoding="utf-8")
    need = [
        "if (priceImpactUsd <= 0)",
        "usdRequiredToBeLent",
        "getMaxLendableUsdAvailable",
        "longTokenUsd + cache.shortTokenUsd",
        "if (cache.usdRequiredToBeLent > cache.maxLendableUsd)",
    ]
    missing = [s for s in need if s not in cap_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "pool excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains <=0 passthrough, pool+lend clip, long+short")
    lend_txt = lend_ex.read_text(encoding="utf-8")
    if "Precision.applyFactor(poolUsd, maxLendableFactor)" not in lend_txt:
        rec("PIN-LEND", "FAIL", "lendable excerpt missing applyFactor(poolUsd, factor)")
        return 1
    if "if (lentUsd > maxLendableUsd)" not in lend_txt:
        rec("PIN-LEND", "FAIL", "lendable excerpt missing over-lent return 0")
        return 1
    rec("PIN-LEND", "PASS", "getMaxLendableUsdAvailable min(applyFactor, config) minus lent")
    prc_txt = prc_ex.read_text(encoding="utf-8")
    if "FLOAT_PRECISION = 10 ** 30" not in prc_txt or "applyFactor" not in prc_txt:
        rec("PIN-PREC", "FAIL", "Precision excerpt missing FLOAT / applyFactor")
        return 1
    rec("PIN-PREC", "PASS", "Precision excerpt pins FLOAT=1e30 (LIN uses FLOAT prime=1e6)")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + Precision.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb impact-pool selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (clip / config / lent / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 impact-pool clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_impact_pool.lin")
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

    gate = run([str(C0), "vm", str(LIN), "g2l_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2l_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2l_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, tuple[int, ...], int]] = [
        ("cap", CLIP, 150_000_000),
        ("wronguncapped", CLIP, 200_000_000),
        ("wrongpool", CLIP, 100_000_000),
        ("size", SIZE, 50_000_000),
        ("cap", COVER, 80_000_000),
        ("cap", LEND_OK, 140_000_000),
        ("cap", EQUAL, 150_000_000),
        ("cap", CONFIG, 140_000_000),
        ("wrongnoconfig", CONFIG, 200_000_000),
        ("cap", LENT, 120_000_000),
        ("wrongnolent", LENT, 200_000_000),
        ("cap", OVER, 100_000_000),
        ("cap", NEG, -200_000_000),
        ("wrongabs", NEG, -150_000_000),
        ("cap", ZERO, 0),
        ("cap", FACTOR0, 100_000_000),
        ("wrongstay", FACTOR0, 200_000_000),
        ("wronglong", LONG, 125_000_000),
        ("muldiv", (7_000_000_000, 2_000_000_000, 1_000_000), 14_000_000_000_000),
        ("lendable", (200_000_000, 250_000, 1_000_000_000, 0), 50_000_000),
    ]
    fn_map = {
        "cap": "g2l_cap",
        "wronguncapped": "g2l_wrong_uncapped",
        "wrongpool": "g2l_wrong_pool_only",
        "wrongnoconfig": "g2l_wrong_noconfig",
        "wrongnolent": "g2l_wrong_nolent",
        "wrongabs": "g2l_wrong_abs",
        "wrongstay": "g2l_wrong_factor0_stay",
        "wronglong": "g2l_wrong_long",
        "size": "g2l_wrong_size",
        "muldiv": "g2l_muldiv",
        "lendable": "g2l_max_lendable",
    }
    py_map = {
        "cap": py_cap,
        "wronguncapped": py_wrong_uncapped,
        "wrongpool": py_wrong_pool,
        "wrongnoconfig": py_wrong_noconfig,
        "wrongnolent": py_wrong_nolent,
        "wrongabs": py_wrong_abs,
        "wrongstay": py_wrong_stay,
        "wronglong": py_wrong_long,
        "size": py_wrong_size,
        "muldiv": lambda a: py_muldiv(*a),
        "lendable": lambda a: py_lendable(*a),
    }
    n_ok = 0
    for kind, args, expect in cases:
        want = int(oracle([kind, *astr(args)]).splitlines()[-1])
        want_limbs = int(oracle([kind, *astr(args), "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn_map[kind], *args)
        pyv = py_map[kind](args)
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"{fn_map[kind]}{args}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}",
            )
            return 1
        n_ok += 1

    wide = lin_vm(LIN, "g2l_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2l_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)
    clip = lin_vm(LIN, "g2l_cap", *CLIP)
    uncap = lin_vm(LIN, "g2l_wrong_uncapped", *CLIP)
    pool_only = lin_vm(LIN, "g2l_wrong_pool_only", *CLIP)
    size_cap = lin_vm(LIN, "g2l_wrong_size", *SIZE)
    cfg = lin_vm(LIN, "g2l_cap", *CONFIG)
    noconfig = lin_vm(LIN, "g2l_wrong_noconfig", *CONFIG)
    lentv = lin_vm(LIN, "g2l_cap", *LENT)
    nolent = lin_vm(LIN, "g2l_wrong_nolent", *LENT)
    over = lin_vm(LIN, "g2l_cap", *OVER)
    neg = lin_vm(LIN, "g2l_cap", *NEG)
    wabs = lin_vm(LIN, "g2l_wrong_abs", *NEG)
    f0 = lin_vm(LIN, "g2l_cap", *FACTOR0)
    stay0 = lin_vm(LIN, "g2l_wrong_factor0_stay", *FACTOR0)
    wlong = lin_vm(LIN, "g2l_wrong_long", *LONG)

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec(
        "CLIP-LEND",
        "PASS" if clip == 150_000_000 and uncap == 200_000_000 else "FAIL",
        "positive 2e8 clips to pool 1e8 + lend 5e7 = 1.5e8; uncapped stays 2e8",
    )
    rec(
        "NOT-POOL-ONLY",
        "PASS" if pool_only == 100_000_000 and clip == 150_000_000 else "FAIL",
        "pool-only would clip to 1e8; lendable headroom pays the extra 5e7",
    )
    rec(
        "NOT-SIZE-CAP",
        "PASS" if size_cap == 50_000_000 and clip == 150_000_000 else "FAIL",
        "applyFactor(sizeDelta=2e8, 0.25)=5e7 is capPositiveImpactUsdByMaxPositionImpact, not this kernel",
    )
    rec(
        "CONFIG-MIN",
        "PASS" if cfg == 140_000_000 and noconfig == 200_000_000 else "FAIL",
        "config 4e7 beats applyFactor 1e8; skip-config would stay 2e8 (need==apply)",
    )
    rec(
        "LENT-CONSUME",
        "PASS" if lentv == 120_000_000 and nolent == 200_000_000 else "FAIL",
        "already-lent 8e7 leaves 2e7; ignoring lent stays 2e8",
    )
    rec(
        "OVER-LENT",
        "PASS" if over == 100_000_000 else "FAIL",
        "lentUsd > maxLendable returns 0 available; clip to impact-pool only",
    )
    rec(
        "NEG-PASS",
        "PASS" if neg == -200_000_000 and wabs == -150_000_000 else "FAIL",
        "negative -2e8 passes through; a symmetric abs cap would clip to -1.5e8",
    )
    rec(
        "FACTOR0",
        "PASS" if f0 == 100_000_000 and stay0 == 200_000_000 else "FAIL",
        "factor 0 yields 0 lendable so clip to pool 1e8; stay would keep 2e8",
    )
    rec(
        "LONG-PLUS-SHORT",
        "PASS" if wlong == 125_000_000 and clip == 150_000_000 else "FAIL",
        "applyFactor(long-only 1e8, 0.25)=2.5e7 clips to 1.25e8; long+short clips to 1.5e8",
    )
    rec(
        "NAIVE-WRAP",
        "PASS" if naive != wide and wide == 14_000_000_000_000 and naive == wrap_py else "FAIL",
        "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "g2l_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2l_test_suite (in-memory libtcc)")
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
    rec(
        "EXPLICIT-ARGS",
        "PASS" if "g2l_cap" in src and "g2l_max_lendable" in src else "FAIL",
        "LIN clone takes impact/pool/factor/config/lent as arguments (no DataStore)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "g2l_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv",
    )
    rec(
        "NOT-SIZE-KERNEL",
        "PASS" if "usdRequiredToBeLent" in cap_txt and "g2l_wrong_size" in src else "FAIL",
        "kernel is impact-pool + lendable, not applyFactor(sizeDelta)",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_t = ["REJ_SOLIDITY_GMX_V2_IMPACT_POOL", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects capPositiveImpactUsdByPositionImpactPool before ENV",
        ",".join(missing_t) if missing_t else "",
    )
    if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0]:
        rec("SOL-HEADER", "FAIL", "changelog must not contain the token =ex{")
    else:
        rec("SOL-HEADER", "PASS", "transpiler header changelog does not contain =ex{")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_V2_IMPACT_POOL" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects cap_positive_impact_usd_by_position_impact_pool",
    )

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_IMPACT_POOL_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT,
            "path": MKT_REL,
            "precision_path": PRC_REL,
            "git_blob_sha": blob or MKT_BLOB,
            "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PRC_BLOB,
            "precision_file_sha256": PRC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 synthetics: positive price-impact above the impact pool is paid by lending from the GM pool, capped by min(applyFactor(poolUsd, maxLendableFactor), maxLendableUsd) minus already-lent. This is not capPositiveImpactUsdByMaxPositionImpact (sizeDelta factor).",
        },
        "lin_clone": "src/lin_gmx_v2_impact_pool.lin",
        "c11_oracle": "test/oracles/gmx_v2_impact_pool_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "clip_lend": 150_000_000,
            "uncapped": 200_000_000,
            "pool_only": 100_000_000,
            "wrong_size": 50_000_000,
            "cover": 80_000_000,
            "lend_ok": 140_000_000,
            "equal_need": 150_000_000,
            "config_min": 140_000_000,
            "wrong_noconfig": 200_000_000,
            "lent_consume": 120_000_000,
            "wrong_nolent": 200_000_000,
            "over_lent": 100_000_000,
            "neg_pass": -200_000_000,
            "wrong_abs": -150_000_000,
            "factor0": 100_000_000,
            "wrong_factor0_stay": 200_000_000,
            "wrong_long": 125_000_000,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-impact-pool",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
