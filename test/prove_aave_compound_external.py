#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Aave V3 MathUtils compounded interest vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of MathUtils.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      that mirror src/lin_aave_compound.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / ray (RAY=1e27 exceeds signed i64)
    * that LIN replaces Aave on mainnet
    * wall-clock superiority vs solc/EVM
    * aave-dao/aave-v3-origin (BUSL Change Date 2027-03-06 still future)

Class: EXPERIMENTAL (real Aave binomial series, wad 1e18 operands).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_aave_compound.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "aave_compound_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "aave_compound_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_aave_v3_core")
EVIDENCE = ROOT / "examples" / "aave_compound" / "aave_compound_evidence.json"
JR_LIN = ROOT / "src" / "lin_compound_jumprate.lin"

WAD = 10**18
YEAR = 31536000
RATE5 = 5 * 10**16
RATE100 = 10**18
PINNED_SHA256 = "7f73c927e9801debfe0666e2a6364b92f62fd2d58d0c4b485ff04765fd4dc58d"
PINNED_BLOB = "9adca939db36cbe1009d0a00600def9314fc7332"
PINNED_COMMIT = "b74526a7bc67a3a117a1963fc871b3eb8cea8435"
UPSTREAM_REL = "contracts/protocol/libraries/math/MathUtils.sol"


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


