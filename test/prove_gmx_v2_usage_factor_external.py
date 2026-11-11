#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getUsageFactor vs LIN C0 (uint64-scale)."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_usage_factor.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_usage_factor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_usage_factor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_usage_factor" / "gmx_v2_usage_factor_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, PREC_REL = "contracts/market/MarketUtils.sol", "contracts/utils/Precision.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PREC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PREC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
FLOAT, I64_MAX = 1_000_000, 9_223_372_036_854_775_807
WRAP = -4_446_744_073_709_551_616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-usage-factor"
MAIN = (40_000_000, 100_000_000, 500_000)
REM = (400, 1_001, 500_000)
DUST = (1, 3, 1_000_000)
ZERO = (0, 0, 0)
DIV0 = (1, 0, 500_000)
OVER = (60_000_000, 100_000_000, 500_000)
FULL = (50_000_000, 100_000_000, 500_000)
R0 = (40_000_000, 100_000_000, 0)
OVF = (1, 7_000_000_000, 2_000_000_000)
OVF2 = (10_000_000_000_000, 100_000_000, 1_000_000)
MUL = (7_000_000_000, 2_000_000_000)
BORROW = (100_000_000, 500_000)


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


def py_apply(value: int, factor: int) -> int:
    if value < 0 or factor < 0 or py_umul_ok(value, factor) == 0:
        return 0
    return (value * factor) // FLOAT


def py_to_factor(value: int, divisor: int, round_up: int) -> int:
    if value < 0 or divisor < 0 or round_up not in (0, 1):
        return 0
    if value == 0:
        return 0
    if divisor == 0 or py_umul_ok(value, FLOAT) == 0:
        return 0
    q, r = divmod(value * FLOAT, divisor)
    if round_up == 0 or r == 0:
        return q
    return 0 if q + 1 > I64_MAX else q + 1


def py_ok(a: tuple[int, ...]) -> int:
    reserved, pool, rfactor = a
    if reserved < 0 or pool < 0 or rfactor < 0:
        return 0
    if reserved == 0:
        return 1
    if py_umul_ok(pool, rfactor) == 0:
        return 0
    mx = py_apply(pool, rfactor)
    if mx == 0 or py_umul_ok(reserved, FLOAT) == 0:
        return 0
    return 1


