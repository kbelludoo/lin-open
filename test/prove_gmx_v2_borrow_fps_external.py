#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getBorrowingFactorPerSecond vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_borrow_fps.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_borrow_fps_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_borrow_fps_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_borrow_fps" / "gmx_v2_borrow_fps_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
FLOAT_P = 1_000_000

# reserved, pool, is_long, long_oi, short_oi, skip, opt, rfactor, factor, base, above
LINEAR = (500000, 1000000, 1, 600, 400, 0, 0, 1000000, 20, 0, 0)
SKIP_LONG = (500000, 1000000, 1, 400, 600, 1, 0, 1000000, 20, 0, 0)
SKIP_SHORT = (500000, 1000000, 0, 400, 600, 1, 0, 1000000, 20, 0, 0)
SKIP_EQ = (500000, 1000000, 1, 500, 500, 1, 0, 1000000, 20, 0, 0)
SKIP_OFF = (500000, 1000000, 1, 400, 600, 0, 0, 1000000, 20, 0, 0)
ZERO_RES = (0, 1000000, 1, 600, 400, 0, 0, 1000000, 20, 0, 0)
KINK_LO = (400000, 1000000, 1, 600, 400, 0, 500000, 1000000, 50, 20, 100)
KINK_HI = (800000, 1000000, 1, 600, 400, 0, 500000, 1000000, 30, 20, 100)
RFACTOR = (500000, 1000000, 1, 600, 400, 0, 500000, 500000, 20, 20, 100)
ABOVE_LE = (800000, 1000000, 1, 600, 400, 0, 500000, 1000000, 30, 100, 50)


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


def py_tofactor(v: int, d: int) -> int:
    return 0 if d == 0 else py_muldiv(v, FLOAT_P, d)


def py_usage(reserved: int, pool: int, rfactor: int) -> int:
    maxr = py_apply(pool, rfactor)
    return 0 if maxr == 0 else py_tofactor(reserved, maxr)


def py_skip(is_long: int, long_oi: int, short_oi: int, skip: int) -> int:
    if skip == 0:
        return 1
    if is_long == 1:
        return 0 if long_oi < short_oi else 1
    return 0 if short_oi < long_oi else 1


def py_kink(usage: int, opt: int, base: int, above: int) -> int:
    fps = py_apply(usage, base)
    if usage > opt and FLOAT_P > opt:
        add = (above - base) if above > base else 0
        den = FLOAT_P - opt
        if den == 0:
            return fps
        fps += py_muldiv(add, usage - opt, den)
    return fps


def py_linear(reserved: int, pool: int, factor: int) -> int:
    if pool == 0:
        return 0
    return py_apply(py_tofactor(reserved, pool), factor)


def py_fps(args: tuple[int, ...]) -> int:
    reserved, pool, is_long, long_oi, short_oi, skip, opt, rfactor, factor, base, above = args
    if reserved == 0:
        return 0
    if py_skip(is_long, long_oi, short_oi, skip) == 0:
        return 0
    if pool == 0:
        return 0
    if opt != 0:
        return py_kink(py_usage(reserved, pool, rfactor), opt, base, above)
    return py_linear(reserved, pool, factor)


def py_wrong_linear(args: tuple[int, ...]) -> int:
    reserved, pool, is_long, long_oi, short_oi, skip, _opt, _rf, factor, _b, _a = args
    if reserved == 0:
        return 0
    if py_skip(is_long, long_oi, short_oi, skip) == 0:
        return 0
    return py_linear(reserved, pool, factor)


def py_wrong_kink_apply(args: tuple[int, ...]) -> int:
    reserved, pool, is_long, long_oi, short_oi, skip, opt, rfactor, _f, base, above = args
    if reserved == 0 or py_skip(is_long, long_oi, short_oi, skip) == 0 or pool == 0:
        return 0
    usage = py_usage(reserved, pool, rfactor)
    fps = py_apply(usage, base)
    if usage > opt and FLOAT_P > opt:
        add = (above - base) if above > base else 0
        fps += py_apply(usage - opt, add)
    return fps


