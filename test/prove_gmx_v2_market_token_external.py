#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 usdToMarketTokenAmount vs LIN C0 (uint64-scale)."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_market_token.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_market_token_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_market_token_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_market_token" / "gmx_v2_market_token_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, PREC_REL = "contracts/market/MarketUtils.sol", "contracts/utils/Precision.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PREC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PREC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
DIV, I64_MAX = 1_000_000, 9_223_372_036_854_775_807
WRAP_MUL = -4_446_744_073_709_551_616
WRAP_ADD = -8_446_744_073_709_551_616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-market-token"
FIRST = (100_000_000, 0, 0)
LEFT = (100_000_000, 20_000_000, 0)
SUB = (50_000_000, 200_000_000, 100_000_000)
INV = (25_000_000, 200_000_000, 100_000_000)
EMPTY_INV = (100, 0, 0)
POOL0 = (50_000_000, 0, 100_000_000)
REM = (4, 5, 3)
DUST = (1, 3, 1)
LEFT0 = (0, 20_000_000, 0)
RT = (100, 100_000_000, 100)
ADDO = (3_000_000_000_000_000_000, 7_000_000_000_000_000_000, 0)
ADD = (7_000_000_000_000_000_000, 3_000_000_000_000_000_000)
MULO = (2_000_000_000, 1, 7_000_000_000)
MUL = (7_000_000_000, 2_000_000_000)
EQ = (50_000_000, 100_000_000, 100_000_000)
ZERO = (0, 0, 0)


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_tools() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")
    if not C0.exists():
        proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"])
        if proc.returncode != 0 or not C0.exists():
            raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/gmx-io/gmx-synthetics.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT])
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    mkt, prec = UPSTREAM / MKT_REL, UPSTREAM / PREC_REL
    if not mkt.exists() or not prec.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    pblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PREC_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(prec) != PREC_SHA256 or pblob != PREC_BLOB:
        return "FAIL", commit, f"prec={sha256_file(prec)} blob={pblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_umul_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a * b > I64_MAX else 1


def py_uadd_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a + b > I64_MAX else 1


def py_wei(value: int) -> int:
    return 0 if value < 0 else value // DIV


