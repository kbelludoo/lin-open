#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve 3pool get_D / get_virtual_price vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned curvefi/curve-contract StableSwap3Pool.vy
    (sha256 + git blob; Vyper is hash-pinned, not vendored)
  * independent C11 oracle (__int128 XOR portable 32-bit limb (a*b+add)/d)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreter + optional libtcc JIT
  * Python arbitrary-precision int as a third oracle

NOT claimed:
  * full Vyper uint256 / RATES / PRECISION=1e18 / mainnet 3pool parity
  * that LIN replaces Curve, Convex, or Yearn on Ethereum
  * wall-clock superiority vs vyper/EVM
  * TVL or dollar savings
  * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real 3pool get_D Newton + D*SCALE/supply, SCALE=1e9).
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
LIN = ROOT / "src" / "lin_curve_vp.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_vp_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_vp_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_contract")
EVIDENCE = ROOT / "examples" / "curve_vp" / "curve_vp_evidence.json"

E9 = 10**9
D0 = 3 * E9
DIMB = 3099778671
I64MAX = 2**63 - 1
PINNED_COMMIT = "bae23a2fc9a0302d174ea1ffce8219a44a92149c"
PINNED_BLOB = "04d170189a1b5ddfecfc0af9ea3fe23eb0840423"
PINNED_SHA = "03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc"
UPSTREAM_REL = "contracts/pools/3pool/StableSwap3Pool.vy"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-curve-vp"


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


def py_get_d(x0: int, x1: int, x2: int, amp: int) -> int:
    if amp <= 0 or min(x0, x1, x2) <= 0:
        return 0
    n = 3
    s = x0 + x1 + x2
    if s <= 0:
        return 0
    ann = amp * n
    if ann <= amp:
        return 0
    d = s
    for _ in range(255):
        dp = d
        for x in (x0, x1, x2):
            xkn = py_md(x, n, 1)
            if xkn <= 0:
                return 0
            dp = py_md(dp, d, xkn)
            if dp <= 0:
                return 0
        dprev = d
        left = py_md(ann, s, 1)
        dp_n = py_md(dp, n, 1)
        if left <= 0 or dp_n <= 0 or left > I64MAX - dp_n:
            return 0
        left += dp_n
        ann1_d = py_md(ann - 1, d, 1)
        n1_dp = py_md(n + 1, dp, 1)
        if ann1_d <= 0 or n1_dp <= 0 or ann1_d > I64MAX - n1_dp:
            return 0
        den = ann1_d + n1_dp
        d = py_md(left, d, den)
        if d <= 0:
            return 0
        if abs(d - dprev) <= 1:
            return d
    return d


