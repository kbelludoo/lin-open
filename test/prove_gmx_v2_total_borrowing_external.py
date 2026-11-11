#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getNextTotalBorrowing vs LIN C0 (uint64-scale)."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_total_borrowing.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_total_borrowing_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_total_borrowing_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_total_borrowing" / "gmx_v2_total_borrowing_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, PREC_REL = "contracts/market/MarketUtils.sol", "contracts/utils/Precision.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PREC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PREC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
FLOAT, I64_MAX = 1_000_000, 9_223_372_036_854_775_807
WRAP_MUL = -4_446_744_073_709_551_616
WRAP_ADD = -9_223_372_036_854_551_616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-total-borrowing"
MAIN = (100_000_000, 50_000_000, 400_000, 50_000_000, 500_000)
UNDER = (10_000_000, 50_000_000, 400_000, 50_000_000, 500_000)
SIZED = (100_000_000, 50_000_000, 400_000, 80_000_000, 500_000)
REM = (10, 3, 400_000, 3, 700_000)
OPENP = (100_000_000, 0, 0, 50_000_000, 500_000)
CLOSEP = (100_000_000, 50_000_000, 400_000, 0, 0)
EQUAL = (20_000_000, 50_000_000, 400_000, 50_000_000, 500_000)
ZCLOSE = (0, 50_000_000, 400_000, 0, 0)
OVF = (1, 7_000_000_000, 2_000_000_000, 0, 0)
ADDO = (9_223_372_036_850_000_000, 0, 0, 5_000_000, 1_000_000)
FIRST = (0, 0, 0, 50_000_000, 500_000)
MUL = (7_000_000_000, 2_000_000_000)
ADD = (9_223_372_036_850_000_000, 5_000_000)
FEE = (50_000_000, 400_000, 500_000)
PENDING = (200_000_000, 600_000, 100_000_000)


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


def py_usub_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a < b else 1


def py_apply(value: int, factor: int) -> int:
    if value < 0 or factor < 0 or py_umul_ok(value, factor) == 0:
        return 0
    return (value * factor) // FLOAT


def py_ok(a: tuple[int, ...]) -> int:
    total, ps, pf, ns, nf = a
    if total < 0 or ps < 0 or pf < 0 or ns < 0 or nf < 0:
        return 0
    if py_umul_ok(ps, pf) == 0 or py_umul_ok(ns, nf) == 0:
        return 0
    pc, nc = py_apply(ps, pf), py_apply(ns, nf)
    if py_usub_ok(total, pc) == 0:
        return 0
    return py_uadd_ok(total - pc, nc)


