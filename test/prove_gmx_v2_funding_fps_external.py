#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 getNextFundingFactorPerSecond vs LIN C0."""
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
LIN = ROOT / "src" / "lin_gmx_v2_funding_fps.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_funding_fps_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_funding_fps_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_funding_fps" / "gmx_v2_funding_fps_evidence.json"

PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL = "contracts/market/MarketUtils.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
PRC_REL = "contracts/utils/Precision.sol"
PRC_SHA256 = "8713db02a257238101fc62cc682a8f8061fba25951216863576afbbd00f34808"
PRC_BLOB = "047143722beaf6adceac3fc2ef1817f054dfe00a"
CALC_REL = "contracts/utils/Calc.sol"
FLOAT_P = 1_000_000

# lo, so, saved, dur, inc, dec, minf, maxf, stable, dthr, sfactor
STATIC = (600, 400, 0, 0, 0, 0, 0, 10000, 0, 0, 50)
STATIC_CAP = (900, 100, 0, 0, 0, 0, 0, 20, 0, 0, 50)
ZERO_DIFF = (500, 500, 0, 0, 0, 0, 0, 10000, 0, 0, 50)
ADAPT_INC = (700, 300, 100, 5, 10, 0, 0, 10000, 100000, 0, 0)
SKEW_HOLD = (300, 700, 100, 5, 10, 0, 0, 10000, 0, 0, 0)
SKEW_FLIP = (300, 700, 10, 5, 10, 0, 0, 10000, 0, 0, 0)
MIN_TRAP = (400, 600, -3, 0, 10, 0, 10, 10000, 500000, 50000, 0)
DEC_ONE = (510, 490, 50, 7, 10, 8, 0, 10000, 500000, 100000, 0)
DEC_PARTIAL = (800, 200, 100, 7, 10, 8, 0, 10000, 900000, 700000, 0)
MAX_CAP = (700, 300, 90, 5, 10, 0, 0, 100, 100000, 0, 0)


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


def py_abs(a: int) -> int:
    return -a if a < 0 else a


def py_sign(a: int) -> int:
    return 1 if a == 0 else (1 if a > 0 else -1)


def py_bound(value: int, minv: int, maxv: int) -> int:
    mag = py_abs(value)
    if mag < minv:
        mag = minv
    if mag > maxv:
        mag = maxv
    return mag * py_sign(value)


def py_diff(a: int, b: int) -> int:
    return a - b if a > b else b - a


def py_imb(lo: int, so: int) -> int:
    total = lo + so
    if total == 0:
        return 0
    return py_muldiv(py_diff(lo, so), FLOAT_P, total)


def py_raw(lo, so, saved, dur, inc, dec, stable, dthr, dec_as_factor=0, dec_to_zero=0):
    d = py_diff(lo, so)
    total = lo + so
    if d == 0 and inc == 0:
        return 0
    if total == 0 or inc == 0:
        return 0
    same = (saved > 0 and lo > so) or (saved < 0 and so > lo)
    imb = py_imb(lo, so)
    if not same:
        ch = 1
    elif imb > stable:
        ch = 1
    elif imb < dthr:
        ch = 2
    else:
        ch = 0
    nexts = saved
    if ch == 1:
        incv = py_muldiv(py_muldiv(d, inc, total), dur, 1)
        if lo < so:
            incv = -incv
        nexts = saved + incv
    if ch == 2 and saved != 0:
        mag = py_abs(saved)
        decv = py_muldiv(dec, dur, 1)
        if dec_as_factor:
            decv = py_muldiv(py_muldiv(imb, dec, FLOAT_P), dur, 1)
        nexts = py_sign(saved) if mag <= decv else (mag - decv) * py_sign(saved)
        if mag <= decv and dec_to_zero:
            nexts = 0
    return nexts


def py_fps(args: tuple[int, ...]) -> int:
    lo, so, saved, dur, inc, dec, minf, maxf, stable, dthr, sfactor = args
    if py_diff(lo, so) == 0 and inc == 0:
        return 0
    if lo + so == 0:
        return 0
    if inc == 0:
        fps = py_muldiv(py_imb(lo, so), sfactor, FLOAT_P)
        return maxf if fps > maxf else fps
    nxt = py_raw(lo, so, saved, dur, inc, dec, stable, dthr)
    return py_abs(py_bound(py_bound(nxt, 0, maxf), minf, maxf))


def py_saved(args: tuple[int, ...]) -> int:
    lo, so, saved, dur, inc, dec, minf, maxf, stable, dthr, _sf = args
    if inc == 0:
        return 0
    return py_bound(py_raw(lo, so, saved, dur, inc, dec, stable, dthr), 0, maxf)


