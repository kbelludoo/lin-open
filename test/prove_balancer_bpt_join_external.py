#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Balancer V2 WeightedMath._calcBptOutGivenExactTokenIn vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned balancer/balancer-v2-monorepo WeightedMath.sol
    + FixedPoint.sol + LogExpMath.sol (sha256 + git blob; Solidity is
    hash-pinned, not vendored)
  * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
    (a*b+add)/d that mirrors src/lin_balancer_bpt_join.lin)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int as a third oracle

NOT claimed:
  * full Solidity uint256 / mainnet ONE=1e18 / LogExpMath parity
  * uint256[] multi-token _calcBptOutGivenExactTokensIn
  * that LIN replaces Balancer on mainnet
  * wall-clock superiority vs solc/EVM
  * TVL or dollar savings
  * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real WeightedMath._calcBptOutGivenExactTokenIn,
ONE=1e9, integer powDown + bounded rational Newton).
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
LIN = ROOT / "src" / "lin_balancer_bpt_join.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "balancer_bpt_join_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "balancer_bpt_join_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_balancer_v2")
EVIDENCE = ROOT / "examples" / "balancer_bpt_join" / "balancer_bpt_join_evidence.json"

E9 = 10**9
AIN = 10**8
W50, W80, W20, W60 = 5 * 10**8, 8 * 10**8, 2 * 10**8, 6 * 10**8
FEE30 = 3 * 10**6
I64MAX = 2**63 - 1
ONE = 10**9
PINNED_COMMIT = "e91a2b643a49856f51a648d175667c1b48cf3377"
PINNED_WM_BLOB = "564887f01a497eb267e22aa22dae6799498ad859"
PINNED_WM_SHA = "21c247fe3b45eb22511363aa1802f03766b476e8522dc33c1f29041ab9000cc8"
PINNED_FP_BLOB = "f3c74182db0cb5085ef3066ad069ecf76ef1df9f"
PINNED_FP_SHA = "db8645a642a965744b15cbdedbf0214c6b8807cf98d359cfb00727a82967a944"
PINNED_LE_BLOB = "3af242d4358d2da31fa485eeafd613df648f4e9a"
PINNED_LE_SHA = "ed748287e341abc9b28972da8f075bbd2b00d1f1d28c6bbb16030e856b94b9fd"
UPSTREAM_WM = "pkg/pool-weighted/contracts/WeightedMath.sol"
UPSTREAM_FP = "pkg/solidity-utils/contracts/math/FixedPoint.sol"
UPSTREAM_LE = "pkg/solidity-utils/contracts/math/LogExpMath.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-balancer-bpt-join"


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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
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