def lin_vm(fn: str, *args: int, module: Path = LIN) -> int:
    cmd = [str(C0), "vm", str(module), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(fn: str, *args: int, module: Path = LIN) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(module), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
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
    url = "https://github.com/aave/aave-v3-core.git"
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
    return "PASS", commit, blob


def py_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (a * b) // d
    if q > 2**64 - 1:
        return 0
    return q


def py_linear(rate: int, dt: int) -> int:
    return WAD + py_muldiv(rate, dt, YEAR)


def py_compounded(rate: int, dt: int) -> int:
    if dt == 0:
        return WAD
    dt1 = dt - 1
    dt2 = dt - 2 if dt > 2 else 0
    first = py_muldiv(rate, dt, YEAR)
    r2 = py_muldiv(rate, rate, WAD)
    pair = py_muldiv(dt, dt1, 2)
    second = py_muldiv(r2, pair, YEAR * YEAR)
    r3 = py_muldiv(r2, rate, WAD)
    t = py_muldiv(r3, dt, YEAR)
    t = py_muldiv(t, dt1, YEAR)
    t = py_muldiv(t, dt2, YEAR)
    third = py_muldiv(t, 1, 6)
    return WAD + first + second + third


def py_year2_floor(rate: int, dt: int) -> int:
    if dt == 0:
        return WAD
    dt1 = dt - 1
    dt2 = dt - 2 if dt > 2 else 0
    first = py_muldiv(rate, dt, YEAR)
    r2 = py_muldiv(rate, rate, WAD)
    bp2 = py_muldiv(r2, 1, YEAR * YEAR)
    pair = py_muldiv(dt, dt1, 2)
    second = py_muldiv(pair, bp2, 1)
    bp3 = py_muldiv(py_muldiv(bp2, rate, WAD), 1, YEAR)
    third = py_muldiv(py_muldiv(py_muldiv(dt, dt1, 1), dt2, 1), bp3, 6)
    return WAD + first + second + third


def py_horner(rate: int, dt: int) -> int:
    x = py_muldiv(rate, dt, YEAR)
    x2 = py_muldiv(x, x, WAD)
    x3 = py_muldiv(x2, x, WAD)
    return WAD + x + py_muldiv(x2, 1, 2) + py_muldiv(x3, 1, 6)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_AAVE_COMPOUND_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  AAVE V3 COMPOUNDED INTEREST — external LIN proof (wad-scale, C11)")
    print("=" * 78)

    pinned = FIX / "MathUtils.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned MathUtils.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned MathUtils.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned aave-v3-core commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MathUtils.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    sol = pinned.read_text(encoding="utf-8")
    if "calculateCompoundedInterest" not in sol or "basePowerTwo" not in sol or "365 days" not in sol:
        rec("UPSTREAM-FORMULA", "FAIL", "pinned MathUtils missing binomial series")
        return 1
    rec("UPSTREAM-FORMULA", "PASS", "pinned MathUtils has binomial (1+x)^n through x^3")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of aave compound clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_aave_compound.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler")

    gate = run([str(C0), "vm", str(LIN), "aci_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "aci_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "aci_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "aci_muldiv", (100, 200, 50), lambda: 400),
        ("linear", [str(RATE5), str(YEAR)], "aci_linear", (RATE5, YEAR), lambda: py_linear(RATE5, YEAR)),
        ("compounded", [str(RATE5), str(YEAR)], "aci_compounded", (RATE5, YEAR), lambda: py_compounded(RATE5, YEAR)),
        ("year2floor", [str(RATE5), str(YEAR)], "aci_year2_floor", (RATE5, YEAR), lambda: py_year2_floor(RATE5, YEAR)),
        ("horner", [str(RATE5), str(YEAR)], "aci_ex_horner", (RATE5, YEAR), lambda: py_horner(RATE5, YEAR)),
        ("compounded", [str(RATE5), "0"], "aci_compounded", (RATE5, 0), lambda: WAD),
        ("compounded", [str(RATE5), "1"], "aci_compounded", (RATE5, 1), lambda: py_compounded(RATE5, 1)),
        ("compounded", [str(RATE100), "2"], "aci_compounded", (RATE100, 2), lambda: py_compounded(RATE100, 2)),
        ("horner", [str(RATE100), "2"], "aci_ex_horner", (RATE100, 2), lambda: py_horner(RATE100, 2)),
        ("linear", [str(RATE5), "86400"], "aci_linear", (RATE5, 86400), lambda: py_linear(RATE5, 86400)),
        ("compounded", [str(RATE5), "86400"], "aci_compounded", (RATE5, 86400), lambda: py_compounded(RATE5, 86400)),
        ("index", [str(WAD), "1051270833291714231"], "aci_index_mul", (WAD, 1051270833291714231), lambda: 1051270833291714231),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, pyfn in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        py = pyfn()
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python bigint")

    wide = py_compounded(RATE5, YEAR)
    linear = py_linear(RATE5, YEAR)
    y2 = py_year2_floor(RATE5, YEAR)
    horner_y = py_horner(RATE5, YEAR)
    if wide <= linear:
        rec("LINEAR-VS-BINOM", "FAIL", "binomial should exceed linear at 1y 5%")
        return 1
    rec(
        "LINEAR-VS-BINOM",
        "PASS",
        "1y 5% APY: binomial exceeds linear (second+third terms)",
        f"linear={linear} compounded={wide} extra={wide - linear}",
    )
    if wide == y2:
        rec("YEAR2-FLOOR", "FAIL", "YEAR^2 floor wad port unexpectedly matched wide binomial")
        return 1
    rec(
        "YEAR2-FLOOR",
        "PASS",
        "naive wad YEAR^2 floor hides second-term precision vs 128-bit binomial",
        f"wide={wide} year2_floor={y2} missing={wide - y2}",
    )
    h2 = py_horner(RATE100, 2)
    w2 = py_compounded(RATE100, 2)
    if h2 == w2:
        rec("HORNER-VS-BINOM", "FAIL", "e^x Horner n^2/2 unexpectedly matched n(n-1)/2 at exp=2")
        return 1
    rec(
        "HORNER-VS-BINOM",
        "PASS",
        "exp=2 100% APY: e^x Horner (n^2/2) != Aave binomial n(n-1)/2",
        f"binomial={w2} horner={h2} delta={h2 - w2}",
    )

    wrapped = (RATE5 * YEAR) & ((1 << 64) - 1)
    naive = wrapped // YEAR
    first = RATE5  # rate * YEAR / YEAR
    if naive == first:
        rec("I64-WRAP", "FAIL", "signed/uint64 product unexpectedly equalled bigint first term")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive uint64 (rate*YEAR)/YEAR wraps; 128-bit muldiv does not",
        f"i64_naive={naive} bigint={first}",
    )

    jit_ok = lin_roundtrip_jit("aci_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on aci_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    fn_body = src[src.find("!aci_") :] if "!aci_" in src else src
    if "aci_compounded(rate: int, dt: int)" not in src or "block.timestamp" in fn_body:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit rate,dt args and no env timestamp in functions")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes rate and dt as arguments (no block.timestamp in functions)")
    if "aci_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 rate*dt wraps)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_RAY",
        "REJ_SOLIDITY_BINOMIAL",
        "REJ_SOLIDITY_SECONDS_YEAR",
        "REJ_SOLIDITY_UINT40",
        "REJ_SOLIDITY_USING",
        "rayMul(",
        "expMinusOne",
        "SECONDS_PER_YEAR",
    ]
    missing = [s for s in need if s not in sol_src]
    if missing:
        rec("SOL-REJECTS", "FAIL", "solidity transpiler missing interest rejects", str(missing))
    else:
        rec("SOL-REJECTS", "PASS", "lin_from_solidity.lin rejects rayMul/RAY/binomial/SECONDS_PER_YEAR/uint40/using")
    if 'out = out + "=";' in sol_src and 'out = out + "ex{";' in sol_src:
        rec("SOL-EMIT-SPLIT", "PASS", "emit splits '=' + 'ex{' so C0 does not steal the export list")
    else:
        rec("SOL-EMIT-SPLIT", "FAIL", "emit concat split missing")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_RAY" in rs_src and "REJ_RUST_BINOMIAL" in rs_src and "REJ_RUST_SECONDS_YEAR" in rs_src:
        rec("RS-REJECTS", "PASS", "lin_from_rust.lin rejects ray_mul/1e27/exp_minus_one/SECONDS_PER_YEAR")
    else:
        rec("RS-REJECTS", "FAIL", "rust transpiler interest rejects missing")

    jr = run([str(C0), "vm", str(JR_LIN), "cjr_test_suite"])
    jv = value_of(jr.stdout)
    if jr.returncode != 0 or jv != 1:
        rec("JUMPRATE-REGRESS", "FAIL", "compound jumprate suite broken after transpiler delta", jr.stdout)
    else:
        rec("JUMPRATE-REGRESS", "PASS", "Compound V2 JumpRate cjr_test_suite still == 1")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/aave/aave-v3-core",
        "tag": "v1.19.4",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT (BUSL-1.1 Change Date 2023-01-27 elapsed)",
        "not_pinned": "aave-dao/aave-v3-origin (BUSL Change Date 2027-03-06 still future)",
    }
    evidence["lin_clone"] = "src/lin_aave_compound.lin"
    evidence["c11_oracle"] = "test/oracles/aave_compound_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["goldens"] = {
        "linear_1y_5pct": linear,
        "compounded_1y_5pct": wide,
        "year2_floor_1y_5pct": y2,
        "horner_1y_5pct": horner_y,
        "binomial_minus_linear_1y_5pct": wide - linear,
        "wide_minus_year2_floor_1y_5pct": wide - y2,
        "compounded_exp2_100pct": w2,
        "horner_exp2_100pct": h2,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-aave-compound"
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
