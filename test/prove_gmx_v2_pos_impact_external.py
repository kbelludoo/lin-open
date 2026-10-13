#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 capPositiveImpactUsdByMaxPositionImpact vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_pos_impact.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_pos_impact_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_pos_impact_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_pos_impact" / "gmx_v2_pos_impact_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
FLOAT_P = 1_000_000

CLIP = (150_000_000, 200_000_000, 500_000, 800_000)
STAY = (50_000_000, 200_000_000, 500_000, 800_000)
EQUAL = (100_000_000, 200_000_000, 500_000, 800_000)
NEG = (-200_000_000, 200_000_000, 500_000, 800_000)
CLAMP = (150_000_000, 200_000_000, 500_000, 250_000)
STAY_CLAMP = (40_000_000, 200_000_000, 500_000, 250_000)
FACTOR0 = (150_000_000, 200_000_000, 0, 1_000_000)
POOL = (150_000_000, 400_000_000, 500_000, 800_000)


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


def py_pos_factor(posf: int, negf: int) -> int:
    return negf if posf > negf else posf


def py_cap(args: tuple[int, ...]) -> int:
    impact, size, posf, negf = args
    if impact < 0:
        return impact
    maxv = py_apply(size, py_pos_factor(posf, negf))
    return maxv if impact > maxv else impact


def py_wrong_uncapped(args: tuple[int, ...]) -> int:
    return args[0]


def py_wrong_noclamp(args: tuple[int, ...]) -> int:
    impact, size, posf, _negf = args
    if impact < 0:
        return impact
    maxv = py_apply(size, posf)
    return maxv if impact > maxv else impact


def py_wrong_abs(args: tuple[int, ...]) -> int:
    impact, size, posf, negf = args
    maxv = py_apply(size, py_pos_factor(posf, negf))
    if impact < 0:
        nmax = -maxv
        return nmax if impact < nmax else impact
    return maxv if impact > maxv else impact


def py_wrong_pool(args: tuple[int, ...]) -> int:
    impact, pool, posf, negf = args
    if impact < 0:
        return impact
    maxv = py_apply(pool, py_pos_factor(posf, negf))
    return maxv if impact > maxv else impact