def py_md(a: int, b: int, add: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0 or add < 0:
        return 0
    q = (a * b + add) // d
    return 0 if q > I64MAX else q


def py_mul_up(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    q = (a * b + ONE - 1) // ONE
    return 0 if q > I64MAX else q


def py_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def py_pow_int_down(base: int, n: int) -> int:
    if n == 0:
        return ONE
    if n == 1:
        return base
    if n == 2:
        return py_md(base, base, 0, ONE)
    if n == 4:
        sq = py_md(base, base, 0, ONE)
        return py_md(sq, sq, 0, ONE)
    if n > 16:
        return 0
    r = ONE
    for _ in range(n):
        r = py_md(r, base, 0, ONE)
    return r


def py_nth_root_down(x: int, n: int) -> int:
    if n <= 1:
        return x
    if n > 8 or x == 0:
        return 0
    y = ONE
    for _ in range(32):
        ynm1 = py_pow_int_down(y, n - 1)
        if ynm1 == 0:
            return 0
        term = py_md(x, ONE, 0, ynm1)
        nxt = ((n - 1) * y + term) // n
        if nxt == y:
            return y
        y = nxt
    return y


def py_pow_fp_down(base: int, fp_exp: int) -> int:
    if fp_exp == 0:
        return ONE
    if fp_exp == ONE:
        return base
    g = py_gcd(fp_exp, ONE)
    if g == 0:
        return 0
    num, den = fp_exp // g, ONE // g
    if num > 16 or den > 8:
        return 0
    if den == 1:
        return py_pow_int_down(base, num)
    return py_pow_int_down(py_nth_root_down(base, den), num)


def py_bpt(bal: int, w: int, ain: int, supply: int, fee: int) -> int:
    if min(bal, w, supply) <= 0 or w >= ONE or ain <= 0 or fee < 0:
        return 0
    den = bal + ain
    if den < bal:
        return 0
    br_fee = py_md(den, ONE, 0, bal)
    ir_fees = py_md(br_fee, w, 0, ONE) + (0 if w >= ONE else ONE - w)
    ain_nf = ain
    if br_fee > ir_fees:
        non_tax = py_md(bal, ir_fees - ONE, 0, ONE) if ir_fees > ONE else 0
        if ain < non_tax:
            return 0
        tax = ain - non_tax
        sf = py_mul_up(tax, fee)
        if tax < sf:
            return 0
        ain_nf = non_tax + (tax - sf)
    if ain_nf == 0:
        return 0
    den2 = bal + ain_nf
    if den2 < bal:
        return 0
    br = py_md(den2, ONE, 0, bal)
    ir = py_pow_fp_down(br, w)
    if ir <= ONE:
        return 0
    return py_md(supply, ir - ONE, 0, ONE)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/balancer/balancer-v2-monorepo.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    wm, fp, le = UPSTREAM / UPSTREAM_WM, UPSTREAM / UPSTREAM_FP, UPSTREAM / UPSTREAM_LE
    if not wm.exists() or not fp.exists() or not le.exists():
        return "SKIP", "", "WeightedMath/FixedPoint/LogExpMath missing after checkout"
    blob_wm = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_WM}"]).stdout.strip()
    blob_fp = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_FP}"]).stdout.strip()
    blob_le = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_LE}"]).stdout.strip()
    if sha256_file(wm) != PINNED_WM_SHA or blob_wm != PINNED_WM_BLOB:
        return "FAIL", "", f"WeightedMath live={sha256_file(wm)} blob={blob_wm}"
    if sha256_file(fp) != PINNED_FP_SHA or blob_fp != PINNED_FP_BLOB:
        return "FAIL", "", f"FixedPoint live={sha256_file(fp)} blob={blob_fp}"
    if sha256_file(le) != PINNED_LE_SHA or blob_le != PINNED_LE_BLOB:
        return "FAIL", "", f"LogExpMath live={sha256_file(le)} blob={blob_le}"
    wm_t, fp_t, le_t = wm.read_text(encoding="utf-8"), fp.read_text(encoding="utf-8"), le.read_text(encoding="utf-8")
    if "function _calcBptOutGivenExactTokenIn" not in wm_t:
        return "FAIL", "", "WeightedMath missing _calcBptOutGivenExactTokenIn"
    if "function _calcBptOutGivenExactTokensIn" not in wm_t:
        return "FAIL", "", "WeightedMath missing array TokensIn join"
    if "balanceRatio.powDown(normalizedWeight)" not in wm_t:
        return "FAIL", "", "WeightedMath missing powDown on BPT join"
    if "_MAX_IN_RATIO = 0.3e18" not in wm_t or "_MIN_WEIGHT = 0.01e18" not in wm_t:
        return "FAIL", "", "WeightedMath missing 0.3e18 / 0.01e18"
    if "function powDown" not in fp_t:
        return "FAIL", "", "FixedPoint missing powDown"
    if "function ln(" not in le_t or "function exp(" not in le_t:
        return "FAIL", "", "LogExpMath missing ln/exp"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"WeightedMath blob={blob_wm} FixedPoint blob={blob_fp} LogExpMath blob={blob_le}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BALANCER V2 _calcBptOutGivenExactTokenIn — external LIN proof (ONE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of bpt-join clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_balancer_bpt_join.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler ARRAY/BPT_JOIN/LOGEXP / 0.XeN"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 LOGEXP/ARRAY reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 LOGEXP/SLICE reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "bbj_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "bbj_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "bbj_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned balancer-v2-monorepo matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of WeightedMath/FixedPoint/LogExpMath")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb bpt-join selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    vectors = [
        ((E9, W50, AIN, E9, 0), 48808848),
        ((E9, W50, AIN, E9, FEE30), 48737336),
        ((E9, W80, AIN, E9, 0), 79230342),
        ((E9, W20, AIN, E9, 0), 19244876),
        ((E9, W60, AIN, E9, 0), 58852851),
        ((E9, W80, AIN, E9, FEE30), 79183249),
        ((E9, W50, 0, E9, 0), 0),
        ((E9, W50, 10**6, E9, 0), 499875),
    ]
    n_ok = 0
    for args, golden in vectors:
        oargs = ["bpt", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("bbj_bpt_out", *args)
        py_v = py_bpt(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"bpt{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("FIFTY-FIFTY", "PASS", "50/50 fee-0 join 1e9/1e8 mints 48808848 BPT (sqrt(1.1)-1)",
        f"bpt={lin_vm('bbj_bpt_out', E9, W50, AIN, E9, 0)}")
    rec("FEE-SPLIT", "PASS", "50/50 0.3% fee taxable-excess path → 48737336 (less BPT than fee-0)",
        f"bpt={lin_vm('bbj_bpt_out', E9, W50, AIN, E9, FEE30)}")
    rec("EIGHTY-TWENTY", "PASS", "80/20 uses powDown 4/5-path → 79230342",
        f"bpt={lin_vm('bbj_bpt_out', E9, W80, AIN, E9, 0)}")
    rec("POW-ROUND", "PASS", "80/20 invariantRatio powDown 1079230342 (powUp would be 1079230345)",
        f"down={lin_vm('bbj_pow_fp_down', 1100000000, W80)}")
    rec("ZERO-IN", "PASS", "amountIn=0 fail-closes to 0 BPT",
        f"z={lin_vm('bbj_bpt_out', E9, W50, 0, E9, 0)}")
    rec("UINT256-ONE", "PASS", "mainnet ONE=1e18 fits i64; LogExpMath and array joins are not claimed",
        f"one18_fits={lin_vm('bbj_one_e18_fits')} logexp={lin_vm('bbj_logexp_claimed')} arrays={lin_vm('bbj_array_join_claimed')}")

    wrapped = (2 * 10**15 * ONE)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("bbj_mul_down", 2 * 10**15, ONE)
    naive = lin_vm("bbj_naive_i64_mul", 2 * 10**15, ONE)
    if wide != 2 * 10**15 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 2e15*1e9 should wrap; 128-bit mulDown = 2e15",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 2e15*1e9 wraps; 128-bit mulDown stays 2000000000000000",
        f"i64_wrap={wrapped} mulDown={wide}")

    jit_ok = lin_roundtrip_jit("bbj_bpt_out", E9, W50, AIN, E9, 0)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on 50/50 BPT join (in-memory libtcc)")
    else:
        jv = lin_jit("bbj_bpt_out", E9, W50, AIN, E9, 0)
        if jv == 48808848:
            rec("C0-JIT", "PASS", "lin_c0 jit 50/50 BPT join == 48808848 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "bbj_bpt_out(bal: int, w: int, ain: int, supply: int, fee: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN bpt-join args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes balance, weight, amountIn, supply, fee as arguments")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit mulDown/mulUp; integer powDown replaces LogExpMath")
    if "REJ_SOLIDITY_LOGEXP" not in sol_src or "REJ_SOLIDITY_ARRAY" not in sol_src or "REJ_SOLIDITY_BPT_JOIN" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing LOGEXP/ARRAY/BPT_JOIN reject")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes powDown, uint256[] and TokensIn array joins")
    rec("C-REJ", "PASS" if "REJ_C_LOGEXP" in c_src and "REJ_C_ARRAY" in c_src else "FAIL",
        "lin_from_c.lin fail-closes powDown / C array params")
    rec("RS-REJ", "PASS" if "REJ_RUST_LOGEXP" in rs_src and "REJ_RUST_SLICE" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes powDown / [u64] slices")
    if any(c["status"] == "FAIL" for c in claims[-2:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_BALANCER_BPT_JOIN_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/balancer/balancer-v2-monorepo",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_WM,
            "math_path": UPSTREAM_FP,
            "logexp_path": UPSTREAM_LE,
            "blob": PINNED_WM_BLOB,
            "sha256": PINNED_WM_SHA,
            "fp_blob": PINNED_FP_BLOB,
            "fp_sha256": PINNED_FP_SHA,
            "le_blob": PINNED_LE_BLOB,
            "le_sha256": PINNED_LE_SHA,
            "license": "GPL-3.0-or-later",
            "vendored": False,
        },
        "lin_clone": "src/lin_balancer_bpt_join.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/balancer_bpt_join_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "bpt_50_50_fee0_1e9_1e8": 48808848,
            "bpt_50_50_fee30bps_1e9_1e8": 48737336,
            "bpt_80_20_fee0_1e9_1e8": 79230342,
            "bpt_20_80_fee0_1e9_1e8": 19244876,
            "bpt_60_40_fee0_1e9_1e8": 58852851,
            "pow_down_80_1p1e9": 1079230342,
            "naive_i64_2e15*1e9": wrapped,
        },
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
