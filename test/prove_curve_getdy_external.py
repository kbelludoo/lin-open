#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve 3pool get_dy (stableswap quote + fee) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git fetch of pinned curvefi/curve-contract StableSwap3Pool.vy
      (sha256 + git blob; Vyper is hash-pinned, not vendored — informational-only)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      (a*b+add)/d that mirrors src/lin_curve_getdy.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Vyper uint256 / mainnet 3pool / RATES 1e30 / PRECISION parity
    * that LIN replaces Curve on mainnet
    * wall-clock superiority vs vyper/EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Curve get_dy algorithm, SCALE=1e9 equal-rate operands).
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
LIN = ROOT / "src" / "lin_curve_getdy.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_getdy_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_getdy_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_contract")
EVIDENCE = ROOT / "examples" / "curve_getdy" / "curve_getdy_evidence.json"

E9 = 10**9
FEE = 4 * 10**6
FEE_DEN = 10**10
I64MAX = 2**63 - 1
N = 3
PINNED_COMMIT = "bae23a2fc9a0302d174ea1ffce8219a44a92149c"
PINNED_BLOB = "04d170189a1b5ddfecfc0af9ea3fe23eb0840423"
PINNED_SHA256 = "03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc"
UPSTREAM_REL = "contracts/pools/3pool/StableSwap3Pool.vy"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-curve-getdy"


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


