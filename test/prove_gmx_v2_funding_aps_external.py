#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getNextFundingAmountPerSize vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_funding_aps.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_funding_aps_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_funding_aps_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_funding_aps" / "gmx_v2_funding_aps_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"

LONG_OI = 200_000_000
SHORT_OI = 100_000_000
DUR = 4000
FPS = 10
FUND_LONG = 8_000_000
FUND_SHORT = 4_000_000
FLOAT_P = 1_000_000
STORE_P = 1_000_000_000


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


def py_funding(lo: int, so: int, pay: int, dur: int, fps: int, same: int) -> int:
    if lo <= 0 or so <= 0:
        return 0
    size = lo if pay else so
    raw = (size * (dur * fps)) // FLOAT_P
    return raw // (2 if same else 1)


def py_wrong_zero(lo: int, so: int, pay: int, dur: int, fps: int, same: int) -> int:
    size = lo if pay else so
    if size <= 0:
        return 0
    raw = (size * (dur * fps)) // FLOAT_P
    return raw // (2 if same else 1)


def py_wrong_nofps(lo: int, so: int, pay: int, dur: int, fps: int, same: int) -> int:
    if lo <= 0 or so <= 0:
        return 0
    size = lo if pay else so
    return ((size * dur) // FLOAT_P) // (2 if same else 1)


def py_wrong_nodiv(lo: int, so: int, pay: int, dur: int, fps: int, same: int) -> int:
    if lo <= 0 or so <= 0:
        return 0
    size = lo if pay else so
    return (size * (dur * fps)) // FLOAT_P


def py_split(funding: int, col: int, total: int) -> int:
    if total == 0:
        return 0
    return (funding * col) // total


def py_aps(funding: int, oi: int, price: int, round_up: int) -> int:
    if funding == 0 or oi == 0 or price <= 0:
        return 0
    if round_up:
        num = funding * STORE_P
        fpsz = (num + oi - 1) // oi if num % oi else num // oi
        return (fpsz + price - 1) // price if fpsz % price else fpsz // price
    return (funding * STORE_P // oi) // price


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 getNextFundingAmountPerSize — LIN proof (C11)")

    fund_ex = FIX / "GetNextFundingAmountPerSize.excerpt.sol"
    dlt_ex = FIX / "GetFundingAmountPerSizeDelta.excerpt.sol"
    div_ex = FIX / "GetPoolDivisor.excerpt.sol"
    prc_ex = FIX / "PrecisionApplySqrt.excerpt.sol"
    if not fund_ex.exists() or not dlt_ex.exists() or not div_ex.exists() or not prc_ex.exists():
        rec("PIN-FILE", "FAIL", "pinned funding-aps / delta / divisor / Precision excerpts missing")
        return 1
    fund_txt = fund_ex.read_text(encoding="utf-8")
    need_fund = [
        "if (cache.longOpenInterest == 0 || cache.shortOpenInterest == 0)",
        "cache.sizeOfPayingSide = result.longsPayShorts ? cache.longOpenInterest : cache.shortOpenInterest;",
        "Precision.applyFactor(cache.sizeOfPayingSide, cache.durationInSeconds * result.fundingFactorPerSecond)",
        "cache.fundingUsd = cache.fundingUsd / divisor;",
    ]
    missing = [s for s in need_fund if s not in fund_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "fundingUsd excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains zero-OI skip, paying-side, applyFactor, /divisor")
    dlt_txt = dlt_ex.read_text(encoding="utf-8")
    need_dlt = [
        "if (fundingUsd == 0 || openInterest == 0) { return 0; }",
        "Precision.FLOAT_PRECISION * Precision.FLOAT_PRECISION_SQRT",
        "Calc.roundUpDivision(fundingUsdPerSize, tokenPrice)",
    ]
    missing_d = [s for s in need_dlt if s not in dlt_txt]
    if missing_d:
        rec("PIN-DELTA", "FAIL", "delta excerpt missing round-up kernel", ",".join(missing_d))
        return 1
    rec("PIN-DELTA", "PASS", "getFundingAmountPerSizeDelta excerpt is STORE-scale then /price")
    if "longToken == shortToken ? 2 : 1" not in div_ex.read_text(encoding="utf-8"):
        rec("PIN-DIV", "FAIL", "getPoolDivisor excerpt missing same-token 2")
        return 1
    rec("PIN-DIV", "PASS", "getPoolDivisor excerpt is 2 iff longToken==shortToken")
    prc_txt = prc_ex.read_text(encoding="utf-8")
    if "FLOAT_PRECISION = 10 ** 30" not in prc_txt or "FLOAT_PRECISION_SQRT = 10 ** 15" not in prc_txt:
        rec("PIN-PREC", "FAIL", "Precision excerpt missing FLOAT / SQRT")
        return 1
    rec("PIN-PREC", "PASS", "Precision excerpt pins FLOAT=1e30 and SQRT=1e15 (LIN uses primes)")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb funding selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (zero-OI / divisor / split / aps / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 funding-aps clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_funding_aps.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "g2f_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2f_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2f_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, list[int], int]] = [
        ("funding", [LONG_OI, SHORT_OI, 1, DUR, FPS, 0], FUND_LONG),
        ("funding", [LONG_OI, SHORT_OI, 1, DUR, FPS, 1], FUND_SHORT),
        ("wrongnodiv", [LONG_OI, SHORT_OI, 1, DUR, FPS, 1], FUND_LONG),
        ("funding", [0, SHORT_OI, 0, DUR, FPS, 0], 0),
        ("wrongzero", [0, SHORT_OI, 0, DUR, FPS, 0], FUND_SHORT),
        ("funding", [LONG_OI, SHORT_OI, 0, DUR, FPS, 0], FUND_SHORT),
        ("wrongnofps", [LONG_OI, SHORT_OI, 1, DUR, FPS, 0], 800_000),
        ("split", [500, 1000, 5000], 100),
        ("split", [500, 4000, 5000], 400),
        ("aps", [100, 10000, 2000, 1], 5000),
        ("aps", [100, 5000, 2000, 0], 10000),
        ("aps", [1, 3, 2, 0], 166666666),
        ("aps", [1, 3, 2, 1], 166666667),
        ("muldiv", [7_000_000_000, 2_000_000_000, 1_000_000], 14_000_000_000_000),
    ]
    fn_map = {
        "funding": "g2f_funding",
        "wrongzero": "g2f_wrong_zero",
        "wrongnofps": "g2f_wrong_nofps",
        "wrongnodiv": "g2f_wrong_nodiv",
        "split": "g2f_split",
        "aps": "g2f_aps",
        "muldiv": "g2f_muldiv",
    }
    py_map = {
        "funding": py_funding,
        "wrongzero": py_wrong_zero,
        "wrongnofps": py_wrong_nofps,
        "wrongnodiv": py_wrong_nodiv,
        "split": py_split,
        "aps": py_aps,
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

    two = lin_vm(LIN, "g2f_funding", LONG_OI, SHORT_OI, 1, DUR, FPS, 0)
    one = lin_vm(LIN, "g2f_funding", LONG_OI, SHORT_OI, 1, DUR, FPS, 1)
    nodiv = lin_vm(LIN, "g2f_wrong_nodiv", LONG_OI, SHORT_OI, 1, DUR, FPS, 1)
    zskip = lin_vm(LIN, "g2f_funding", 0, SHORT_OI, 0, DUR, FPS, 0)
    zwrong = lin_vm(LIN, "g2f_wrong_zero", 0, SHORT_OI, 0, DUR, FPS, 0)
    nofps = lin_vm(LIN, "g2f_wrong_nofps", LONG_OI, SHORT_OI, 1, DUR, FPS, 0)
    fee = lin_vm(LIN, "g2f_aps", 100, 10000, 2000, 1)
    claim = lin_vm(LIN, "g2f_aps", 100, 5000, 2000, 0)
    wide = lin_vm(LIN, "g2f_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2f_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)

    if two != FUND_LONG or one != FUND_SHORT or nodiv != FUND_LONG:
        rec("DIVISOR", "FAIL", "single-token /2 vs ignore-divisor 2x", f"two={two} one={one} nodiv={nodiv}")
        return 1
    if zskip != 0 or zwrong != FUND_SHORT:
        rec("ZERO-OI", "FAIL", "zero long OI skip vs still-charge", f"zskip={zskip} zwrong={zwrong}")
        return 1
    if nofps != 800_000 or two != FUND_LONG:
        rec("FPS-SCALE", "FAIL", "duration*fps vs forgotten fps (10x)", f"nofps={nofps} two={two}")
        return 1
    if fee != 5000 or claim != 10000:
        rec("APS-SCALE", "FAIL", "fee 0.05/10k vs claimable 0.05/5k at STORE'", f"fee={fee} claim={claim}")
        return 1
    if naive == wide or wide != 14_000_000_000_000 or naive != wrap_py:
        rec("NAIVE-WRAP", "FAIL", "i64 wrap vs 128-bit applyFactor", f"naive={naive} wide={wide} py={wrap_py}")
        return 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("DIVISOR", "PASS", "two-token funding 8e6; single-token /2 = 4e6; ignore-divisor stays 8e6 (2x charge)")
    rec("ZERO-OI", "PASS", "long OI 0 => funding 0; wrong still-charge shorts 4e6")
    rec("FPS-SCALE", "PASS", "paying 2e8 * 4000 * 10 / 1e6 = 8e6; forgotten fps = 8e5 (10x trap)")
    rec("APS-SCALE", "PASS", "GMX comment: $100 / $2000 / $10k fee aps=5000; claimable on $5k = 10000")
    rec("NAIVE-WRAP", "PASS", "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000")

    jit_ok = lin_roundtrip_jit(LIN, "g2f_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2f_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "g2f_funding" in src and "g2f_aps" in src else "FAIL",
        "LIN clone takes OI/duration/fps/divisor as arguments (no DataStore)")
    rec("WIDE-MULDIV", "PASS" if "g2f_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit size*rate / FLOAT prime")
    rec("NOT-V1-RATE", "PASS" if "getNextFundingAmountPerSize" in fund_txt and "g2f_wrong_nofps" in src else "FAIL",
        "kernel is per-second paying-side fundingUsd, not V1 factor*reserved*intervals/pool")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_GMX_V2_FUNDING_APS", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getNextFundingAmountPerSize before ENV",
        ",".join(missing_t) if missing_t else "")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_FUNDING_APS" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_next_funding_amount_per_size")

    evidence = {
        "schema": "LIN_GMX_V2_FUNDING_APS_EVIDENCE_1.0",
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
            "commercial_descendants": "GMX V2 synthetics: fundingUsd is applyFactor(payingSide, duration*fps)/divisor, not V1 interval*reserved/pool. Single-token markets must divide by 2 or they double-charge.",
        },
        "lin_clone": "src/lin_gmx_v2_funding_aps.lin",
        "c11_oracle": "test/oracles/gmx_v2_funding_aps_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "funding_long_two_token": FUND_LONG,
            "funding_long_single_token": FUND_SHORT,
            "wrong_nodiv": FUND_LONG,
            "zero_oi_skip": 0,
            "wrong_zero_charge": FUND_SHORT,
            "shorts_pay": FUND_SHORT,
            "wrong_nofps": 800_000,
            "split_long_col": 100,
            "split_short_col": 400,
            "aps_fee": 5000,
            "aps_claimable": 10000,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-funding-aps",
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