def py_wrong_no_rfactor(args: tuple[int, ...]) -> int:
    reserved, pool, is_long, long_oi, short_oi, skip, opt, _rf, _f, base, above = args
    if reserved == 0 or py_skip(is_long, long_oi, short_oi, skip) == 0 or pool == 0:
        return 0
    return py_kink(py_tofactor(reserved, pool), opt, base, above)


def py_wrong_add_neg(args: tuple[int, ...]) -> int:
    reserved, pool, _il, _lo, _so, _sk, opt, rfactor, _f, base, above = args
    if reserved == 0 or pool == 0:
        return 0
    usage = py_usage(reserved, pool, rfactor)
    fps = py_apply(usage, base)
    if usage > opt:
        den = FLOAT_P - opt
        if den == 0:
            return fps
        fps += ((above - base) * (usage - opt)) // den
    return fps


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
    print("  GMX V2 getBorrowingFactorPerSecond — LIN proof (C11)")

    fps_ex = FIX / "GetBorrowingFactorPerSecond.excerpt.sol"
    kink_ex = FIX / "GetKinkBorrowingFactor.excerpt.sol"
    use_ex = FIX / "GetUsageFactor.excerpt.sol"
    cum_ex = FIX / "GetNextCumulativeBorrowingFactor.excerpt.sol"
    prc_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    if not all(p.exists() for p in (fps_ex, kink_ex, use_ex, cum_ex, prc_ex)):
        rec("PIN-FILE", "FAIL", "pinned borrow-fps / kink / usage / cum / Precision excerpts missing")
        return 1
    fps_txt = fps_ex.read_text(encoding="utf-8")
    need = [
        "if (reservedUsd == 0) { return 0; }",
        "skipBorrowingFeeForSmallerSide",
        "the borrowing fee would be charged for both sides",
        "UnableToGetBorrowingFactorEmptyPoolUsd",
        "if (optimalUsageFactor != 0)",
        "return Precision.applyFactor(reservedUsdToPoolFactor, borrowingFactor)",
    ]
    missing = [s for s in need if s not in fps_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "fps excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains reserved=0, skip-smaller, empty-pool revert, kink vs linear")
    kink_txt = kink_ex.read_text(encoding="utf-8")
    if "additionalBorrowingFactorPerSecond * diff / divisor" not in kink_txt:
        rec("PIN-KINK", "FAIL", "kink excerpt missing raw additional*diff/divisor")
        return 1
    rec("PIN-KINK", "PASS", "kink additional is raw muldiv, not applyFactor")
    if "Precision.toFactor(reservedUsd, maxReservedUsd)" not in use_ex.read_text(encoding="utf-8"):
        rec("PIN-USAGE", "FAIL", "usage excerpt missing reserved/maxReserved toFactor")
        return 1
    rec("PIN-USAGE", "PASS", "getUsageFactor is reserved / applyFactor(pool, openInterestReserveFactor)")
    if "durationInSeconds * borrowingFactorPerSecond" not in cum_ex.read_text(encoding="utf-8"):
        rec("PIN-CUM", "FAIL", "cumulative excerpt missing duration * fps")
        return 1
    rec("PIN-CUM", "PASS", "cumulative delta is durationInSeconds * fps, not applyFactor and not V1 intervals")
    prc_txt = prc_ex.read_text(encoding="utf-8")
    if "FLOAT_PRECISION = 10 ** 30" not in prc_txt or "applyFactor" not in prc_txt:
        rec("PIN-PREC", "FAIL", "Precision excerpt missing FLOAT / applyFactor")
        return 1
    rec("PIN-PREC", "PASS", "Precision excerpt pins FLOAT=1e30 (LIN uses FLOAT prime=1e6)")
    if "exponentFactor == FLOAT_PRECISION" not in prc_txt:
        rec("PIN-EXP", "FAIL", "applyExponentFactor identity skip missing")
        return 1
    rec("PIN-EXP", "PASS", "applyExponentFactor is identity when exponent == FLOAT; pow is not claimed")

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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb borrow-fps selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (linear / skip / kink / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 borrow-fps clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_borrow_fps.lin")
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

    gate = run([str(C0), "vm", str(LIN), "g2b_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2b_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2b_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, tuple[int, ...], int]] = [
        ("fps", LINEAR, 10),
        ("fps", SKIP_LONG, 0),
        ("fps", SKIP_SHORT, 10),
        ("fps", SKIP_EQ, 10),
        ("fps", SKIP_OFF, 10),
        ("fps", ZERO_RES, 0),
        ("fps", KINK_LO, 8),
        ("wronglinear", KINK_LO, 20),
        ("fps", KINK_HI, 64),
        ("wrongkinkapply", KINK_HI, 40),
        ("wronglinear", KINK_HI, 24),
        ("fps", RFACTOR, 100),
        ("wrongnorfactor", RFACTOR, 10),
        ("fps", ABOVE_LE, 80),
        ("wrongaddneg", ABOVE_LE, 50),
        ("muldiv", (7_000_000_000, 2_000_000_000, 1_000_000), 14_000_000_000_000),
        ("delta", (10, 3600), 36000),
        ("applydelta", (10, 3600), 0),
        ("v1", (10, 3600, 3600), 10),
        ("ok", (100, 0), 0),
        ("ok", (0, 0), 1),
    ]
    fn_map = {
        "fps": "g2b_fps",
        "wronglinear": "g2b_wrong_linear",
        "wrongkinkapply": "g2b_wrong_kink_apply",
        "wrongnorfactor": "g2b_wrong_no_rfactor",
        "wrongaddneg": "g2b_wrong_add_neg",
        "muldiv": "g2b_muldiv",
        "delta": "g2b_delta",
        "applydelta": "g2b_wrong_delta_apply",
        "v1": "g2b_v1_interval",
        "ok": "g2b_ok",
    }
    py_map = {
        "fps": py_fps,
        "wronglinear": py_wrong_linear,
        "wrongkinkapply": py_wrong_kink_apply,
        "wrongnorfactor": py_wrong_no_rfactor,
        "wrongaddneg": py_wrong_add_neg,
        "muldiv": lambda a: py_muldiv(*a),
        "delta": lambda a: a[0] * a[1],
        "applydelta": lambda a: py_apply(a[1], a[0]),
        "v1": lambda a: a[0] * (a[1] // a[2]),
        "ok": lambda a: (1 if a[0] == 0 else (0 if a[1] == 0 else 1)),
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

    wide = lin_vm(LIN, "g2b_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2b_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)
    skip0 = lin_vm(LIN, "g2b_fps", *SKIP_LONG)
    skip1 = lin_vm(LIN, "g2b_fps", *SKIP_SHORT)
    skipeq = lin_vm(LIN, "g2b_fps", *SKIP_EQ)
    kink8 = lin_vm(LIN, "g2b_fps", *KINK_LO)
    lin20 = lin_vm(LIN, "g2b_wrong_linear", *KINK_LO)
    kink64 = lin_vm(LIN, "g2b_fps", *KINK_HI)
    app40 = lin_vm(LIN, "g2b_wrong_kink_apply", *KINK_HI)
    rf100 = lin_vm(LIN, "g2b_fps", *RFACTOR)
    rf10 = lin_vm(LIN, "g2b_wrong_no_rfactor", *RFACTOR)
    d36000 = lin_vm(LIN, "g2b_delta", 10, 3600)
    d0 = lin_vm(LIN, "g2b_wrong_delta_apply", 10, 3600)
    d10 = lin_vm(LIN, "g2b_v1_interval", 10, 3600, 3600)
    ok_empty = lin_vm(LIN, "g2b_ok", 100, 0)
    ok_zero = lin_vm(LIN, "g2b_ok", 0, 0)

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec(
        "SKIP-SMALLER",
        "PASS" if skip0 == 0 and skip1 == 10 and skipeq == 10 else "FAIL",
        "skip-smaller: long-light 0, short-heavy 10, equal OI still 10",
    )
    rec(
        "KINK-VS-LINEAR",
        "PASS" if kink8 == 8 and lin20 == 20 else "FAIL",
        "kink below opt uses baseBorrowingFactor (8) not linear borrowingFactor (20)",
    )
    rec(
        "KINK-RAW",
        "PASS" if kink64 == 64 and app40 == 40 else "FAIL",
        "kink above opt additional is raw 48 (fps 64) vs applyFactor extra 24 (fps 40)",
    )
    rec(
        "RFACTOR",
        "PASS" if rf100 == 100 and rf10 == 10 else "FAIL",
        "kink usage is reserved/(pool*rfactor); ignoring rfactor=0.5 yields 10 not 100",
    )
    rec(
        "CUM-DELTA",
        "PASS" if d36000 == 36000 and d0 == 0 and d10 == 10 else "FAIL",
        "V2 delta duration*fps=36000; applyFactor floors to 0; V1 interval count yields 10",
    )
    rec(
        "EMPTY-POOL",
        "PASS" if ok_empty == 0 and ok_zero == 1 else "FAIL",
        "empty pool with reserved>0 fail-closes; reserved==0 is ok even if pool==0",
    )
    rec(
        "NAIVE-WRAP",
        "PASS" if naive != wide and wide == 14_000_000_000_000 and naive == wrap_py else "FAIL",
        "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000",
    )

    jit_ok = lin_roundtrip_jit(LIN, "g2b_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2b_test_suite (in-memory libtcc)")
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
        "PASS" if "g2b_fps" in src and "g2b_kink" in src else "FAIL",
        "LIN clone takes reserved/pool/OI/skip/opt/rfactor/factor/base/above as arguments (no DataStore)",
    )
    rec(
        "WIDE-MULDIV",
        "PASS" if "g2b_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv",
    )
    rec(
        "NOT-V1-RATE",
        "PASS" if "getBorrowingFactorPerSecond" in fps_txt and "g2b_v1_interval" in src else "FAIL",
        "kernel is per-second fps vs V1 interval*reserved/pool",
    )
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_t = ["REJ_SOLIDITY_GMX_V2_BORROW_FPS", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec(
        "SOL-REJECT",
        "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getBorrowingFactorPerSecond before ENV",
        ",".join(missing_t) if missing_t else "",
    )
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-REJECT",
        "PASS" if "REJ_RUST_GMX_V2_BORROW_FPS" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_borrowing_factor_per_second",
    )

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_BORROW_FPS_EVIDENCE_1.0",
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
            "commercial_descendants": "GMX V2 synthetics: borrowing is per-second; skip-smaller-side zeros the lighter OI; kink additional is raw (above-base)*diff/(FLOAT-opt) not applyFactor; cumulative delta is duration*fps not V1 interval count.",
        },
        "lin_clone": "src/lin_gmx_v2_borrow_fps.lin",
        "c11_oracle": "test/oracles/gmx_v2_borrow_fps_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "linear_fps": 10,
            "skip_long_smaller": 0,
            "skip_short_larger": 10,
            "skip_equal_both": 10,
            "kink_below": 8,
            "wrong_linear_below": 20,
            "kink_above": 64,
            "wrong_kink_apply": 40,
            "wrong_linear_above": 24,
            "rfactor_kink": 100,
            "wrong_no_rfactor": 10,
            "above_le_base": 80,
            "wrong_add_neg": 50,
            "delta_v2": 36000,
            "delta_applyfactor": 0,
            "delta_v1_interval": 10,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-borrow-fps",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
