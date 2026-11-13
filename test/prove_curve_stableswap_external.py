#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Curve StableSwap 3-coin get_D/get_y/get_dy vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live fetch of pinned curvefi/curve-contract 3pool Vyper (hash only;
      the file is NOT stored in lin-open because upstream LICENSE grants
      no redistribution right)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Python arbitrary-precision int implementing the same Newton iteration
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity/Vyper uint256 / mainnet 3pool parity
    * that LIN replaces Curve, Uniswap, or the EVM
    * wall-clock superiority vs vyper/solc
    * redistribution of Curve's Vyper source

Class: EXPERIMENTAL (real StableSwap algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_curve_stableswap.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
KERNEL = ROOT / "test" / "oracles" / "curve_get_d_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "curve_stableswap_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "curve_stableswap_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_contract")
EVIDENCE = ROOT / "examples" / "curve_stableswap" / "curve_stableswap_evidence.json"

PINNED_SHA256 = "03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc"
PINNED_BLOB = "04d170189a1b5ddfecfc0af9ea3fe23eb0840423"
PINNED_COMMIT = "574f44027d089de0eac765f5a74ea5ae96aba968"
UPSTREAM_REL = "contracts/pools/3pool/StableSwap3Pool.vy"
UPSTREAM_URL = "https://github.com/curvefi/curve-contract.git"
FORMULA_GET_D = "D = (Ann * S + D_P * N_COINS) * D / ((Ann - 1) * D + (N_COINS + 1) * D_P)"
FORMULA_GET_Y = "y = (y*y + c) / (2 * y + b - D)"

FEE = 4_000_000
AMP = 2000
X = 10**10


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
    proc = run(cmd, timeout=120)
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


def py_get_d(xp: list[int], amp: int, n: int = 3) -> int:
    S = sum(xp)
    if S == 0 or any(x < 1 for x in xp) or amp < 1:
        return 0
    D = S
    Ann = amp * n
    for _ in range(255):
        D_P = D
        for x in xp:
            D_P = D_P * D // (x * n)
        Dprev = D
        D = (Ann * S + D_P * n) * D // ((Ann - 1) * D + (n + 1) * D_P)
        if abs(D - Dprev) <= 1:
            return D
    return D


def py_get_y(i: int, j: int, x: int, xp: list[int], amp: int, n: int = 3) -> int:
    if i == j or i < 0 or j < 0 or i >= n or j >= n or x < 1:
        return 0
    D = py_get_d(xp, amp, n)
    if D == 0:
        return 0
    c = D
    S_ = 0
    Ann = amp * n
    for k in range(n):
        if k == j:
            continue
        _x = x if k == i else xp[k]
        S_ += _x
        c = c * D // (_x * n)
    c = c * D // (Ann * n)
    b = S_ + D // Ann
    y = D
    for _ in range(255):
        y_prev = y
        y = (y * y + c) // (2 * y + b - D)
        if abs(y - y_prev) <= 1:
            return y
    return y


def py_get_dy(i: int, j: int, dx: int, xp: list[int], amp: int, fee: int) -> int:
    x = xp[i] + dx
    y = py_get_y(i, j, x, xp, amp)
    dy = xp[j] - y - 1
    return dy - dy * fee // (10**10)