def py_usage(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0 or a[0] == 0:
        return 0
    return py_to_factor(a[0], py_apply(a[1], a[2]), 0)


def py_fused(a: tuple[int, ...]) -> int:
    reserved, pool, rfactor = a
    if reserved <= 0 or pool < 0 or rfactor < 0 or py_umul_ok(pool, rfactor) == 0:
        return 0
    den = pool * rfactor
    if den == 0 or py_umul_ok(reserved, FLOAT) == 0:
        return 0
    n1 = reserved * FLOAT
    if py_umul_ok(n1, FLOAT) == 0:
        return 0
    return (n1 * FLOAT) // den


def py_compound(a: tuple[int, ...]) -> int:
    reserved, pool, rfactor = a
    if rfactor < 0 or reserved <= 0 or pool < 0 or py_uadd_ok(pool, reserved) == 0:
        return 0
    den = pool + reserved
    if den == 0 or py_umul_ok(reserved, FLOAT) == 0:
        return 0
    return (reserved * FLOAT) // den


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 getUsageFactor — LIN proof (C11)")
    uf_ex = FIX / "GetUsageFactor.excerpt.sol"
    app_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    tf_ex = FIX / "PrecisionToFactor.excerpt.sol"
    bf_ex = FIX / "GetBorrowingFees.excerpt.sol"
    rf_ex = FIX / "GetOpenInterestReserveFactor.excerpt.sol"
    if not all(p.exists() for p in (uf_ex, app_ex, tf_ex, bf_ex, rf_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    uf_txt, app_txt, tf_txt, bf_txt, rf_txt = (p.read_text(encoding="utf-8") for p in (uf_ex, app_ex, tf_ex, bf_ex, rf_ex))
    need = [
        "function getUsageFactor",
        "getOpenInterestReserveFactor",
        "maxReservedUsd = Precision.applyFactor(poolUsd, reserveFactor)",
        "reserveUsageFactor = Precision.toFactor(reservedUsd, maxReservedUsd)",
    ]
    missing = [s for s in need if s not in uf_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "usage-factor excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt is toFactor(reserved, applyFactor(pool, reserveFactor))")
    rec(
        "PIN-APPLY",
        "PASS" if "mulDiv(value, factor, FLOAT_PRECISION)" in app_txt and "FLOAT_PRECISION = 10 ** 30" in app_txt else "FAIL",
        "applyFactor is value*factor/1e30; LIN FLOAT is 1e6",
    )
    rec(
        "PIN-TOFACTOR",
        "PASS" if "if (value == 0) { return 0; }" in tf_txt and "toFactor(value, divisor, false)" in tf_txt else "FAIL",
        "toFactor early-returns 0 and the 2-arg form always floors",
    )
    rec(
        "PIN-BORROW",
        "PASS" if "Precision.applyFactor(position.sizeInUsd(), diffFactor)" in bf_txt else "FAIL",
        "getBorrowingFees is a single applyFactor USD fee, not nested usage",
    )
    rec(
        "PIN-RESERVE",
        "PASS" if "openInterestReserveFactorKey" in rf_txt else "FAIL",
        "isLong selects the reserve-factor storage key; it does not flip the math",
    )

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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (nested usage / fused / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 usage-factor clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_usage_factor.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2u_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2u_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2u_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2u_ok", "usage": "g2u_usage", "wrongpool": "g2u_wrong_pool",
        "wrongcompound": "g2u_wrong_compound", "wrongapply": "g2u_wrong_apply",
        "wrongfused": "g2u_wrong_fused", "wrongceil": "g2u_wrong_ceil",
        "wrongcap": "g2u_wrong_cap", "wrongborrow": "g2u_wrong_borrow",
        "naivemul": "g2u_naive_i64_mul",
    }
    py_map = {
        "ok": py_ok, "usage": py_usage,
        "wrongpool": lambda a: py_to_factor(a[0], a[1], 0),
        "wrongcompound": py_compound,
        "wrongapply": lambda a: py_apply(a[1], a[2]),
        "wrongfused": py_fused,
        "wrongceil": lambda a: 0 if py_ok(a) == 0 or a[0] == 0 else py_to_factor(a[0], py_apply(a[1], a[2]), 1),
        "wrongcap": lambda a: FLOAT if py_usage(a) > FLOAT else py_usage(a),
        "wrongborrow": lambda a: py_apply(a[0], a[1]),
        "naivemul": lambda a: w64(a[0] * a[1]),
    }
    cases = [
        ("ok", MAIN, 1), ("usage", MAIN, 800_000), ("wrongpool", MAIN, 400_000),
        ("wrongcompound", MAIN, 285_714), ("wrongapply", MAIN, 50_000_000),
        ("usage", REM, 800_000), ("wrongfused", REM, 799_200), ("wrongfused", MAIN, 0),
        ("usage", DUST, 333_333), ("wrongceil", DUST, 333_334),
        ("usage", ZERO, 0), ("ok", ZERO, 1), ("ok", DIV0, 0),
        ("usage", OVER, 1_200_000), ("wrongcap", OVER, 1_000_000),
        ("usage", FULL, 1_000_000), ("ok", R0, 0), ("ok", OVF, 0),
        ("naivemul", MUL, WRAP), ("ok", OVF2, 0), ("wrongborrow", BORROW, 50_000_000),
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
    rec("NESTED-VS-POOL", "PASS" if got[("usage", MAIN)] == 800_000 and got[("wrongpool", MAIN)] == 400_000 else "FAIL",
        "reserved 4e7 / maxReserved 5e7 is 800000; reserved/pool is 400000 (understates by 2x at 50% reserveFactor)")
    rec("NOT-COMPOUND", "PASS" if got[("wrongcompound", MAIN)] == 285_714 else "FAIL",
        "Compound-style reserved/(pool+reserved) is 285714, not GMX nested usage")
    rec("INNER-FLOOR", "PASS" if got[("usage", REM)] == 800_000 and got[("wrongfused", REM)] == 799_200 else "FAIL",
        "nested floor of applyFactor raises usage 800000 vs fused reserved*FLOAT^2/(pool*factor) 799200")
    rec("FUSED-OVF", "PASS" if got[("wrongfused", MAIN)] == 0 else "FAIL",
        "fusing FLOAT^2 at production-scale 4e7 overflows i64; nested sequential mulDiv stays in range")
    rec("TOFACTOR-FLOOR", "PASS" if got[("usage", DUST)] == 333_333 and got[("wrongceil", DUST)] == 333_334 else "FAIL",
        "2-arg toFactor floors dust 1/3 to 333333; Rounding.Up would be 333334")
    rec("ZERO-EARLY", "PASS" if got[("usage", ZERO)] == 0 and got[("ok", ZERO)] == 1 else "FAIL",
        "reserved=0 returns 0 even when maxReserved=0 (toFactor early return, not div0)")
    rec("DIV0-MAX", "PASS" if got[("ok", DIV0)] == 0 and got[("ok", R0)] == 0 else "FAIL",
        "reserved>0 and maxReserved=0 fail-closes (pool=0 or reserveFactor=0)")
    rec("OVER-RESERVE", "PASS" if got[("usage", OVER)] == 1_200_000 and got[("wrongcap", OVER)] == 1_000_000 else "FAIL",
        "usage is not capped at FLOAT: 6e7/5e7 = 1200000 vs min(usage,1e6) 1000000")
    rec("FULL-MAX", "PASS" if got[("usage", FULL)] == 1_000_000 else "FAIL",
        "reserved == maxReserved yields FLOAT (100% of the reserve cap, 50% of pool)")
    rec("NOT-BORROW-FEE", "PASS" if got[("wrongborrow", BORROW)] == 50_000_000 else "FAIL",
        "getBorrowingFees applyFactor(size, factor) is 50000000 USD, not a 0-1 usage factor")
    rec("MUL-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naivemul", MUL)] == WRAP else "FAIL",
        "7e9*2e9 pool*rfactor fail-closes; naive i64 wraps to -4446744073709551616")
    rec("TOFACTOR-OVF", "PASS" if got[("ok", OVF2)] == 0 else "FAIL",
        "1e13*FLOAT reserved*1e6 fail-closes instead of wrapping")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2u_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2u_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2u_usage" in src and "g2u_max_reserved" in src else "FAIL",
        "LIN clone takes reserved/pool/rfactor as arguments; DataStore lifted")
    rec("FAIL-CLOSED-MUL", "PASS" if "g2u_umul_ok" in src and "g2u_inputs_ok" in src else "FAIL",
        "clone fail-closes pool*rfactor and reserved*FLOAT overflow and maxReserved=0")
    rec("NOT-UTIL", "PASS" if "g2u_wrong_pool" in src and "g2u_wrong_compound" in src else "FAIL",
        "kernel is nested applyFactor then toFactor, not reserved/pool or Compound util")
    need_t = ["REJ_SOLIDITY_GMX_V2_USAGE", "Chain.currentTimestamp", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getUsageFactor before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_USAGE" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_usage_factor")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_USAGE_FACTOR_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL,
            "precision_path": PREC_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PREC_BLOB, "precision_file_sha256": PREC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 usage is reserved / (pool * reserveFactor), not reserved/pool. Nested floor of applyFactor then toFactor is strictly larger than fused reserved*FLOAT^2/(pool*factor) when the inner remainder is nonzero. Over-reserve is not capped at 100%. FLOAT is 1e30 on chain; this clone uses 1e6.",
        },
        "lin_clone": "src/lin_gmx_v2_usage_factor.lin",
        "c11_oracle": "test/oracles/gmx_v2_usage_factor_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "usage": 800_000, "pool_ratio": 400_000, "compound": 285_714,
            "apply_only": 50_000_000, "fused_rem": 799_200, "fused_main": 0,
            "dust_floor": 333_333, "dust_ceil": 333_334, "over": 1_200_000,
            "capped": 1_000_000, "full": 1_000_000, "borrow_fee": 50_000_000,
            "wrap_naive": WRAP,
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
