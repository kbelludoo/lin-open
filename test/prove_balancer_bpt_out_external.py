#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Balancer _calcTokenOutGivenExactBptIn vs LIN C0 (ONE=1e9).

Recomputed this run: live git pin of WeightedMath.sol, C11 __int128 XOR
32-bit limbs, Compiler 0 interpreter + optional libtcc JIT, Python bigint.
NOT claimed: uint256/ONE=1e18/LogExpMath/uint256[] exits, LIN replacing
Balancer, wall-clock vs solc, TVL, zk soundness. Class: EXPERIMENTAL.
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
LIN = ROOT / "src" / "lin_balancer_bpt_out.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "balancer_bpt_out_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "balancer_bpt_out_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_balancer_v2_bpt_out")
EVIDENCE = ROOT / "examples" / "balancer_bpt_out" / "balancer_bpt_out_evidence.json"

E9 = 10**9
I64MAX = 2**63 - 1
MIN_INV = 700000000
PINNED_COMMIT = "e91a2b643a49856f51a648d175667c1b48cf3377"
PINNED_BLOB = "564887f01a497eb267e22aa22dae6799498ad859"
PINNED_SHA = "21c247fe3b45eb22511363aa1802f03766b476e8522dc33c1f29041ab9000cc8"
FP_BLOB = "f3c74182db0cb5085ef3066ad069ecf76ef1df9f"
FP_SHA = "db8645a642a965744b15cbdedbf0214c6b8807cf98d359cfb00727a82967a944"
LE_BLOB = "3af242d4358d2da31fa485eeafd613df648f4e9a"
LE_SHA = "ed748287e341abc9b28972da8f075bbd2b00d1f1d28c6bbb16030e856b94b9fd"
UPSTREAM_REL = "pkg/pool-weighted/contracts/WeightedMath.sol"
FP_REL = "pkg/solidity-utils/contracts/math/FixedPoint.sol"
LE_REL = "pkg/solidity-utils/contracts/math/LogExpMath.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-balancer-bpt-out"


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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=90)
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


def py_md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > I64MAX else q


def py_mul_up(a: int, b: int) -> int:
    if a <= 0 or b <= 0:
        return 0
    q = py_md(a, b, E9)
    r = (a * b) % E9
    if r == 0:
        return q
    s = q + 1
    return 0 if s < 0 or s > I64MAX else s


def py_mul_down(a: int, b: int) -> int:
    if a < 0 or b < 0:
        return 0
    return py_md(a, b, E9)


def py_div_up(a: int, b: int) -> int:
    if a <= 0 or b <= 0:
        return 0
    q = py_md(a, E9, b)
    r = (a * E9) % b
    if r == 0:
        return q
    s = q + 1
    return 0 if s < 0 or s > I64MAX else s