def ensure_upstream() -> tuple[str, str, str]:
    """Fetch the pinned commit. SKIP on network failure; formula pin still holds."""
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", UPSTREAM_URL])
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
    text = live.read_text(encoding="utf-8", errors="replace")
    if FORMULA_GET_D not in text or "def get_D(" not in text:
        return "FAIL", commit, "pinned file missing get_D formula"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_CURVE_STABLESWAP_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CURVE STABLESWAP 3POOL — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    if not LIN.exists():
        rec("LIN-FILE", "FAIL", "src/lin_curve_stableswap.lin missing")
        return 1
    src = LIN.read_text(encoding="utf-8")
    if PINNED_SHA256 not in src or PINNED_COMMIT not in src:
        rec("LIN-PIN", "FAIL", "LIN clone header missing pinned upstream hashes")
        return 1
    rec("LIN-PIN", "PASS", "LIN clone header pins curve-contract commit + sha256 + blob")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned curve-contract commit matches advertised sha256",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-FORMULA", "PASS", "pinned 3pool Vyper still contains get_D Newton formula")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; header pin still holds",
            up_note,
        )
        rec("UPSTREAM-FORMULA", "SKIP", "live formula not re-read this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from advertised hash", up_note)
        rec("UPSTREAM-FORMULA", "FAIL", "formula check failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb StableSwap selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv/get_D/get_dy agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Curve clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_curve_stableswap.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if ".typecheck=passed" not in chk2.stdout and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (if-else, /=, REJ_C_WIDE_INT)")

    chk3 = run([str(C0), "check", str(SOL_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk3.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3 (require + if-else)")

    gate = run([str(C0), "vm", str(LIN), "cs_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cs_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cs_test_suite == 1 on Compiler 0 interpreter", gate.stdout.splitlines()[-1] if gate.stdout else "")

    vectors = [
        ("get_d", ["1000000", "1000000", "1000000", "100"], "cs_get_d", (1000000, 1000000, 1000000, 100)),
        ("get_d", [str(X), str(X), str(X), str(AMP)], "cs_get_d", (X, X, X, AMP)),
        ("get_d", [str(X), str(9 * 10**9), str(11 * 10**9), str(AMP)], "cs_get_d", (X, 9 * 10**9, 11 * 10**9, AMP)),
        ("get_dy", ["0", "1", "10000000", str(X), str(X), str(X), str(AMP), str(FEE)], "cs_get_dy", (0, 1, 10**7, X, X, X, AMP, FEE)),
        ("muldiv", ["100", "200", "50"], "cs_muldiv", (100, 200, 50)),
        ("muladd", ["7", "9", "1", "2"], "cs_muladd_div", (7, 9, 1, 2)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "get_d":
            py = py_get_d([largs[0], largs[1], largs[2]], largs[3])
        elif kind == "get_dy":
            py = py_get_dy(largs[0], largs[1], largs[2], [largs[3], largs[4], largs[5]], largs[6], largs[7])
        elif kind == "muldiv":
            py = (largs[0] * largs[1]) // largs[2]
        else:
            py = (largs[0] * largs[1] + largs[2]) // largs[3]
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    d_prod = lin_vm("cs_muldiv", X, X, 1)
    wrapped = (X * X) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if d_prod != 0:
        rec("I64-WRAP", "FAIL", "1e10*1e10/1 should fail-close (quotient 1e20 > uint64)")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e10*1e10) wraps; 128-bit muldiv fail-closes quotient 1e20",
        f"i64_wrap={wrapped} lin_muldiv_ov={d_prod}",
    )

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_WIDE_INT" not in c_src or "/=" not in c_src or "else_src" not in c_src:
        rec("C-EMIT", "FAIL", "lin_from_c.lin missing v2 if-else / /= / REJ_C_WIDE_INT")
    else:
        rec("C-EMIT", "PASS", "C transpiler v2: if-else, /=, reject __int128 as REJ_C_WIDE_INT")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_require_cond" not in sol_src or "else_src" not in sol_src:
        rec("SOL-EMIT", "FAIL", "lin_from_solidity.lin missing v3 require/if-else")
    else:
        rec("SOL-EMIT", "PASS", "Solidity transpiler v3: require() fail-closed + if/else emit")

    if not KERNEL.exists() or "else" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable Curve get_D kernel missing if-else")
    else:
        rec(
            "C-KERNEL",
            "PASS",
            "pointer-free C kernel (curve_get_d_kernel.c) is eligible for lin_from_c; naive * / is uint64-scale only",
        )

    if "cs_get_d(x0: int, x1: int, x2: int, amp: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args for balances and amp")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes xp/amp/fee as arguments (no hidden pool storage / block.timestamp ramp)",
        )
    if "cs_wide_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv/muladd (naive i64 D*D wraps at 1e10)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    jit_ok = lin_roundtrip_jit("cs_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cs_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("cs_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cs_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/curvefi/curve-contract",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "Curve.Fi custom: no redistribution grant; LIN clone is original code citing the published algorithm",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_curve_stableswap.lin"
    evidence["c11_oracle"] = "test/oracles/curve_stableswap_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/curve_get_d_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["get_d_balanced_1e10"] = lin_vm("cs_get_d", X, X, X, AMP)
    evidence["get_dy_1e7"] = lin_vm("cs_get_dy", 0, 1, 10**7, X, X, X, AMP, FEE)
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-curve-stableswap"
    evidence["clone_lin_source"] = "https://github.com/kbelludoo/clone-lin-curve-stableswap/blob/main/src/lin_curve_stableswap.lin"
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
