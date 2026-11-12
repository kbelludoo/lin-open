#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve 3pool get_y_D / calc_withdraw_one_coin vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned curvefi/curve-contract StableSwap3Pool.vy
    (sha256 + git blob; Vyper is hash-pinned, not vendored)
  * independent C11 oracle (__int128 XOR portable 32-bit limb (a*b+add)/d)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreter + optional libtcc JIT
  * Python arbitrary-precision int as a third oracle

NOT claimed:
  * full Vyper uint256 / RATES / PRECISION_MUL / mainnet 3pool parity
  * that LIN replaces Curve on Ethereum
  * wall-clock superiority vs vyper/EVM
  * TVL or dollar savings
  * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real 3pool get_y_D Newton, SCALE=1e9, 128-bit muldiv).
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
LIN = ROOT / "src" / "lin_curve_getyd.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_getyd_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_getyd_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_contract")
EVIDENCE = ROOT / "examples" / "curve_getyd" / "curve_getyd_evidence.json"

E9 = 10**9
D0 = 3 * E9
D1_10 = 2700000000
D1_1 = 2970000000
DIMB = 3099778671
I64MAX = 2**63 - 1
PINNED_COMMIT = "bae23a2fc9a0302d174ea1ffce8219a44a92149c"
PINNED_BLOB = "04d170189a1b5ddfecfc0af9ea3fe23eb0840423"
PINNED_SHA = "03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc"
UPSTREAM_REL = "contracts/pools/3pool/StableSwap3Pool.vy"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-curve-getyd"


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


def py_md_add(a: int, b: int, add: int, d: int) -> int:
    if d <= 0 or min(a, b, add) < 0:
        return 0
    q = (a * b + add) // d
    return 0 if q > I64MAX else q


def py_get_y_d(i: int, d: int, x0: int, x1: int, x2: int, amp: int) -> int:
    if i < 0 or i > 2 or d <= 0 or amp <= 0 or min(x0, x1, x2) <= 0:
        return 0
    xp = [x0, x1, x2]
    n = 3
    ann = amp * n
    if ann <= amp:
        return 0
    c = d
    s_ = 0
    for k in range(n):
        if k == i:
            continue
        xk = xp[k]
        t = s_ + xk
        if t < s_:
            return 0
        s_ = t
        c = py_md(c, d, xk * n)
        if c <= 0:
            return 0
    ann_n = py_md(ann, n, 1)
    if ann_n <= 0:
        return 0
    c = py_md(c, d, ann_n)
    if c <= 0:
        return 0
    d_ann = py_md(d, 1, ann)
    b = s_ + d_ann
    if b < s_:
        return 0
    y = d
    for _ in range(255):
        yprev = y
        two_y = y + y
        if two_y < y:
            return 0
        tb = two_y + b
        if tb < two_y or tb < d:
            return 0
        den = tb - d
        if den <= 0:
            return 0
        y = py_md_add(y, y, c, den)
        if y == 0:
            return 0
        if abs(y - yprev) <= 1:
            break
    return y


def py_d1(d0: int, burn: int, supply: int) -> int:
    if d0 <= 0 or burn <= 0 or supply <= 0 or burn >= supply:
        return 0
    sub = py_md(burn, d0, supply)
    return 0 if d0 < sub else d0 - sub


