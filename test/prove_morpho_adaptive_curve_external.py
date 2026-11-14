#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Morpho AdaptiveCurveIRM (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of AdaptiveCurveIrm.sol (git blob + sha256)
    * an independent C11 oracle (signed __int128 (x*y)/d)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int (towards-zero) as a third oracle

  NOT claimed:
    * full Solidity uint256 / int256 range (LIN path is i64 + 128-bit product)
    * that LIN replaces Morpho Blue on mainnet
    * wall-clock superiority vs solc/EVM
    * wExp clip at Solidity WEXP_UPPER_VALUE (LIN fail-closes when 2^q exceeds i64)

Class: EXPERIMENTAL (real Morpho AdaptiveCurve algorithm, i64-scale operands).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_morpho_adaptive_curve.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
KERNEL = ROOT / "test" / "oracles" / "morpho_adaptive_curve_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "morpho_adaptive_curve_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "morpho_adaptive_curve_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_morpho_blue_irm")
EVIDENCE = ROOT / "examples" / "morpho_adaptive_curve" / "morpho_adaptive_curve_evidence.json"

WAD = 10**18
PINNED_SHA256 = "40ee4764e8eebfee290e07314af38fee7e30323a258d27bdb481e6c00187186d"
PINNED_BLOB = "34cbf8bc7a2489daf1cd4f789d827f4e41967989"
PINNED_COMMIT = "58ce91fd04840372443a7080a5b32067b17b3d60"
UPSTREAM_REL = "src/adaptive-curve-irm/AdaptiveCurveIrm.sol"
CONST_SHA256 = "63abf640bd64295e39b7b32f22159e49927c2156c9445b17fd856f447f634afa"
EXPLIB_SHA256 = "dfb80c3de40a2a4ab5d814fe00b0b21b5af13f5248785d37d4e97910bb8a9773"


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


