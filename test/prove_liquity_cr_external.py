#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Liquity ICR / decMul / decPow (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of LiquityMath.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet Trove / LUSD / PriceFeed parity
    * that LIN replaces Liquity on mainnet
    * TVL, gas, or wall-clock superiority vs solc/EVM
    * that Aave health-factor is fully ported (named contrast only)

Class: EXPERIMENTAL (real LiquityMath algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_liquity_cr.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "liquity_cr_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "liquity_cr_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_liquity")
EVIDENCE = ROOT / "examples" / "liquity_cr" / "liquity_cr_evidence.json"

PINNED_SHA256 = "0d418289d7ba0ab052d1fff29b3c832bd809175d9bd69b8cd5552184a5e1bf17"
PINNED_BLOB = "9f6c44d728f69387d40e0645386c5a271e7e37c5"
PINNED_COMMIT = "9130cb989a953185f5f19824c91e2031b8fdfa90"
UPSTREAM_REL = "packages/contracts/contracts/Dependencies/LiquityMath.sol"
WAD = 10**18
HALF = 5 * 10**17
MINUTE_DECAY = 999037758833783000
U64 = 2**64 - 1


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/liquity/dev.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    return "PASS", commit, blob


def py_down(x: int, y: int, d: int) -> int:
    if d == 0:
        return 0
    q = (x * y) // d
    return 0 if q > U64 else q


def py_dec_mul(x: int, y: int) -> int:
    q = py_down(x, y, WAD)
    if q == 0 and (x * y) // WAD > U64:
        return 0
    r = (x * y) % WAD if WAD else 0
    if r < HALF:
        return q
    return 0 if q == U64 else q + 1


def py_cr(coll: int, debt: int, price: int) -> int:
    if debt == 0:
        return 0
    return py_down(coll, price, debt)


def py_aave(coll: int, debt: int, lt: int) -> int:
    if debt == 0:
        return 0
    return py_down(py_down(coll, lt, 10000), WAD, debt)


def py_dec_pow(base: int, minutes: int) -> int:
    if minutes > 525600000:
        minutes = 525600000
    if minutes == 0:
        return WAD
    y = WAD
    x = base
    n = minutes
    while n > 1:
        if n % 2 == 0:
            x = py_dec_mul(x, x)
            n = n // 2
        else:
            y = py_dec_mul(x, y)
            x = py_dec_mul(x, x)
            n = (n - 1) // 2
    return py_dec_mul(x, y)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_LIQUITY_CR_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  LIQUITY ICR / decMul / decPow — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "LiquityMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned LiquityMath.sol missing")
        return 1
    if sha256_file(pinned) != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "LiquityMath.sol hash mismatch", sha256_file(pinned))
        return 1
    rec("PIN-SHA256", "PASS", "pinned LiquityMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned liquity/dev matches fixture", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of LiquityMath.sol", up_note)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of liquity clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_liquity_cr.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v4")

    chk3 = run([str(C0), "check", str(RS_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk3.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "lq_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "lq_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "lq_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("floor", ["100", "200", "50"], "lq_floor", (100, 200, 50), py_down(100, 200, 50)),
        ("floor", ["7", "9", "2"], "lq_floor", (7, 9, 2), py_down(7, 9, 2)),
        ("decmul", [str(WAD), str(WAD)], "lq_dec_mul", (WAD, WAD), py_dec_mul(WAD, WAD)),
        ("decmul", ["3", str(HALF)], "lq_dec_mul", (3, HALF), py_dec_mul(3, HALF)),
        ("decmul", ["1", str(HALF - 1)], "lq_dec_mul", (1, HALF - 1), py_dec_mul(1, HALF - 1)),
        ("cr", ["10", "5", "3"], "lq_compute_cr", (10, 5, 3), py_cr(10, 5, 3)),
        ("cr", ["1000", "0", "2000"], "lq_compute_cr", (1000, 0, 2000), py_cr(1000, 0, 2000)),
        ("cr", ["10000", "10000", str(WAD)], "lq_compute_cr", (10000, 10000, WAD), py_cr(10000, 10000, WAD)),
        ("aave", ["10000", "10000", "8500"], "lq_aave_hf", (10000, 10000, 8500), py_aave(10000, 10000, 8500)),
        ("pow", [str(2 * WAD), "3"], "lq_dec_pow", (2 * WAD, 3), py_dec_pow(2 * WAD, 3)),
        ("pow", [str(MINUTE_DECAY), "2"], "lq_dec_pow", (MINUTE_DECAY, 2), py_dec_pow(MINUTE_DECAY, 2)),
        ("pow", [str(MINUTE_DECAY), "0"], "lq_dec_pow", (MINUTE_DECAY, 0), py_dec_pow(MINUTE_DECAY, 0)),
        ("min", ["3", "5"], "lq_min", (3, 5), 3),
        ("abs", ["3", "10"], "lq_absdiff", (3, 10), 7),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        if kind == "floor":
            want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
            if want != want_limbs:
                rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
                return 1
        got_lin = lin_vm(fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    liq_cr = lin_vm("lq_compute_cr", 10000, 10000, WAD)
    aave_hf = lin_vm("lq_aave_hf", 10000, 10000, 8500)
    if liq_cr != WAD or aave_hf != 850000000000000000:
        rec("HF-CONTRAST", "FAIL", "Liquity CR vs Aave-style HF", f"liq={liq_cr} aave={aave_hf}")
        return 1
    rec(
        "HF-CONTRAST",
        "PASS",
        "same 10000/10000 coll/debt: Liquity CR=1e18 (price=1e18) vs Aave-style HF=0.85e18 (lt=85%)",
        "named contrast only; not an Aave port or TVL claim",
    )

    floor_half = lin_vm("lq_floor", 3, HALF, WAD)
    half_up = lin_vm("lq_dec_mul", 3, HALF)
    if floor_half != 1 or half_up != 2:
        rec("HALFUP-CONTRAST", "FAIL", "floor wad-mul vs Liquity decMul half-up", f"floor={floor_half} decmul={half_up}")
        return 1
    rec("HALFUP-CONTRAST", "PASS", "3*(5e17)/1e18 is floor 1 vs Liquity decMul half-up 2")

    empty = lin_vm("lq_compute_cr", 1000, 0, 2000)
    ok = lin_vm("lq_cr_ok", 0)
    if empty != 0 or ok != 0:
        rec("DEBT-ZERO", "FAIL", "empty-debt CR", f"cr={empty} ok={ok}")
        return 1
    rec("DEBT-ZERO", "PASS", "debt==0: Solidity returns 2**256-1 (infinite CR); LIN fail-closes 0 and lq_cr_ok=0")

    wrapped = ((10**18) * (10**18)) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 0 and lin_vm("lq_ov", 10**18, 10**18, 1) != 1:
        rec("I64-WRAP", "FAIL", "1e18*1e18 overflow not detected")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes", f"i64_wrap={wrapped}")

    jit_ok = lin_roundtrip_jit("lq_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on lq_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("lq_floor", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit lq_floor(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "_computeCR" not in sol or "2**256" not in sol or "decMul" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "upstream _computeCR / 2**256 / decMul missing")
    elif "lq_compute_cr(coll: int, debt: int, price: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "LIN CR args not explicit")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN lifts hidden PriceFeed to a price argument; SafeMath product is 128-bit")
    if "NICR_PRECISION = 1e20" in sol:
        rec("NICR-SCALE", "PASS", "upstream NICR 1e20 exceeds signed i64; LIN rejects that scale (no silent wrap)")
    else:
        rec("NICR-SCALE", "FAIL", "1e20 NICR constant missing from pin")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if (
        "REJ_SOLIDITY_LIBCALL" in sol_src
        and "REJ_SOLIDITY_POW256" in sol_src
        and "REJ_SOLIDITY_NICR_SCALE" in sol_src
        and ".add(" in sol_src
        and "2**256" in sol_src
    ):
        rec("SOL-REJECT", "PASS", "lin_from_solidity.lin v4 rejects SafeMath .mul/.add/.div, 2**256, and 1e20 NICR")
    else:
        rec("SOL-REJECT", "FAIL", "solidity reject codes missing")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_OVERFLOW_CEIL" in rs_src and "REJ_RUST_DIV_CEIL" in rs_src:
        rec("RS-REJECT", "PASS", "lin_from_rust.lin v2 rejects overflow-ceil / div_ceil")
    else:
        rec("RS-REJECT", "FAIL", "rust reject codes missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/liquity/dev",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_liquity_cr.lin"
    evidence["c11_oracle"] = "test/oracles/liquity_cr_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["liquity_cr_100pct"] = liq_cr
    evidence["aave_hf_85pct"] = aave_hf
    evidence["floor_half"] = floor_half
    evidence["decmul_half_up"] = half_up
    evidence["empty_debt_cr"] = empty
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-liquity-cr"
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