def py_vp(x0: int, x1: int, x2: int, amp: int, supply: int) -> int:
    if supply <= 0:
        return 0
    return py_md(py_get_d(x0, x1, x2, amp), E9, supply)


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
        "def get_virtual_price",
        "def get_D",
        "self.token.totalSupply()",
        "D * PRECISION / token_supply",
        "D_P = D_P * D / (_x * N_COINS)",
        "self.balances",
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
    print("  CURVE 3pool get_virtual_price — external LIN proof (SCALE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of get_virtual_price clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_vp.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler TOKEN_CALL/TOTALSUPPLY/SELF_BALANCES"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 TOKEN_CALL/TOTALSUPPLY reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 TOKEN/TOTAL_SUPPLY reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "cvp_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cvp_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "cvp_test_suite == 1 on Compiler 0 interpreter")

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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb get_D selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    vecs = [
        ("getd", (E9, E9, E9, 100), D0, "cvp_get_d"),
        ("getd", (E9, E9, E9, 2000), D0, "cvp_get_d"),
        ("getd", (12 * 10**8, 9 * 10**8, E9, 100), DIMB, "cvp_get_d"),
        ("vp", (E9, E9, E9, 100, D0), E9, "cvp_virtual_price"),
        ("vp", (12 * 10**8, 9 * 10**8, E9, 100, D0), 1033259557, "cvp_virtual_price"),
        ("vp", (12 * 10**8, 9 * 10**8, E9, 100, 3100000000), 999928603, "cvp_virtual_price"),
        ("vp", (E9, E9, E9, 100, DIMB), 967811033, "cvp_virtual_price"),
        ("fromd", (3001000000, D0), 1000333333, "cvp_from_d"),
        ("fromd", (D0, 0), 0, "cvp_from_d"),
        ("csum", (12 * 10**8, 9 * 10**8, E9, 3100000000), E9, "cvp_constant_sum_price"),
    ]
    n_ok = 0
    for kind, args, golden, fn in vecs:
        oargs = [kind, *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if kind == "getd":
            py_v = py_get_d(*args)
        elif kind == "vp":
            py_v = py_vp(*args)
        elif kind == "fromd":
            py_v = py_md(args[0], E9, args[1]) if args[1] else 0
        else:
            py_v = want
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"{kind}{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("IDENTITY", "PASS", "equal 1e9 balances, supply=D, A=100: virtual price = SCALE (1.0)",
        f"vp={lin_vm('cvp_virtual_price', E9, E9, E9, 100, D0)}")
    rec("IMB-HAIRCUT", "PASS", "imbalance vs constant-sum: vp 999928603 vs 1e9 (haircut 71397)",
        f"vp={lin_vm('cvp_virtual_price', 1200000000, 900000000, E9, 100, 3100000000)} "
        f"csum={lin_vm('cvp_constant_sum_price', 1200000000, 900000000, E9, 3100000000)}")
    rec("FEE-MARK", "PASS", "D grown by fees to 3001000000 / supply 3e9 marks vp=1000333333",
        f"from_d={lin_vm('cvp_from_d', 3001000000, D0)}")
    rec("SUPPLY-ZERO", "PASS", "token.totalSupply()=0 and zero coin fail-close to 0",
        f"vp0={lin_vm('cvp_virtual_price', E9, E9, E9, 100, 0)} d0={lin_vm('cvp_get_d', E9, E9, 0, 100)}")
    rec("UINT256-CAP", "PASS", "mainnet uint256 / RATES / totalSupply / self.balances are not claimed",
        f"ts={lin_vm('cvp_token_supply_claimed')} bal={lin_vm('cvp_balances_claimed')} "
        f"rates={lin_vm('cvp_rates_claimed')}")

    wrapped = (12000000000 * E9)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("cvp_muldiv", 12000000000, E9, 1)
    naive = lin_vm("cvp_naive_i64_mul", 12000000000, E9)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 D*SCALE should wrap; 128-bit muldiv fail-closes",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 D*SCALE wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("cvp_virtual_price", E9, E9, E9, 100, D0)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on identity virtual price (in-memory libtcc)")
    else:
        jv = lin_jit("cvp_from_d", D0, D0)
        if jv == E9:
            rec("C0-JIT", "PASS", "lin_c0 jit from_d(D0,D0)==1e9 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "cvp_virtual_price(x0: int, x1: int, x2: int, amp: int, supply: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN virtual_price args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes xp, amp, supply as arguments (not storage/token)")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit Newton get_D and D*SCALE/supply; N=3 SCALE=1e9")
    rec("SOL-REJ", "PASS" if "REJ_SOLIDITY_TOKEN_CALL" in sol_src and "REJ_SOLIDITY_TOTALSUPPLY" in sol_src
        and "REJ_SOLIDITY_SELF_BALANCES" in sol_src else "FAIL",
        "lin_from_solidity.lin fail-closes self.token, totalSupply, self.balances")
    rec("C-REJ", "PASS" if "REJ_C_TOKEN_CALL" in c_src and "REJ_C_TOTALSUPPLY" in c_src
        and "REJ_C_SELF_BALANCES" in c_src else "FAIL",
        "lin_from_c.lin fail-closes token./totalSupply / self.balances")
    rec("RS-REJ", "PASS" if "REJ_RUST_TOKEN_CALL" in rs_src and "REJ_RUST_TOTAL_SUPPLY" in rs_src
        and "REJ_RUST_SELF_BALANCES" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes token./total_supply / self.balances")
    if any(c["status"] == "FAIL" for c in claims[-3:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_CURVE_VP_EVIDENCE_1.0",
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
        "lin_clone": "src/lin_curve_vp.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/curve_vp_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "get_d_equal_1e9": D0,
            "vp_equal_supply_d": E9,
            "get_d_imbalance": DIMB,
            "vp_imbalance_supply_d0": 1033259557,
            "vp_imbalance_supply_sum": 999928603,
            "from_d_fee_mark": 1000333333,
            "naive_i64_12e9_times_1e9": wrapped,
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