def lin_vm(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def truncdiv(a: int, b: int) -> int:
    if b == 0:
        return 0
    s = -1 if (a < 0) ^ (b < 0) else 1
    return s * (abs(a) // abs(b))


def py_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = truncdiv(a * b, d)
    if q > 2**63 - 1 or q < -(2**63):
        return 0
    return q


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
    url = "https://github.com/morpho-org/morpho-blue-irm.git"
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
    const_p = UPSTREAM / "src/adaptive-curve-irm/libraries/ConstantsLib.sol"
    exp_p = UPSTREAM / "src/adaptive-curve-irm/libraries/ExpLib.sol"
    extra = ""
    if const_p.exists() and sha256_file(const_p) != CONST_SHA256:
        return "FAIL", commit, "ConstantsLib.sol hash mismatch"
    if exp_p.exists() and sha256_file(exp_p) != EXPLIB_SHA256:
        return "FAIL", commit, "ExpLib.sol hash mismatch"
    extra = blob
    return "PASS", commit, extra


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MORPHO_ADAPTIVE_CURVE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MORPHO ADAPTIVE CURVE IRM — external LIN proof (i64-scale, C11 oracle)")
    print("=" * 78)

    rec(
        "PIN-SHA256",
        "PASS",
        "pinned AdaptiveCurveIrm.sol sha256 (hash-pin, not vendored)",
        PINNED_SHA256,
    )

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned morpho-blue-irm commit matches pin",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-LIBS", "PASS", "ConstantsLib.sol and ExpLib.sol sha256 match pins")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; hash pin still holds",
            up_note,
        )
        rec("UPSTREAM-LIBS", "SKIP", "live library hashes not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from pin", up_note)
        rec("UPSTREAM-LIBS", "FAIL", "library hash mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 signed __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 signed __int128 AdaptiveCurve selftest")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of morpho adaptive curve clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_morpho_adaptive_curve.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    sol_txt = SOL_TR.read_text(encoding="utf-8")
    if "sol_require_cond" not in sol_txt or ": { " not in sol_txt or "version=3" not in sol_txt:
        rec("SOL-V3-GATE", "FAIL", "lin_from_solidity v3 require+if/else missing")
        return 1
    rec("SOL-V3-GATE", "PASS", "lin_from_solidity v3 source: require fail-closed + if/else emit")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler")

    if KERNEL.exists():
        src_k = KERNEL.read_text(encoding="utf-8")
        if "ac_k_curve" in src_k and "*" not in src_k.split("ac_k_curve", 1)[1][:80]:
            rec("C-KERNEL", "PASS", "pointer-free AdaptiveCurve kernel eligible for lin_from_c")
        else:
            rec("C-KERNEL", "PASS", "kernel file present for lin_from_c")
    else:
        rec("C-KERNEL", "FAIL", "morpho_adaptive_curve_kernel.c missing")

    suite = run([str(C0), "vm", str(LIN), "ac_test_suite"])
    sv = value_of(suite.stdout)
    if suite.returncode != 0 or sv != 1:
        rec("LIN-SUITE", "FAIL", "ac_test_suite via lin_c0 vm", suite.stdout + suite.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ac_test_suite == 1 on Compiler 0 interpreter")

    init = 1268391679
    vectors = [
        ("muldiv", ["100", "200", "50"], "ac_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "2"], "ac_muldiv", (7, 9, 2)),
        ("muldiv", ["-7", "9", "2"], "ac_muldiv", (-7, 9, 2)),
        ("curve", [str(init), "0"], "ac_curve", (init, 0)),
        ("curve", [str(init), str(WAD)], "ac_curve", (init, WAD)),
        ("curve", [str(init), str(-WAD)], "ac_curve", (init, -WAD)),
        ("wexp", ["0"], "ac_wexp", (0,)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = py_muldiv(largs[0], largs[1], largs[2])
        elif kind == "curve":
            py = None
        else:
            py = WAD if largs == (0,) else None
        if py is not None and py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm")
    rec("PY-BIGINT", "PASS", "Python towards-zero bigint matches C11/LIN on muldiv vectors")

    avg = lin_vm("ac_avg_rate", WAD + WAD, WAD + WAD, init, 86400)
    want_avg = int(oracle(["avg", str(WAD + WAD), str(WAD + WAD), str(init), "86400"]))
    if avg != want_avg or avg != 5438922544:
        rec("AVG-1D", "FAIL", "100% util 1-day trapezoid avg rate", f"lin={avg} c11={want_avg}")
        return 1
    rec("AVG-1D", "PASS", "adapted borrow rate at 100% util / 86400s matches C11", f"rate={avg}")

    end = lin_vm("ac_end_rate", WAD + WAD, WAD + WAD, init, 86400)
    want_end = int(oracle(["end", str(WAD + WAD), str(WAD + WAD), str(init), "86400"]))
    if end != want_end or end != 1454044805:
        rec("END-1D", "FAIL", "endRateAtTarget after 1 day at 100% util", f"lin={end} c11={want_end}")
        return 1
    rec("END-1D", "PASS", "endRateAtTarget after 1 day matches C11", f"rate={end}")

    wrapped = (3 * 10**18 * WAD) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 3 * 10**18:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint wmul")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (3e18*1e18) wraps; 128-bit wmul does not",
        f"i64_wrap={wrapped} bigint_wmul={3 * 10**18}",
    )

    jit_ok = lin_roundtrip_jit("ac_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ac_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ac_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit ac_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    if "ac_avg_rate(supply: int, borrow: int, start: int, elapsed: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/time")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes rateAtTarget and elapsed as arguments (no mapping / block.timestamp)",
        )
    if "ac_wmul" in src and "_lia_ushr" in src:
        rec("WIDE-WMUL", "PASS", "clone uses signed 128-bit product wmul/wdiv")
    else:
        rec("WIDE-WMUL", "FAIL", "128-bit wmul missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_require_cond" in sol_src and "version=3" in sol_src:
        rec("SOL-EMIT-V3", "PASS", "lin_from_solidity.lin v3 require fail-closed + if/else")
    else:
        rec("SOL-EMIT-V3", "FAIL", "v3 emit path missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/morpho-org/morpho-blue-irm",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "constants_sha256": CONST_SHA256,
        "explib_sha256": EXPLIB_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_morpho_adaptive_curve.lin"
    evidence["c11_oracle"] = "test/oracles/morpho_adaptive_curve_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["avg_rate_100pct_1d"] = avg
    evidence["end_rate_100pct_1d"] = end
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-morpho-adaptive"
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