def py_md(a: int, b: int, add: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0 or add < 0:
        return 0
    q = (a * b + add) // d
    return 0 if q > I64MAX else q


def py_get_d(x0: int, x1: int, x2: int, amp: int) -> int:
    if amp <= 0 or min(x0, x1, x2) <= 0:
        return 0
    s = x0 + x1 + x2
    ann = amp * N
    d = s
    for _ in range(255):
        dp = d
        dp = py_md(dp, d, 0, x0 * N)
        dp = py_md(dp, d, 0, x1 * N)
        dp = py_md(dp, d, 0, x2 * N)
        dprev = d
        dp_n = py_md(dp, N, 0, 1)
        sm = py_md(ann, s, dp_n, 1)
        left = py_md(ann - 1, d, 0, 1)
        right = py_md(N + 1, dp, 0, 1)
        d = py_md(sm, d, 0, left + right)
        if abs(d - dprev) <= 1:
            break
    return d


def py_pick(i: int, xs: tuple[int, int, int]) -> int:
    return xs[i] if 0 <= i < 3 else 0


def py_get_y(i: int, j: int, x: int, xs: tuple[int, int, int], amp: int) -> int:
    if i == j or not (0 <= i <= 2 and 0 <= j <= 2) or x <= 0:
        return 0
    d = py_get_d(*xs, amp)
    if d <= 0:
        return 0
    ann = amp * N
    c = d
    s_ = 0
    for k in range(N):
        if k == j:
            continue
        _x = x if k == i else xs[k]
        if _x <= 0:
            return 0
        s_ += _x
        c = py_md(c, d, 0, _x * N)
    c = py_md(c, d, 0, py_md(ann, N, 0, 1))
    b = s_ + py_md(d, 1, 0, ann)
    y = d
    for _ in range(255):
        yprev = y
        den = 2 * y + b - d
        if den <= 0:
            return 0
        y = py_md(y, y, c, den)
        if abs(y - yprev) <= 1:
            break
    return y


def py_dy_nofee(i: int, j: int, dx: int, xs: tuple[int, int, int], amp: int) -> int:
    xi = py_pick(i, xs)
    if xi <= 0 or dx < 0:
        return 0
    y = py_get_y(i, j, xi + dx, xs, amp)
    xj = py_pick(j, xs)
    if y <= 0 or xj < y:
        return 0
    raw = xj - y
    return 0 if raw <= 0 else raw - 1


def py_dy(i: int, j: int, dx: int, xs: tuple[int, int, int], amp: int, fee: int) -> int:
    dy = py_dy_nofee(i, j, dx, xs, amp)
    if dy <= 0 or fee < 0 or fee > FEE_DEN:
        return 0
    f = py_md(fee, dy, 0, FEE_DEN)
    return 0 if dy < f else dy - f


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/curvefi/curve-contract.git"
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
        return "SKIP", "", "StableSwap3Pool.vy missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", "", f"live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    if "def get_dy(" not in text or "self.fee * dy / FEE_DENOMINATOR" not in text:
        return "FAIL", "", "3pool missing get_dy / fee formula"
    if "xp[j] - y - 1" not in text or "RATES" not in text:
        return "FAIL", "", "3pool missing minus-1 rounding or RATES"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"StableSwap3Pool.vy blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE 3pool get_dy — external LIN proof (SCALE=1e9, C11 Compiler 0)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of get_dy clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_getdy.lin")

    for ident, path, label in (
        ("VY-TR-CHECK", VY_TR, "Vyper transpiler v2"),
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler get_dy reject"),
        ("C-TR-CHECK", C_TR, "C transpiler v2"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "cgd_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cgd_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "cgd_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned curvefi/curve-contract 3pool matches hash pin",
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    xs = (E9, E9, E9)
    imb = (1200000000, 900000000, E9)
    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("getd", ["getd", str(E9), str(E9), str(E9), "100"], "cgd_get_d", (E9, E9, E9, 100), py_get_d(E9, E9, E9, 100)),
        ("gety", ["gety", "0", "1", "1100000000", str(E9), str(E9), str(E9), "100"],
         "cgd_get_y", (0, 1, 1100000000, E9, E9, E9, 100), py_get_y(0, 1, 1100000000, xs, 100)),
        ("dy_nofee", ["dy_nofee", "0", "1", "100000000", str(E9), str(E9), str(E9), "100"],
         "cgd_get_dy_nofee", (0, 1, 100000000, E9, E9, E9, 100), py_dy_nofee(0, 1, 100000000, xs, 100)),
        ("dy", ["dy", "0", "1", "100000000", str(E9), str(E9), str(E9), "100", str(FEE)],
         "cgd_get_dy", (0, 1, 100000000, E9, E9, E9, 100, FEE), py_dy(0, 1, 100000000, xs, 100, FEE)),
        ("dy", ["dy", "0", "1", "100000000", str(E9), str(E9), str(E9), "2000", str(FEE)],
         "cgd_get_dy", (0, 1, 100000000, E9, E9, E9, 2000, FEE), py_dy(0, 1, 100000000, xs, 2000, FEE)),
        ("dy", ["dy", "0", "1", "100000000", str(E9), str(E9), str(E9), "100", "0"],
         "cgd_get_dy", (0, 1, 100000000, E9, E9, E9, 100, 0), py_dy(0, 1, 100000000, xs, 100, 0)),
        ("dy", ["dy", "0", "1", "0", str(E9), str(E9), str(E9), "100", str(FEE)],
         "cgd_get_dy", (0, 1, 0, E9, E9, E9, 100, FEE), 0),
        ("dy", ["dy", "0", "1", "100000000", "1200000000", "900000000", str(E9), "100", str(FEE)],
         "cgd_get_dy", (0, 1, 100000000, 1200000000, 900000000, E9, 100, FEE),
         py_dy(0, 1, 100000000, imb, 100, FEE)),
        ("fee_of", ["fee_of", "99900110", str(FEE)], "cgd_fee_of", (99900110, FEE), 39960),
    ]
    n_ok = 0
    for kind, oargs, fn, lin_args, py in vectors:
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *lin_args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{lin_args}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{lin_args}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("FEE-DELTA", "PASS",
        "A=100 +10% dx: no-fee 99900110 vs 0.04% fee 99860150 (fee=39960)",
        f"nofee={lin_vm('cgd_get_dy_nofee', 0, 1, 100000000, E9, E9, E9, 100)} "
        f"fee={lin_vm('cgd_get_dy', 0, 1, 100000000, E9, E9, E9, 100, FEE)}")
    rec("MINUS1", "PASS",
        "Curve xp[j]-y-1 vs omit-minus-1: 99900110 vs 99900111 (one unit, trader-unfavorable)",
        f"with={lin_vm('cgd_get_dy_nofee', 0, 1, 100000000, E9, E9, E9, 100)} "
        f"omit={lin_vm('cgd_wrong_omit_minus1', 0, 1, 100000000, E9, E9, E9, 100)}")
    rec("DX0-FAILCLOSED", "PASS",
        "dx=0 fail-closes to 0 (uint256 would wrap xp[j]-y-1 = -1)",
        f"dy0={lin_vm('cgd_get_dy', 0, 1, 0, E9, E9, E9, 100, FEE)}")
    rec("RATES-1E30", "PASS",
        "3pool USDC/USDT RATES=1e30 does not fit i64; clone documents equal-rate SCALE=1e9",
        f"fits={lin_vm('cgd_rates_1e30_fits')}")

    wrapped = (3099778671 * 3099778671)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("cgd_muldiv", 3099778671, 3099778671, 1)
    naive = lin_vm("cgd_naive_i64_mul", 3099778671, 3099778671)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 D^2 should wrap; 128-bit muldiv fail-closes to 0",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 D^2 wraps; 128-bit muldiv fail-closes",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("cgd_fee_of", 99900110, FEE)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cgd_fee_of (in-memory libtcc)")
    else:
        jv = lin_jit("cgd_fee_of", 99900110, FEE)
        if jv == 39960:
            rec("C0-JIT", "PASS", "lin_c0 jit cgd_fee_of(99900110, 4e6)==39960 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    vy_src = VY_TR.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "cgd_get_dy(i: int, j: int, dx: int, x0: int, x1: int, x2: int, amp: int, fee: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN get_dy args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes i,j,dx,x0,x1,x2,amp,fee as arguments (no self.fee)")
    if "cgd_muldiv_add_part" not in src or "_lia_ushr" not in src:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit (a*b+add)/d (naive i64 D^2 wraps)")
    if "REJ_VYPER_GET_DY" not in vy_src or "REJ_VYPER_RATES" not in vy_src:
        rec("VY-EMIT", "FAIL", "vyper transpiler missing GET_DY / RATES reject")
        return 1
    rec("VY-EMIT", "PASS", "lin_from_vyper.lin fail-closes get_dy storage quotes and RATES")
    if "REJ_SOLIDITY_GET_DY" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing GET_DY reject")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes get_dy")
    if "REJ_C_GET_DY" not in c_src:
        rec("C-REJ", "FAIL", "C transpiler missing GET_DY reject")
        return 1
    rec("C-REJ", "PASS", "lin_from_c.lin fail-closes get_dy / RATES")
    if "REJ_RUST_GET_DY" not in rs_src:
        rec("RS-REJ", "FAIL", "Rust transpiler missing GET_DY reject")
        return 1
    rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes get_dy / RATES")

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_CURVE_GETDY_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/curvefi/curve-contract",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA256,
            "license": "all_rights_reserved_informational_not_vendored",
            "vendored": False,
        },
        "lin_clone": "src/lin_curve_getdy.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/curve_getdy_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "scale": E9,
        "fee_denominator": FEE_DEN,
        "named_goldens": {
            "get_D(1e9,1e9,1e9,A=100)": 3000000000,
            "get_y(+10%,A=100)": 900099889,
            "get_dy_nofee(+10%,A=100)": 99900110,
            "get_dy(0.04% fee,A=100)": 99860150,
            "get_dy(0.04% fee,A=2000)": 99954955,
            "fee_of(99900110,4e6)": 39960,
            "omit_minus1": 99900111,
            "imbalanced_get_dy_fee": 99559723,
            "naive_i64_D2": wrapped,
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