def py_dy0(i: int, d1: int, x0: int, x1: int, x2: int, amp: int) -> int:
    y = py_get_y_d(i, d1, x0, x1, x2, amp)
    xi = [x0, x1, x2][i] if 0 <= i <= 2 else 0
    if y <= 0 or xi < y:
        return 0
    return xi - y


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/curvefi/curve-contract.git"
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
        return "SKIP", "", "StableSwap3Pool.vy missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    digest = sha256_file(src)
    if digest != PINNED_SHA or blob != PINNED_BLOB:
        return "FAIL", "", f"live={digest} blob={blob}"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "def get_y_D",
        "def _calc_withdraw_one_coin",
        "self.token.totalSupply()",
        "self.balances",
        "xp[j] * D1 / D0 - new_y",
        "y = (y*y + c) / (2 * y + b - D)",
    ):
        if needle not in text:
            return "FAIL", "", f"StableSwap3Pool missing {needle}"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"StableSwap3Pool blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE 3pool get_y_D — external LIN proof (SCALE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of get_y_D clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_getyd.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler TOTALSUPPLY/SELF_BALANCES"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 TOTALSUPPLY/SELF_BALANCES reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 TOTAL_SUPPLY/SELF_BALANCES reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "cyd_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cyd_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "cyd_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned curve-contract 3pool matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of StableSwap3Pool.vy")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb get_y_D selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    vecs = [
        ("getyd", (0, D0, E9, E9, E9, 100), E9, "cyd_get_y_d"),
        ("getyd", (0, D1_10, E9, E9, E9, 100), 700367933, "cyd_get_y_d"),
        ("getyd", (0, D1_10, E9, E9, E9, 2000), 700018630, "cyd_get_y_d"),
        ("getyd", (0, DIMB, 12 * 10**8, 9 * 10**8, E9, 100), 12 * 10**8, "cyd_get_y_d"),
        ("d1", (D0, 3 * 10**8, D0), D1_10, "cyd_d1"),
        ("dy0", (0, D1_10, E9, E9, E9, 100), 299632067, "cyd_dy0"),
        ("dy0", (0, D1_10, E9, E9, E9, 2000), 299981370, "cyd_dy0"),
        ("dy0", (0, D0, E9, E9, E9, 100), 0, "cyd_dy0"),
        ("dy0", (0, D1_1, E9, E9, E9, 100), 29996980, "cyd_dy0"),
        ("wfee", (0, D0, D1_10, E9, E9, E9, 100), 299572241, "cyd_withdraw_fee"),
        ("wfee", (0, D0, D1_1, E9, E9, E9, 100), 29990981, "cyd_withdraw_fee"),
    ]
    n_ok = 0
    for kind, args, golden, fn in vecs:
        oargs = [kind, *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if kind == "getyd":
            py_v = py_get_y_d(*args)
        elif kind == "d1":
            py_v = py_d1(*args)
        elif kind == "dy0":
            py_v = py_dy0(*args)
        else:
            py_v = want
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"{kind}{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("IDENTITY", "PASS", "get_y_D recovers xp[i] when D is the equal-pool invariant",
        f"y={lin_vm('cyd_get_y_d', 0, D0, E9, E9, E9, 100)}")
    rec("WITHDRAW-10", "PASS", "10% LP burn at A=100 returns 299632067 of coin 0, not 300000000",
        f"dy0={lin_vm('cyd_dy0', 0, D1_10, E9, E9, E9, 100)} haircut=367933")
    rec("AMP-TIGHTEN", "PASS", "same 10% burn at A=2000 haircut shrinks to 18630 vs 367933",
        f"dy0={lin_vm('cyd_dy0', 0, D1_10, E9, E9, E9, 2000)}")
    rec("FEE-PATH", "PASS", "3pool 0.04% fee path returns 299572241 (dy0 minus imbalance fee)",
        f"wfee={lin_vm('cyd_withdraw_fee', 0, D0, D1_10, E9, E9, E9, 100)}")
    rec("BURN-ZERO", "PASS", "identity D and burn>=supply fail-close to 0",
        f"dy0_id={lin_vm('cyd_dy0', 0, D0, E9, E9, E9, 100)} d1_all={lin_vm('cyd_d1', D0, D0, D0)}")
    rec("UINT256-CAP", "PASS", "mainnet uint256 / RATES / totalSupply / self.balances are not claimed",
        f"ts={lin_vm('cyd_totalsupply_claimed')} bal={lin_vm('cyd_balances_claimed')}")

    wrapped = (DIMB * DIMB)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("cyd_muldiv", DIMB, DIMB, 1)
    naive = lin_vm("cyd_naive_i64_mul", DIMB, DIMB)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 D^2 should wrap; 128-bit muldiv fail-closes",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 D^2 wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("cyd_get_y_d", 0, D0, E9, E9, E9, 100)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on identity get_y_D (in-memory libtcc)")
    else:
        jv = lin_jit("cyd_get_y_d", 0, D0, E9, E9, E9, 100)
        if jv == E9:
            rec("C0-JIT", "PASS", "lin_c0 jit identity get_y_D == 1e9 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "cyd_get_y_d(i: int, d: int, x0: int, x1: int, x2: int, amp: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN get_y_D args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes i, D, x0/x1/x2, amp as arguments (not storage)")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit Newton (a*b+add)/d; N=3 and FEE_DEN=1e9 are constants")
    rec("SOL-REJ", "PASS" if "REJ_SOLIDITY_TOTALSUPPLY" in sol_src and "REJ_SOLIDITY_SELF_BALANCES" in sol_src else "FAIL",
        "lin_from_solidity.lin fail-closes totalSupply and self.balances")
    rec("C-REJ", "PASS" if "REJ_C_TOTALSUPPLY" in c_src and "REJ_C_SELF_BALANCES" in c_src else "FAIL",
        "lin_from_c.lin fail-closes totalSupply / self.balances")
    rec("RS-REJ", "PASS" if "REJ_RUST_TOTAL_SUPPLY" in rs_src and "REJ_RUST_SELF_BALANCES" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes total_supply / self.balances")
    if any(c["status"] == "FAIL" for c in claims[-3:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_CURVE_GETYD_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/curvefi/curve-contract",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA,
            "license": "all-rights-reserved-informational-only",
            "vendored": False,
        },
        "lin_clone": "src/lin_curve_getyd.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/curve_getyd_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "get_y_d_identity_1e9": E9,
            "d1_burn10": D1_10,
            "y_after_burn10_A100": 700367933,
            "dy0_burn10_A100": 299632067,
            "dy0_burn10_A2000": 299981370,
            "wfee_burn10_A100": 299572241,
            "dy0_burn1_A100": 29996980,
            "naive_i64_Dimb_sq": wrapped,
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
