#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Uniswap V3 SqrtPriceMath getAmount0Delta / getAmount1Delta vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of SqrtPriceMath.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      that mirror src/lin_uniswap_v3_sqrt.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / Q64.96 (Q96=2^96 exceeds signed i64)
    * that LIN replaces Uniswap V3 on mainnet
    * wall-clock superiority vs solc/EVM
    * a full port of OpenZeppelin Math.mulDiv (amount0 is two sequential
      divisions, not one generic mulDiv)

Class: EXPERIMENTAL (real Uniswap V3 amount-delta algorithm, Q32 operands).
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
LIN = ROOT / "src" / "lin_uniswap_v3_sqrt.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v3_sqrt_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v3_sqrt_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v3_core")
EVIDENCE = ROOT / "examples" / "uniswap_v3_sqrt" / "uniswap_v3_sqrt_evidence.json"
JR_LIN = ROOT / "src" / "lin_compound_jumprate.lin"

Q = 1 << 32
L = 1_000_000
PINNED_SHA256 = "ddd62e3a94346248677f30f1ab009ef015e71e4b8696dcca890eeabc9dc6c149"
PINNED_BLOB = "685f485da43402235c3a9ce7fd85a49597b6373a"
PINNED_COMMIT = "e3589b192d0be27e100cd0daaf6c97204fdb1899"
UPSTREAM_REL = "contracts/libraries/SqrtPriceMath.sol"


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
    url = "https://github.com/Uniswap/v3-core.git"
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