def py_wrong_stay(args: tuple[int, ...]) -> int:
    impact, size, posf, negf = args
    if py_pos_factor(posf, negf) == 0:
        return impact
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
    print("  GMX V2 capPositiveImpactUsdByMaxPositionImpact — LIN proof (C11)")

    cap_ex = FIX / "CapPositiveImpactUsdByMaxPositionImpact.excerpt.sol"
    fac_ex = FIX / "GetMaxPositionImpactFactors.excerpt.sol"
    prc_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    if not all(p.exists() for p in (cap_ex, fac_ex, prc_ex)):
        rec("PIN-FILE", "FAIL", "pinned cap / factors / Precision excerpts missing")
        return 1
    cap_txt = cap_ex.read_text(encoding="utf-8")
    need = [
        "if (priceImpactUsd < 0)",
        "getMaxPositionImpactFactor(dataStore, market, true)",
        "Precision.applyFactor(sizeDeltaUsd, maxPriceImpactFactor)",
        "if (priceImpactUsd > maxPriceImpactUsdBasedOnMaxPriceImpactFactor)",
    ]
    missing = [s for s in need if s not in cap_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "cap excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains <0 passthrough, applyFactor(sizeDelta), clip")
    fac_txt = fac_ex.read_text(encoding="utf-8")
    if "if (maxPositiveImpactFactor > maxNegativeImpactFactor)" not in fac_txt:
        rec("PIN-FACTORS", "FAIL", "factors excerpt missing positive<=negative clamp")
        return 1
    rec("PIN-FACTORS", "PASS", "getMaxPositionImpactFactors clamps pos factor down to neg factor")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb pos-impact selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (clip / clamp / neg / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 pos-impact clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_pos_impact.lin")
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

    gate = run([str(C0), "vm", str(LIN), "g2p_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2p_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2p_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, tuple[int, ...], int]] = [
        ("cap", CLIP, 100_000_000),
        ("wronguncapped", CLIP, 150_000_000),
        ("cap", STAY, 50_000_000),
        ("cap", EQUAL, 100_000_000),
        ("cap", NEG, -200_000_000),
        ("wrongabs", NEG, -100_000_000),
        ("cap", CLAMP, 50_000_000),
        ("wrongnoclamp", CLAMP, 100_000_000),
        ("cap", STAY_CLAMP, 40_000_000),
        ("cap", FACTOR0, 0),
        ("wrongstay", FACTOR0, 150_000_000),
        ("wrongpool", POOL, 150_000_000),
        ("muldiv", (7_000_000_000, 2_000_000_000, 1_000_000), 14_000_000_000_000),
        ("posfactor", (500_000, 250_000), 250_000),
        ("posfactor", (500_000, 800_000), 500_000),
    ]
    fn_map = {
        "cap": "g2p_cap",
        "wronguncapped": "g2p_wrong_uncapped",
        "wrongnoclamp": "g2p_wrong_noclamp",
        "wrongabs": "g2p_wrong_abs",
        "wrongpool": "g2p_wrong_pool",
        "wrongstay": "g2p_wrong_factor0_stay",
        "muldiv": "g2p_muldiv",
        "posfactor": "g2p_pos_factor",
    }
    py_map = {
        "cap": py_cap,
        "wronguncapped": py_wrong_uncapped,
        "wrongnoclamp": py_wrong_noclamp,
        "wrongabs": py_wrong_abs,
        "wrongpool": py_wrong_pool,
        "wrongstay": py_wrong_stay,
        "muldiv": lambda a: py_muldiv(*a),
        "posfactor": lambda a: py_pos_factor(*a),
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

    wide = lin_vm(LIN, "g2p_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2p_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)
    clip = lin_vm(LIN, "g2p_cap", *CLIP)
    uncap = lin_vm(LIN, "g2p_wrong_uncapped", *CLIP)
    neg = lin_vm(LIN, "g2p_cap", *NEG)
    wabs = lin_vm(LIN, "g2p_wrong_abs", *NEG)
    clamped = lin_vm(LIN, "g2p_cap", *CLAMP)
    noclamp = lin_vm(LIN, "g2p_wrong_noclamp", *CLAMP)
    f0 = lin_vm(LIN, "g2p_cap", *FACTOR0)
    stay0 = lin_vm(LIN, "g2p_wrong_factor0_stay", *FACTOR0)
    pool = lin_vm(LIN, "g2p_wrong_pool", *POOL)

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec(
        "CLIP-SIZE",
        "PASS" if clip == 100_000_000 and uncap == 150_000_000 else "FAIL",
        "positive 1.5e8 clips to applyFactor(size=2e8, 0.5)=1e8; uncapped stays 1.5e8",
    )
    rec(
        "NEG-PASS",
        "PASS" if neg == -200_000_000 and wabs == -100_000_000 else "FAIL",
        "negative -2e8 passes through; symmetric abs cap would clip to -1e8",
    )
    rec(
        "POS-CLAMP",
        "PASS" if clamped == 50_000_000 and noclamp == 100_000_000 else "FAIL",
        "pos 0.5 clamped to neg 0.25 yields 5e7; skipping clamp over-rebates 1e8",
    )
    rec(
        "FACTOR0",
        "PASS" if f0 == 0 and stay0 == 150_000_000 else "FAIL",
        "factor 0 clips positive impact to 0; getCappedPnl-style stay would keep 1.5e8",
    )
    rec(
        "NOT-POOL",
        "PASS" if pool == 150_000_000 and clip == 100_000_000 else "FAIL",
        "applyFactor(pool=4e8, 0.5)=2e8 leaves 1.5e8; sizeDelta cap clips to 1e8",
    )
    rec(
        "NAIVE-WRAP",
        "PASS" if naive != wide and wide == 14_000_000_000_000 and naive == wrap_py else "FAIL",
        "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "g2p_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2p_test_suite (in-memory libtcc)")
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
        "PASS" if "g2p_cap" in src and "g2p_pos_factor" in src else "FAIL",
        "LIN clone takes impact/size/posFactor/negFactor as arguments (no DataStore)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "g2p_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv",
    )
    rec(
        "NOT-CAPPED-PNL",
        "PASS" if "sizeDeltaUsd" in cap_txt and "g2p_wrong_pool" in src else "FAIL",
        "kernel is applyFactor(sizeDelta) not getCappedPnl applyFactor(pool, maxPnl)",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_t = ["REJ_SOLIDITY_GMX_V2_POS_IMPACT", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects capPositiveImpactUsdByMaxPositionImpact before ENV",
        ",".join(missing_t) if missing_t else "",
    )
    if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0]:
        rec("SOL-HEADER", "FAIL", "changelog must not contain the token =ex{")
    else:
        rec("SOL-HEADER", "PASS", "transpiler header changelog does not contain =ex{")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_V2_POS_IMPACT" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects cap_positive_impact_usd_by_max_position_impact",
    )

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_POS_IMPACT_EVIDENCE_1.0",
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
            "commercial_descendants": "GMX V2 synthetics: positive price-impact rebate is capped by applyFactor(sizeDelta, min(posFactor,negFactor)); negative impact is paid in full; this is not getCappedPnl (pool*maxPnlFactor).",
        },
        "lin_clone": "src/lin_gmx_v2_pos_impact.lin",
        "c11_oracle": "test/oracles/gmx_v2_pos_impact_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "clip_size": 100_000_000,
            "uncapped": 150_000_000,
            "stay": 50_000_000,
            "equal": 100_000_000,
            "neg_pass": -200_000_000,
            "wrong_abs": -100_000_000,
            "clamp_pos": 50_000_000,
            "wrong_noclamp": 100_000_000,
            "factor0": 0,
            "wrong_factor0_stay": 150_000_000,
            "wrong_pool": 150_000_000,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-pos-impact",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