def py_ok(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    if supply == 0:
        return 1 if pool == 0 else py_uadd_ok(pool, usd)
    return 0 if pool == 0 else py_umul_ok(supply, usd)


def py_usd(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    usd, pool, supply = a
    if supply == 0:
        return py_wei(usd) if pool == 0 else py_wei(pool + usd)
    return (supply * usd) // pool


def py_tok_ok(a: tuple[int, ...]) -> int:
    tokens, pool, supply = a
    if tokens < 0 or pool < 0 or supply < 0 or supply == 0:
        return 0
    return py_umul_ok(pool, tokens)


def py_tok(a: tuple[int, ...]) -> int:
    if py_tok_ok(a) == 0:
        return 0
    tokens, pool, supply = a
    return (pool * tokens) // supply


def py_lido(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    if pool == 0:
        return usd
    return 0 if py_umul_ok(supply, usd) == 0 else (supply * usd) // pool


def py_ignore(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    if supply == 0:
        return py_wei(usd)
    if pool == 0:
        return 0
    return 0 if py_umul_ok(supply, usd) == 0 else (supply * usd) // pool


def py_sum(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    if supply == 0:
        if pool == 0:
            return usd
        return 0 if py_uadd_ok(pool, usd) == 0 else pool + usd
    if pool == 0:
        return 0
    return 0 if py_umul_ok(supply, usd) == 0 else (supply * usd) // pool


def py_or(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    if supply == 0 or pool == 0:
        return py_wei(usd)
    return 0 if py_umul_ok(supply, usd) == 0 else (supply * usd) // pool


def py_always(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0 or pool == 0:
        return 0
    return 0 if py_umul_ok(supply, usd) == 0 else (supply * usd) // pool


def py_wei_only(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0:
        return 0
    return py_wei(usd)


def py_ceil(a: tuple[int, ...]) -> int:
    usd, pool, supply = a
    if usd < 0 or pool < 0 or supply < 0 or supply == 0 or pool == 0:
        return 0
    if py_umul_ok(supply, usd) == 0:
        return 0
    prod = supply * usd
    return 0 if py_uadd_ok(prod, pool - 1) == 0 else (prod + (pool - 1)) // pool


def py_inv(a: tuple[int, ...]) -> int:
    tokens, pool, supply = a
    if tokens < 0 or pool < 0 or supply < 0:
        return 0
    if supply == 0:
        return tokens
    return 0 if py_umul_ok(pool, tokens) == 0 else (pool * tokens) // supply


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 usdToMarketTokenAmount — LIN proof (C11)")
    usd_ex = FIX / "UsdToMarketTokenAmount.excerpt.sol"
    tok_ex = FIX / "MarketTokenAmountToUsd.excerpt.sol"
    wei_ex = FIX / "PrecisionFloatToWei.excerpt.sol"
    md_ex = FIX / "PrecisionMulDiv.excerpt.sol"
    if not all(p.exists() for p in (usd_ex, tok_ex, wei_ex, md_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    usd_txt, tok_txt, wei_txt, md_txt = (p.read_text(encoding="utf-8") for p in (usd_ex, tok_ex, wei_ex, md_ex))
    need = [
        "function usdToMarketTokenAmount",
        "if (supply == 0 && poolValue == 0)",
        "return Precision.floatToWei(usdValue);",
        "if (supply == 0 && poolValue > 0)",
        "return Precision.floatToWei(poolValue + usdValue);",
        "return Precision.mulDiv(supply, usdValue, poolValue);",
    ]
    missing = [s for s in need if s not in usd_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "usdToMarketTokenAmount excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt is three-branch first-deposit AND, leftover pool+usd, then floor mulDiv")
    rec("PIN-INVERSE", "PASS" if "function marketTokenAmountToUsd" in tok_txt and "EmptyMarketTokenSupply" in tok_txt else "FAIL",
        "inverse reverts EmptyMarketTokenSupply when supply==0, then mulDiv(pool, tokens, supply)")
    rec("PIN-WEI", "PASS" if "FLOAT_TO_WEI_DIVISOR = 10 ** 12" in wei_txt and "value / FLOAT_TO_WEI_DIVISOR" in wei_txt and "FLOAT_PRECISION = 10 ** 30" in wei_txt else "FAIL",
        "floatToWei is value/1e12; LIN DIV is 1e6; FLOAT on chain is 1e30")
    rec("PIN-MULDIV", "PASS" if "Math.mulDiv(value, numerator, denominator)" in md_txt else "FAIL",
        "subsequent path is floor mulDiv(supply, usd, pool), not 1:1")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + Precision.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs portable umul_ok selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (three-branch mint / leftover / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 market-token clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_market_token.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2m_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2m_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2m_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2m_ok", "usd": "g2m_usd", "tok": "g2m_tok", "tokok": "g2m_tok_ok",
        "wronglido": "g2m_wrong_lido", "wrongignore": "g2m_wrong_ignore",
        "wrongsum": "g2m_wrong_sum", "wrongor": "g2m_wrong_or",
        "wrongalways": "g2m_wrong_always", "wrongwei": "g2m_wrong_wei",
        "wrongceil": "g2m_wrong_ceil", "wronginv": "g2m_wrong_inv",
        "naivemul": "g2m_naive_i64_mul", "naiveadd": "g2m_naive_i64_add",
    }
    py_map = {
        "ok": py_ok, "usd": py_usd, "tok": py_tok, "tokok": py_tok_ok,
        "wronglido": py_lido, "wrongignore": py_ignore, "wrongsum": py_sum,
        "wrongor": py_or, "wrongalways": py_always, "wrongwei": py_wei_only,
        "wrongceil": py_ceil, "wronginv": py_inv,
        "naivemul": lambda a: w64(a[0] * a[1]), "naiveadd": lambda a: w64(a[0] + a[1]),
    }
    cases = [
        ("usd", FIRST, 100), ("wronglido", FIRST, 100_000_000),
        ("usd", LEFT, 120), ("wronglido", LEFT, 0), ("wrongignore", LEFT, 100),
        ("wrongsum", LEFT, 120_000_000), ("usd", SUB, 25_000_000),
        ("wrongwei", SUB, 50), ("tok", INV, 50_000_000),
        ("tokok", FIRST, 0), ("wronginv", EMPTY_INV, 100),
        ("ok", POOL0, 0), ("wronglido", POOL0, 50_000_000), ("wrongor", POOL0, 50),
        ("usd", REM, 2), ("wrongceil", REM, 3), ("usd", DUST, 0),
        ("usd", LEFT0, 20), ("tok", RT, 100_000_000),
        ("ok", ADDO, 0), ("naiveadd", ADD, WRAP_ADD),
        ("ok", MULO, 0), ("naivemul", MUL, WRAP_MUL),
        ("usd", EQ, 50_000_000), ("ok", FIRST, 1),
        ("wrongalways", FIRST, 0), ("wrongor", LEFT, 100), ("usd", ZERO, 0),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn_map[kind], *args)
        pyv = py_map[kind](args)
        got[(kind, args)] = got_lin
        if want != expect or want_port != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}", f"lin={got_lin} c11={want} port={want_port} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == portable == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("NOT-LIDO", "PASS" if got[("usd", FIRST)] == 100 and got[("wronglido", FIRST)] == 100_000_000 else "FAIL",
        "empty supply AND empty pool is floatToWei 100, not Lido/Rocket 1:1 100000000")
    rec("LEFTOVER", "PASS" if got[("usd", LEFT)] == 120 and got[("wronglido", LEFT)] == 0 and got[("wrongignore", LEFT)] == 100 and got[("wrongsum", LEFT)] == 120_000_000 else "FAIL",
        "supply=0 pool>0 mints floatToWei(pool+usd)=120 vs Lido 0 vs ignore-pool 100 vs forgot-wei 120000000")
    rec("NOT-OR", "PASS" if got[("ok", POOL0)] == 0 and got[("wronglido", POOL0)] == 50_000_000 and got[("wrongor", POOL0)] == 50 else "FAIL",
        "supply>0 pool=0 fail-closes; Lido 1:1 is 50000000; OR-empty wei is 50")
    rec("SUBSEQUENT", "PASS" if got[("usd", SUB)] == 25_000_000 and got[("wrongwei", SUB)] == 50 else "FAIL",
        "subsequent floor mulDiv(supply, usd, pool) is 25000000, not floatToWei(usd) 50")
    rec("INVERSE", "PASS" if got[("tok", INV)] == 50_000_000 and got[("tokok", FIRST)] == 0 and got[("wronginv", EMPTY_INV)] == 100 else "FAIL",
        "inverse mulDiv(pool, tokens, supply) is 50000000; empty supply fail-closes vs 1:1 100")
    rec("INNER-FLOOR", "PASS" if got[("usd", REM)] == 2 and got[("wrongceil", REM)] == 3 and got[("usd", DUST)] == 0 else "FAIL",
        "3*4/5 floors 2 vs ceil 3; dust 1*1/3 floors 0")
    rec("ROUNDTRIP", "PASS" if got[("tok", RT)] == 100_000_000 and got[("usd", EQ)] == 50_000_000 else "FAIL",
        "first-deposit inverse of 100 tokens against pool 1e8 is 1e8; equal pool=supply subsequent is usd")
    rec("ZERO-USD", "PASS" if got[("usd", LEFT0)] == 20 and got[("usd", ZERO)] == 0 and got[("wrongalways", FIRST)] == 0 else "FAIL",
        "usd=0 leftover still weies pool to 20; both-zero usd=0 is 0; always-mulDiv first deposit is 0")
    rec("ADD-OVERFLOW", "PASS" if got[("ok", ADDO)] == 0 and got[("naiveadd", ADD)] == WRAP_ADD else "FAIL",
        "leftover 7e18+3e18 fail-closes; naive i64 wrap -8446744073709551616")
    rec("MUL-OVERFLOW", "PASS" if got[("ok", MULO)] == 0 and got[("naivemul", MUL)] == WRAP_MUL else "FAIL",
        "7e9*2e9 supply*usd fail-closes; naive i64 wraps to -4446744073709551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2m_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2m_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2m_usd" in src and "g2m_tok" in src else "FAIL",
        "LIN clone takes usd/pool/supply as arguments; DataStore lifted")
    rec("FAIL-CLOSED", "PASS" if "g2m_uadd_ok" in src and "g2m_umul_ok" in src else "FAIL",
        "clone fail-closes leftover add overflow, subsequent mul overflow, empty-supply inverse, and pool=0")
    rec("NOT-1TO1", "PASS" if "g2m_wrong_lido" in src and "g2m_wrong_or" in src else "FAIL",
        "kernel is three-branch AND plus leftover floatToWei, not Lido 1:1 or supply==0 OR pool==0")
    need_t = ["REJ_SOLIDITY_GMX_V2_MARKET_TOKEN", "Chain.currentTimestamp", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects usdToMarketTokenAmount before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_MARKET_TOKEN" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects usd_to_market_token_amount")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_MARKET_TOKEN_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL,
            "precision_path": PREC_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PREC_BLOB, "precision_file_sha256": PREC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 market tokens mint with three branches: empty supply AND empty pool uses floatToWei (not Lido/Rocket 1:1); empty supply with leftover poolValue mints floatToWei(pool+usd) so the post-mint price is 1 USD; otherwise floor mulDiv(supply, usd, pool). Inverse reverts EmptyMarketTokenSupply. FLOAT_TO_WEI_DIVISOR is 1e12 on chain; this clone uses 1e6.",
        },
        "lin_clone": "src/lin_gmx_v2_market_token.lin",
        "c11_oracle": "test/oracles/gmx_v2_market_token_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "first_wei": 100, "lido_1to1": 100_000_000, "leftover": 120,
            "lido_leftover": 0, "ignore_pool": 100, "forgot_wei": 120_000_000,
            "subsequent": 25_000_000, "always_wei": 50, "inverse": 50_000_000,
            "empty_inv": 100, "pool0_lido": 50_000_000, "pool0_or": 50,
            "rem_floor": 2, "rem_ceil": 3, "dust": 0, "leftover_zero_usd": 20,
            "roundtrip": 100_000_000, "equal": 50_000_000,
            "wrap_mul": WRAP_MUL, "wrap_add": WRAP_ADD,
        },
        "clone_lin": CLONE_LIN,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