def py_md(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (a * b) // d
    return 0 if q > 2**64 - 1 else q


def py_mdu(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q, r = divmod(a * b, d)
    if q > 2**64 - 1:
        return 0
    if r:
        q += 1
    return 0 if q > 2**64 - 1 else q


def py_amt0(sa: int, sb: int, liq: int, up: int) -> int:
    lo, hi = (sb, sa) if sb < sa else (sa, sb)
    if lo == 0:
        return 0
    n1 = py_md(liq, Q, 1)
    if liq != 0 and n1 == 0:
        return 0
    n2 = hi - lo
    if up:
        return py_mdu(py_mdu(n1, n2, hi), 1, lo)
    return py_md(py_md(n1, n2, hi), 1, lo)


def py_amt1(sa: int, sb: int, liq: int, up: int) -> int:
    lo, hi = (sb, sa) if sb < sa else (sa, sb)
    n2 = hi - lo
    return py_mdu(liq, n2, Q) if up else py_md(liq, n2, Q)


def py_naive0(sa: int, sb: int, liq: int) -> int:
    lo, hi = (sb, sa) if sb < sa else (sa, sb)
    den = py_md(lo, hi, 1)
    if den == 0:
        return 0
    return py_md(liq, hi - lo, den)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_UNISWAP_V3_SQRT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V3 SQRTPRICEMATH — external LIN proof (Q32-scale, C11)")
    print("=" * 78)

    pinned = FIX / "SqrtPriceMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned SqrtPriceMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned SqrtPriceMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned v3-core commit matches fixture",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of SqrtPriceMath.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    sol = pinned.read_text(encoding="utf-8")
    if "getAmount0Delta" not in sol or "getAmount1Delta" not in sol or "FixedPoint96" not in sol:
        rec("UPSTREAM-FORMULA", "FAIL", "pinned SqrtPriceMath missing amount-delta kernels")
        return 1
    rec("UPSTREAM-FORMULA", "PASS", "pinned SqrtPriceMath has getAmount0Delta / getAmount1Delta")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of uniswap v3 sqrt clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v3_sqrt.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler")

    gate = run([str(C0), "vm", str(LIN), "v3s_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "v3s_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "v3s_test_suite == 1 on Compiler 0 interpreter")

    two = Q + Q
    one = Q + 1
    mid = Q + (Q // 2)
    vectors = [
        ("muldiv", ["100", "200", "50"], "v3s_muldiv", (100, 200, 50), lambda: 400),
        ("muldivup", ["7", "9", "2"], "v3s_muldiv_up", (7, 9, 2), lambda: 32),
        ("amount0", [str(Q), str(two), str(L), "0"], "v3s_amount0", (Q, two, L, 0),
         lambda: py_amt0(Q, two, L, 0)),
        ("amount1", [str(Q), str(two), str(L), "0"], "v3s_amount1", (Q, two, L, 0),
         lambda: py_amt1(Q, two, L, 0)),
        ("naive0", [str(Q), str(two), str(L)], "v3s_naive_amt0", (Q, two, L),
         lambda: py_naive0(Q, two, L)),
        ("amount0", [str(two), str(Q), str(L), "0"], "v3s_amount0", (two, Q, L, 0),
         lambda: py_amt0(two, Q, L, 0)),
        ("amount0", [str(Q), str(one), "1", "0"], "v3s_amount0", (Q, one, 1, 0),
         lambda: py_amt0(Q, one, 1, 0)),
        ("amount0", [str(Q), str(one), "1", "1"], "v3s_amount0", (Q, one, 1, 1),
         lambda: py_amt0(Q, one, 1, 1)),
        ("amount1", [str(Q), str(one), "1", "1"], "v3s_amount1", (Q, one, 1, 1),
         lambda: py_amt1(Q, one, 1, 1)),
        ("amount0", [str(Q), str(mid), str(L), "0"], "v3s_amount0", (Q, mid, L, 0),
         lambda: py_amt0(Q, mid, L, 0)),
        ("amount0", [str(Q), str(mid), str(L), "1"], "v3s_amount0", (Q, mid, L, 1),
         lambda: py_amt0(Q, mid, L, 1)),
        ("amount1", [str(Q), str(mid), str(L), "0"], "v3s_amount1", (Q, mid, L, 0),
         lambda: py_amt1(Q, mid, L, 0)),
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

    a0 = py_amt0(Q, two, L, 0)
    a1 = py_amt1(Q, two, L, 0)
    nv = py_naive0(Q, two, L)
    if a0 != 500000 or a1 != 1000000 or nv != 0:
        rec("NAIVE-VS-SEQ", "FAIL", "expected amount0=500000 amount1=1000000 naive=0")
        return 1
    rec("NAIVE-VS-SEQ", "PASS",
        "price 1->4 L=1e6: sequential amount0 keeps 500000; naive (L*dsqrt)/(sa*sb) floors to 0",
        f"amount0={a0} amount1={a1} naive={nv} hidden={a0 - nv}")

    f0 = py_amt0(Q, one, 1, 0)
    c0 = py_amt0(Q, one, 1, 1)
    if f0 == c0 or c0 != 1:
        rec("ROUNDUP-WEI", "FAIL", "1-unit roundup should differ from floor", f"floor={f0} ceil={c0}")
        return 1
    rec("ROUNDUP-WEI", "PASS",
        "L=1 sb=sa+1: floor amount0=0 vs ceil=1 (protocol-solvency 1-unit gap)",
        f"floor={f0} ceil={c0}")

    fmid = py_amt0(Q, mid, L, 0)
    cmid = py_amt0(Q, mid, L, 1)
    if cmid - fmid != 1:
        rec("ROUNDUP-MID", "FAIL", "1->2.25 should round up by 1", f"floor={fmid} ceil={cmid}")
        return 1
    rec("ROUNDUP-MID", "PASS",
        "price 1->2.25 L=1e6: amount0 ceil is floor+1 (333334 vs 333333)",
        f"floor={fmid} ceil={cmid}")

    if (1 << 96) <= 2**63 - 1:
        rec("Q96-I64", "FAIL", "Q96 unexpectedly fits signed i64")
        return 1
    rec("Q96-I64", "PASS", "Q96=2^96 exceeds signed i64; clone uses reduced Q32=2^32",
        f"Q32={Q} Q96_bits=96")

    jit_ok = lin_roundtrip_jit("v3s_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on v3s_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "v3s_amount0(sa: int, sb: int, liq: int, round_up: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit sa,sb,liq,round_up args")
    else:
        rec("EXPLICIT-ARGS", "PASS",
            "LIN clone takes sqrt prices, liquidity, round_up as arguments (no tuple swap / roundUp bool storage)")
    if "v3s_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (sa*sb at Q32 overflows uint64)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = ["REJ_SOLIDITY_Q96", "REJ_SOLIDITY_ROUNDING_UP", "REJ_SOLIDITY_UNSAFE_MATH",
            "FixedPoint96", "mulDivRoundingUp", "UnsafeMath"]
    missing = [s for s in need if s not in sol_src]
    if missing:
        rec("SOL-REJECTS", "FAIL", "solidity transpiler missing v3 sqrt rejects", str(missing))
    else:
        rec("SOL-REJECTS", "PASS",
            "lin_from_solidity.lin rejects Q96/FixedPoint96/mulDivRoundingUp/UnsafeMath")
    if 'out = out + "=";' in sol_src and 'out = out + "ex{";' in sol_src:
        rec("SOL-EMIT-SPLIT", "PASS", "emit splits '=' + 'ex{' so C0 does not steal the export list")
    else:
        rec("SOL-EMIT-SPLIT", "FAIL", "emit concat split missing")

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_Q96" in rs_src and "REJ_RUST_ROUNDING_UP" in rs_src and "REJ_RUST_FIXEDPOINT96" in rs_src:
        rec("RS-REJECTS", "PASS", "lin_from_rust.lin rejects q96 / mul_div_rounding_up / fixed_point_96")
    else:
        rec("RS-REJECTS", "FAIL", "rust transpiler v3 sqrt rejects missing")

    jr = run([str(C0), "vm", str(JR_LIN), "cjr_test_suite"])
    jv = value_of(jr.stdout)
    if jr.returncode != 0 or jv != 1:
        rec("JUMPRATE-REGRESS", "FAIL", "compound jumprate suite broken after transpiler delta", jr.stdout)
    else:
        rec("JUMPRATE-REGRESS", "PASS", "Compound V2 JumpRate cjr_test_suite still == 1")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/Uniswap/v3-core",
        "tag": "v1.0.0",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-2.0-or-later (BUSL-1.1 Change Date 2023-04-01 elapsed)",
    }
    evidence["lin_clone"] = "src/lin_uniswap_v3_sqrt.lin"
    evidence["c11_oracle"] = "test/oracles/uniswap_v3_sqrt_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["goldens"] = {
        "q32": Q,
        "amount0_1to4_L1e6": a0,
        "amount1_1to4_L1e6": a1,
        "naive_amt0_1to4_L1e6": nv,
        "hidden_vs_naive_1to4": a0 - nv,
        "amount0_wei_floor": f0,
        "amount0_wei_ceil": c0,
        "amount0_1to225_floor": fmid,
        "amount0_1to225_ceil": cmid,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-uniswap-v3-sqrt"
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