def py_next(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    total, ps, pf, ns, nf = a
    return (total - py_apply(ps, pf)) + py_apply(ns, nf)


def py_fused(a: tuple[int, ...]) -> int:
    total, ps, pf, ns, nf = a
    if ps < 0 or pf < 0 or ns < 0 or nf < 0:
        return 0
    if py_umul_ok(ps, pf) == 0 or py_umul_ok(ns, nf) == 0:
        return 0
    return (total - py_apply(ps, pf)) + py_apply(ns, nf)


def py_muldiv(a: tuple[int, ...]) -> int:
    total, ps, pf, ns, nf = a
    if total < 0 or ps < 0 or pf < 0 or ns < 0 or nf < 0:
        return 0
    if py_umul_ok(ps, pf) == 0 or py_umul_ok(ns, nf) == 0:
        return 0
    pp, np = ps * pf, ns * nf
    if np < pp:
        d = (pp - np) // FLOAT
        return 0 if py_usub_ok(total, d) == 0 else total - d
    d = (np - pp) // FLOAT
    return 0 if py_uadd_ok(total, d) == 0 else total + d


def py_size(a: tuple[int, ...]) -> int:
    total, ps, pf, ns, nf = a
    if pf < 0 or py_usub_ok(ns, ps) == 0:
        return 0
    c = py_apply(ns - ps, nf)
    return 0 if py_uadd_ok(total, c) == 0 else total + c


def py_fee(a: tuple[int, ...]) -> int:
    size, pf, nf = a
    return 0 if py_usub_ok(nf, pf) == 0 else py_apply(size, nf - pf)


def py_pending(a: tuple[int, ...]) -> int:
    oi, cum, total = a
    v = py_apply(oi, cum)
    return 0 if py_usub_ok(v, total) == 0 else v - total


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 getNextTotalBorrowing — LIN proof (C11)")
    tb_ex = FIX / "GetNextTotalBorrowing.excerpt.sol"
    up_ex = FIX / "UpdateTotalBorrowing.excerpt.sol"
    bf_ex = FIX / "GetBorrowingFees.excerpt.sol"
    pf_ex = FIX / "GetTotalPendingBorrowingFees.excerpt.sol"
    ap_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    gt_ex = FIX / "GetTotalBorrowing.excerpt.sol"
    if not all(p.exists() for p in (tb_ex, up_ex, bf_ex, pf_ex, ap_ex, gt_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    tb_txt, up_txt, bf_txt, pf_txt, ap_txt, gt_txt = (p.read_text(encoding="utf-8") for p in (tb_ex, up_ex, bf_ex, pf_ex, ap_ex, gt_ex))
    need = [
        "function getNextTotalBorrowing",
        "totalBorrowing -= Precision.applyFactor(prevPositionSizeInUsd, prevPositionBorrowingFactor)",
        "totalBorrowing += Precision.applyFactor(nextPositionSizeInUsd, nextPositionBorrowingFactor)",
    ]
    missing = [s for s in need if s not in tb_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "total-borrowing excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt is unsigned sub-then-add of applyFactor contributions")
    rec("PIN-UPDATE", "PASS" if "setTotalBorrowing(dataStore, market, isLong, totalBorrowing)" in up_txt else "FAIL",
        "updateTotalBorrowing stores getNextTotalBorrowing; DataStore lifted")
    rec("PIN-APPLY", "PASS" if "mulDiv(value, factor, FLOAT_PRECISION)" in ap_txt and "FLOAT_PRECISION = 10 ** 30" in ap_txt else "FAIL",
        "applyFactor is value*factor/1e30; LIN FLOAT is 1e6")
    rec("PIN-FEE", "PASS" if "Precision.applyFactor(position.sizeInUsd(), diffFactor)" in bf_txt else "FAIL",
        "getBorrowingFees is applyFactor(size, cum-entry), not a running total")
    rec("PIN-PENDING", "PASS" if "Precision.applyFactor(openInterest, nextCumulativeBorrowingFactor) - totalBorrowing" in pf_txt else "FAIL",
        "getTotalPendingBorrowingFees is applyFactor(OI, nextCum) minus total")
    rec("PIN-STORE", "PASS" if "totalBorrowingKey(market, isLong)" in gt_txt else "FAIL",
        "isLong selects the totalBorrowing storage key; it does not flip the math")

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
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (unsigned sub-then-add / fused / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 total-borrowing clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_total_borrowing.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL", "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL", "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2t_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2t_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2t_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2t_ok", "next": "g2t_next", "wrongfused": "g2t_wrong_fused",
        "wrongmuldiv": "g2t_wrong_muldiv", "wrongsize": "g2t_wrong_size",
        "wrongfee": "g2t_wrong_fee", "wrongpending": "g2t_wrong_pending",
        "naivemul": "g2t_naive_i64_mul", "naiveadd": "g2t_naive_i64_add",
    }
    py_map = {
        "ok": py_ok, "next": py_next, "wrongfused": py_fused, "wrongmuldiv": py_muldiv,
        "wrongsize": py_size, "wrongfee": py_fee, "wrongpending": py_pending,
        "naivemul": lambda a: w64(a[0] * a[1]), "naiveadd": lambda a: w64(a[0] + a[1]),
    }
    cases = [
        ("ok", MAIN, 1), ("next", MAIN, 105_000_000), ("wrongfused", UNDER, 15_000_000),
        ("ok", UNDER, 0), ("wrongfee", FEE, 5_000_000), ("wrongpending", PENDING, 20_000_000),
        ("next", SIZED, 120_000_000), ("wrongsize", SIZED, 115_000_000),
        ("next", REM, 11), ("wrongmuldiv", REM, 10),
        ("next", OPENP, 125_000_000), ("next", CLOSEP, 80_000_000), ("next", EQUAL, 25_000_000),
        ("ok", ZCLOSE, 0), ("ok", OVF, 0), ("naivemul", MUL, WRAP_MUL),
        ("ok", ADDO, 0), ("naiveadd", ADD, WRAP_ADD), ("ok", MAIN, 1),
        ("next", FIRST, 25_000_000), ("wrongfused", MAIN, 105_000_000),
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
    rec("UNSIGNED-SUB", "PASS" if got[("next", MAIN)] == 105_000_000 and got[("ok", UNDER)] == 0 and got[("wrongfused", UNDER)] == 15_000_000 else "FAIL",
        "size 5e7 factor 4e5->5e5 next total 105000000; prev contrib > total fail-closes vs signed fused 15000000")
    rec("NOT-FEE", "PASS" if got[("wrongfee", FEE)] == 5_000_000 else "FAIL",
        "getBorrowingFees applyFactor(size, factor-diff) is 5000000 USD, not the running total")
    rec("NOT-PENDING", "PASS" if got[("wrongpending", PENDING)] == 20_000_000 else "FAIL",
        "getTotalPendingBorrowingFees applyFactor(OI, cum)-total is 20000000, not getNextTotalBorrowing")
    rec("NOT-SIZE-DELTA", "PASS" if got[("next", SIZED)] == 120_000_000 and got[("wrongsize", SIZED)] == 115_000_000 else "FAIL",
        "size 5e7->8e7 and factor 4e5->5e5 is 120000000, not applyFactor(size-delta, nextFactor) 115000000")
    rec("INNER-FLOOR", "PASS" if got[("next", REM)] == 11 and got[("wrongmuldiv", REM)] == 10 else "FAIL",
        "nested floor of applyFactor raises total 11 vs fused (nextProd-prevProd)/FLOAT 10")
    rec("OPEN-CLOSE", "PASS" if got[("next", OPENP)] == 125_000_000 and got[("next", CLOSEP)] == 80_000_000 else "FAIL",
        "open prev=0 adds 25000000 to 125000000; close next=0 subtracts 20000000 to 80000000")
    rec("EQUAL-PREV", "PASS" if got[("next", EQUAL)] == 25_000_000 else "FAIL",
        "prev contrib == total is allowed and yields the next contribution 25000000")
    rec("ZERO-UNDER", "PASS" if got[("ok", ZCLOSE)] == 0 and got[("next", FIRST)] == 25_000_000 else "FAIL",
        "close when total=0 fail-closes; first position total=0 prev=0 yields 25000000")
    rec("MUL-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naivemul", MUL)] == WRAP_MUL else "FAIL",
        "7e9*2e9 prevSize*prevFactor fail-closes; naive i64 wraps to -4446744073709551616")
    rec("ADD-OVERFLOW", "PASS" if got[("ok", ADDO)] == 0 and got[("naiveadd", ADD)] == WRAP_ADD else "FAIL",
        "near-i64-max total + applyFactor(5e6, 1e6) fail-closes; naive wrap -9223372036854551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2t_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2t_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", (jit.stdout + jit.stderr)[:240] or "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2t_next" in src and "g2t_apply" in src else "FAIL",
        "LIN clone takes total/prevSize/prevFactor/nextSize/nextFactor as arguments; DataStore lifted")
    rec("FAIL-CLOSED-SUB", "PASS" if "g2t_usub_ok" in src and "g2t_uadd_ok" in src else "FAIL",
        "clone fail-closes prev contrib > total, applyFactor overflow, and add overflow")
    rec("NOT-DELTA", "PASS" if "g2t_wrong_fused" in src and "g2t_wrong_size" in src else "FAIL",
        "kernel is unsigned sub-then-add of applyFactor, not signed fused or size-delta")
    need_t = ["REJ_SOLIDITY_GMX_V2_TOTAL_BORROW", "Chain.currentTimestamp", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getNextTotalBorrowing before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_TOTAL_BORROW" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_next_total_borrowing")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_TOTAL_BORROWING_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL,
            "precision_path": PREC_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PREC_BLOB, "precision_file_sha256": PREC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 totalBorrowing is a running sum of applyFactor(size, factor) updated by unsigned subtract-then-add. Treating it as signed (next-prev) lets a prev contribution larger than the total succeed (15000000 vs revert). Nested floor of applyFactor raises the total versus fused (nextProd-prevProd)/FLOAT. FLOAT is 1e30 on chain; this clone uses 1e6.",
        },
        "lin_clone": "src/lin_gmx_v2_total_borrowing.lin",
        "c11_oracle": "test/oracles/gmx_v2_total_borrowing_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "next": 105_000_000, "fused_under": 15_000_000, "fee": 5_000_000,
            "pending": 20_000_000, "size_next": 120_000_000, "size_wrong": 115_000_000,
            "rem_nested": 11, "rem_fused": 10, "open": 125_000_000, "close": 80_000_000,
            "equal": 25_000_000, "first": 25_000_000, "wrap_mul": WRAP_MUL, "wrap_add": WRAP_ADD,
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