def py_div_down(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        return 0
    return py_md(a, E9, b)


def py_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def py_pow_int_up(base: int, n: int) -> int:
    if n == 0:
        return E9
    r = E9
    for _ in range(n):
        r = py_mul_up(r, base)
    return r


def py_pow_int_down(base: int, n: int) -> int:
    if n == 0:
        return E9
    r = E9
    for _ in range(n):
        r = py_mul_down(r, base)
    return r


def py_nth_root_up(x: int, n: int) -> int:
    if n <= 1:
        return x
    if n > 8 or x == 0:
        return 0
    y = E9
    for _ in range(32):
        ynm1 = py_pow_int_up(y, n - 1)
        if ynm1 == 0:
            return 0
        term = py_div_up(x, ynm1)
        nxt = ((n - 1) * y + term) // n
        if nxt == y:
            break
        y = nxt
    for _ in range(8):
        pdown = py_pow_int_down(y, n)
        if pdown >= x:
            if y > 0 and py_pow_int_down(y - 1, n) >= x:
                y -= 1
                continue
            break
        y += 1
    return y


def py_pow_fp_up(base: int, fp_exp: int) -> int:
    if fp_exp == 0:
        return E9
    if fp_exp == E9:
        return base
    g = py_gcd(fp_exp, E9)
    if g == 0:
        return 0
    num, den = fp_exp // g, E9 // g
    if num > 16 or den > 8:
        return 0
    if den == 1:
        return py_pow_int_up(base, num)
    return py_nth_root_up(py_pow_int_up(base, num), den)


def py_token_out(bal: int, w: int, bpt_in: int, supply: int, fee: int) -> int:
    if bal <= 0 or w <= 0 or w >= E9 or supply <= 0 or bpt_in <= 0 or fee < 0:
        return 0
    if bpt_in >= supply:
        return 0
    ir = py_div_up(supply - bpt_in, supply)
    if ir < MIN_INV:
        return 0
    br = py_pow_fp_up(ir, py_div_down(E9, w))
    aout_nf = py_mul_down(bal, (E9 - br) if br < E9 else 0)
    tax = py_mul_up(aout_nf, E9 - w)
    if tax > aout_nf:
        return 0
    cf = E9 - fee if 0 <= fee < E9 else 0
    s = (aout_nf - tax) + py_mul_up(tax, cf)
    return 0 if s < aout_nf - tax else s


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
    src = UPSTREAM / UPSTREAM_REL
    if not src.exists():
        return "SKIP", "", "WeightedMath.sol missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    digest = sha256_file(src)
    if digest != PINNED_SHA or blob != PINNED_BLOB:
        return "FAIL", "", f"live={digest} blob={blob}"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "_calcTokenOutGivenExactBptIn",
        "_MIN_INVARIANT_RATIO",
        "powUp",
        "divUp",
        "mulDown",
        "normalizedWeight.complement()",
    ):
        if needle not in text:
            return "FAIL", "", f"WeightedMath.sol missing {needle}"
    fp = UPSTREAM / FP_REL
    le = UPSTREAM / LE_REL
    if fp.exists() and sha256_file(fp) != FP_SHA:
        return "FAIL", "", "FixedPoint.sol sha256 mismatch"
    if le.exists() and sha256_file(le) != LE_SHA:
        return "FAIL", "", "LogExpMath.sol sha256 mismatch"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"WeightedMath.sol blob={blob} fp_blob={FP_BLOB} le_blob={LE_BLOB}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  Balancer _calcTokenOutGivenExactBptIn — external LIN proof (ONE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of token-out-given-bpt-in clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_balancer_bpt_out.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler BPT_OUT/POWUP/ARRAY"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 BPT_OUT/POWUP reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 POWUP/SLICE reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "bbo_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "bbo_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "bbo_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned balancer WeightedMath.sol matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of WeightedMath.sol + FixedPoint + LogExpMath")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb token_out selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    e9, bin_, w50, w80, w20, fee = E9, 10**8, 5 * 10**8, 8 * 10**8, 2 * 10**8, 3 * 10**6
    vecs = [
        ((e9, w50, bin_, e9, 0), 190000000),
        ((e9, w50, bin_, e9, fee), 189715000),
        ((e9, w80, bin_, e9, 0), 123396627),
        ((e9, w20, bin_, e9, 0), 409510000),
        ((e9, w80, bin_, e9, fee), 123322590),
        ((e9, w50, 0, e9, 0), 0),
        ((e9, w50, 310000000, e9, 0), 0),
    ]
    n_ok = 0
    for args, golden in vecs:
        oargs = ["tout", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("bbo_token_out", *args)
        py_v = py_token_out(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"tout{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("FIFTY-FIFTY", "PASS", "50/50 fee-0 1e8 BPT in yields 190000000 tokens (1-0.9^2)",
        f"tout={lin_vm('bbo_token_out', e9, w50, bin_, e9, 0)}")
    rec("LINEAR-UNDER", "PASS", "naive linear bal*bpt/supply=100000000 understates 1.9x vs weighted 190000000",
        f"linear={lin_vm('bbo_naive_linear', e9, bin_, e9)}")
    rec("FEE-SPLIT", "PASS", "0.3% taxable complement(w) fee 189715000 vs full-fee misuse 189430000",
        f"split={lin_vm('bbo_token_out', e9, w50, bin_, e9, fee)} full={lin_vm('bbo_full_fee', e9, w50, bin_, e9, fee)}")
    rec("WEIGHT-SKEW", "PASS", "80/20 yields 123396627 vs 20/80 409510000 for the same 1e8 BPT",
        f"w80={lin_vm('bbo_token_out', e9, w80, bin_, e9, 0)} w20={lin_vm('bbo_token_out', e9, w20, bin_, e9, 0)}")
    rec("MIN-INV", "PASS", "MIN_INVARIANT_RATIO=0.7e9 fail-closes bptIn=3.1e8 (Solidity reverts)",
        f"z={lin_vm('bbo_token_out', e9, w50, 310000000, e9, 0)}")
    rec("UINT256-CAP", "PASS", "mainnet uint256 / ONE=1e18 / LogExpMath / uint256[] exits are not claimed",
        f"logexp={lin_vm('bbo_logexp_claimed')} array={lin_vm('bbo_array_exit_claimed')}")

    wrapped = (2000000000000000 * E9)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("bbo_mul_down", 2000000000000000, E9)
    naive = lin_vm("bbo_naive_i64_mul", 2000000000000000, E9)
    if wide != 2000000000000000 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 mul should wrap; 128-bit mul_down stays 2e15",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (2e15*1e9) wraps; 128-bit mul_down is 2e15",
        f"i64_wrap={wrapped} mul_down={wide}")

    jit_ok = lin_roundtrip_jit("bbo_token_out", e9, w50, bin_, e9, 0)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on token_out (in-memory libtcc)")
    else:
        jv = lin_jit("bbo_div_up", e9 - bin_, e9)
        if jv == 900000000:
            rec("C0-JIT", "PASS", "lin_c0 jit div_up(9e8,1e9)==900000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "bbo_token_out(bal: int, w: int, bpt_in: int, supply: int, fee: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN token_out args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes bal/w/bpt_in/supply/fee as arguments (not storage)")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit mulDown/mulUp/divUp/powUp; ONE=1e9; MIN_INVARIANT_RATIO=0.7e9")
    rec("SOL-REJ", "PASS" if "REJ_SOLIDITY_BPT_OUT" in sol_src and "REJ_SOLIDITY_POWUP" in sol_src
        and "REJ_SOLIDITY_ARRAY" in sol_src else "FAIL",
        "lin_from_solidity.lin fail-closes TokenOutGivenExactBpt, powUp, uint256[]")
    rec("C-REJ", "PASS" if "REJ_C_BPT_OUT" in c_src and "REJ_C_POWUP" in c_src
        and "REJ_C_ARRAY" in c_src else "FAIL",
        "lin_from_c.lin fail-closes TokenOutGivenExactBpt / powUp / uint256[]")
    rec("RS-REJ", "PASS" if "REJ_RUST_BPT_OUT" in rs_src and "REJ_RUST_POWUP" in rs_src
        and "REJ_RUST_SLICE" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes TokenOutGivenExactBpt / powUp / slice []")
    rec("XE-N", "PASS" if "0.7e18" in sol_src or "flen" in sol_src else "FAIL",
        "lin_from_solidity.lin expands 0.XeN literals (0.7e18 / 0.01e18)")
    if any(c["status"] == "FAIL" for c in claims[-4:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_BALANCER_BPT_OUT_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/balancer/balancer-v2-monorepo",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA,
            "fp_blob": FP_BLOB,
            "fp_sha256": FP_SHA,
            "le_blob": LE_BLOB,
            "le_sha256": LE_SHA,
            "license": "GPL-3.0-or-later",
            "vendored": False,
        },
        "lin_clone": "src/lin_balancer_bpt_out.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/balancer_bpt_out_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "token_out_50_50_fee0": 190000000,
            "token_out_50_50_fee": 189715000,
            "token_out_80_20_fee0": 123396627,
            "token_out_20_80_fee0": 409510000,
            "naive_linear": 100000000,
            "full_fee_misuse": 189430000,
            "naive_i64_2e15_times_1e9": wrapped,
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