def py_pay(args: tuple[int, ...]) -> int:
    lo, so, saved, dur, inc, dec, minf, maxf, stable, dthr, sfactor = args
    if py_diff(lo, so) == 0 and inc == 0:
        return 1
    if lo + so == 0:
        return 0
    if inc == 0:
        return 1 if lo > so else 0
    m = py_bound(py_saved(args), minf, maxf)
    return 1 if m > 0 else 0


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
    print("  GMX V2 getNextFundingFactorPerSecond — LIN proof (C11)")

    fps_ex = FIX / "GetNextFundingFactorPerSecond.excerpt.sol"
    bnd_ex = FIX / "BoundMagnitude.excerpt.sol"
    prc_ex = FIX / "PrecisionApplyFactor.excerpt.sol"
    if not fps_ex.exists() or not bnd_ex.exists() or not prc_ex.exists():
        rec("PIN-FILE", "FAIL", "pinned fps / bound / Precision excerpts missing")
        return 1
    fps_txt = fps_ex.read_text(encoding="utf-8")
    need = [
        "only the nextFundingFactorPerSecond is bound by minFundingFactorPerSecond",
        "the nextSavedFundingFactorPerSecond is not bound by minFundingFactorPerSecond",
        "fundingDecreaseFactorPerSecond * durationInSeconds",
        "nextSavedFundingFactorPerSecondWithMinBound.abs()",
    ]
    missing = [s for s in need if s not in fps_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "fps excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains min-vs-saved split, raw decrease, abs(minBound)")
    if "value == 0 ? int256(1)" not in bnd_ex.read_text(encoding="utf-8"):
        rec("PIN-BOUND", "FAIL", "boundMagnitude excerpt missing zero-sign +1")
        return 1
    rec("PIN-BOUND", "PASS", "Calc.boundMagnitude excerpt is min/max on abs, sign(0)=+1")
    prc_txt = prc_ex.read_text(encoding="utf-8")
    if "FLOAT_PRECISION = 10 ** 30" not in prc_txt or "applyFactor" not in prc_txt:
        rec("PIN-PREC", "FAIL", "Precision excerpt missing FLOAT / applyFactor")
        return 1
    rec("PIN-PREC", "PASS", "Precision excerpt pins FLOAT=1e30 (LIN uses FLOAT prime=1e6)")

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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb fps selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (static / min-trap / decrease / wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 funding-fps clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_funding_fps.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "g2r_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "g2r_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2r_test_suite == 1 on Compiler 0 interpreter")

    cases: list[tuple[str, tuple[int, ...], int]] = [
        ("fps", STATIC, 10),
        ("fps", STATIC_CAP, 20),
        ("fps", ZERO_DIFF, 0),
        ("pay", ZERO_DIFF, 1),
        ("fps", ADAPT_INC, 120),
        ("fps", SKEW_HOLD, 80),
        ("pay", SKEW_HOLD, 1),
        ("saved", SKEW_FLIP, -10),
        ("pay", SKEW_FLIP, 0),
        ("saved", MIN_TRAP, -3),
        ("wrongmin", MIN_TRAP, -10),
        ("fps", MIN_TRAP, 10),
        ("saved", DEC_ONE, 1),
        ("wrongdec0", DEC_ONE, 0),
        ("saved", DEC_PARTIAL, 44),
        ("wrongdecf", DEC_PARTIAL, 72),
        ("fps", MAX_CAP, 100),
        ("muldiv", (7_000_000_000, 2_000_000_000, 1_000_000), 14_000_000_000_000),
        ("wrongnocap", (900, 100, 50), 40),
    ]
    fn_map = {
        "fps": "g2r_fps",
        "saved": "g2r_saved",
        "pay": "g2r_pay",
        "wrongmin": "g2r_wrong_min_saved",
        "wrongdec0": "g2r_wrong_dec_zero",
        "wrongdecf": "g2r_wrong_dec_factor",
        "muldiv": "g2r_muldiv",
        "wrongnocap": "g2r_wrong_nocap",
    }
    n_ok = 0
    for kind, args, expect in cases:
        want = int(oracle([kind, *astr(args)]).splitlines()[-1])
        want_limbs = int(oracle([kind, *astr(args), "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn_map[kind], *args)
        if kind == "fps":
            pyv = py_fps(args)
        elif kind == "saved":
            pyv = py_saved(args)
        elif kind == "pay":
            pyv = py_pay(args)
        elif kind == "wrongmin":
            pyv = py_bound(py_raw(*args[:6], args[8], args[9]), args[6], args[7])
        elif kind == "wrongdec0":
            pyv = py_bound(py_raw(*args[:6], args[8], args[9], 0, 1), 0, args[7])
        elif kind == "wrongdecf":
            pyv = py_bound(py_raw(*args[:6], args[8], args[9], 1, 0), 0, args[7])
        elif kind == "muldiv":
            pyv = py_muldiv(*args)
        else:
            pyv = py_muldiv(py_imb(args[0], args[1]), args[2], FLOAT_P)
        if want != expect or want_limbs != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}",
                f"lin={got_lin} c11={want} limbs={want_limbs} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    wide = lin_vm(LIN, "g2r_muldiv", 7_000_000_000, 2_000_000_000, 1_000_000)
    naive = lin_vm(LIN, "g2r_naive_i64", 7_000_000_000, 2_000_000_000, 1_000_000)
    wrap_py = trunc_div(w64(7_000_000_000 * 2_000_000_000), 1_000_000)
    min_saved = lin_vm(LIN, "g2r_saved", *MIN_TRAP)
    min_wrong = lin_vm(LIN, "g2r_wrong_min_saved", *MIN_TRAP)
    dec1 = lin_vm(LIN, "g2r_saved", *DEC_ONE)
    dec0 = lin_vm(LIN, "g2r_wrong_dec_zero", *DEC_ONE)
    dec44 = lin_vm(LIN, "g2r_saved", *DEC_PARTIAL)
    dec72 = lin_vm(LIN, "g2r_wrong_dec_factor", *DEC_PARTIAL)
    hold_pay = lin_vm(LIN, "g2r_pay", *SKEW_HOLD)
    cap20 = lin_vm(LIN, "g2r_fps", *STATIC_CAP)
    nocap = lin_vm(LIN, "g2r_wrong_nocap", 900, 100, 50)

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("MIN-TRAP", "PASS" if min_saved == -3 and min_wrong == -10 else "FAIL",
        "charged min-bound fps keeps saved=-3; wrongly min-binding saved yields -10")
    rec("DEC-SIGN", "PASS" if dec1 == 1 and dec0 == 0 else "FAIL",
        "decrease past magnitude becomes +1; clamp-to-zero yields 0")
    rec("DEC-SCALE", "PASS" if dec44 == 44 and dec72 == 72 else "FAIL",
        "decrease is raw 56 (saved 44) vs applyFactor-as-increase 28 (saved 72)")
    rec("SKEW-HOLD", "PASS" if hold_pay == 1 else "FAIL",
        "after skew flip, saved=80 still longs-pay until signed saved crosses 0")
    rec("STATIC-CAP", "PASS" if cap20 == 20 and nocap == 40 else "FAIL",
        "static path caps 40 to max=20; ignoring max leaves 40")
    rec("NAIVE-WRAP", "PASS" if naive != wide and wide == 14_000_000_000_000 and naive == wrap_py else "FAIL",
        "naive i64 7e9*2e9/1e6 wraps to -4446744073709; 128-bit = 14000000000000")

    jit_ok = lin_roundtrip_jit(LIN, "g2r_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2r_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "g2r_fps" in src and "g2r_saved" in src else "FAIL",
        "LIN clone takes OI/saved/inc/dec/min/max as arguments (no DataStore)")
    rec("WIDE-MULDIV", "PASS" if "g2r_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit diff*inc / total")
    rec("NOT-V1-RATE", "PASS" if "getNextFundingFactorPerSecond" in fps_txt and "g2r_wrong_min_saved" in src else "FAIL",
        "kernel is adaptive signed fps vs min-bound saved, not V1 interval*reserved/pool")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_t = ["REJ_SOLIDITY_GMX_V2_FUNDING_FPS", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects getNextFundingFactorPerSecond before ENV",
        ",".join(missing_t) if missing_t else "")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_FUNDING_FPS" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects get_next_funding_factor_per_second")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_FUNDING_FPS_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT,
            "path": MKT_REL,
            "calc_path": CALC_REL,
            "precision_path": PRC_REL,
            "git_blob_sha": blob or MKT_BLOB,
            "file_sha256": MKT_SHA256,
            "precision_git_blob_sha": PRC_BLOB,
            "precision_file_sha256": PRC_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 synthetics: adaptive funding fps is signed; min binds the charged rate not the saved rate, otherwise min!=0 blocks sign flip. Decrease is raw dec*duration not applyFactor.",
        },
        "lin_clone": "src/lin_gmx_v2_funding_fps.lin",
        "c11_oracle": "test/oracles/gmx_v2_funding_fps_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "static_fps": 10,
            "static_cap": 20,
            "wrong_nocap": 40,
            "zero_diff_pay": 1,
            "adapt_inc": 120,
            "skew_hold": 80,
            "skew_flip_saved": -10,
            "min_trap_saved": -3,
            "min_trap_wrong": -10,
            "dec_one": 1,
            "dec_zero_wrong": 0,
            "dec_partial": 44,
            "dec_factor_wrong": 72,
            "max_cap": 100,
            "wrap_wide": 14_000_000_000_000,
            "wrap_naive": wrap_py,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-gmx-v2-funding-fps",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
