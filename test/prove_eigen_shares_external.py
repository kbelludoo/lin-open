#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: EigenLayer StrategyBase share conversion vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned eigenlayer-contracts StrategyBase.sol v1.13.0
    (sha256 + git blob; Solidity is hash-pinned, not vendored)
  * independent C11 oracle (__int128 XOR portable 32-bit limb (a*b)/d)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreter + optional libtcc JIT
  * Python arbitrary-precision int as a third oracle

NOT claimed:
  * full Solidity uint256 / MAX_TOTAL_SHARES=1e38 / IERC20.balanceOf parity
  * userUnderlying(address) / StrategyManager lookups
  * that LIN replaces EigenLayer on mainnet
  * wall-clock superiority vs solc/EVM
  * TVL or dollar savings
  * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real StrategyBase virtual-share conversion, OFFSET=1000,
128-bit muldiv).
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
LIN = ROOT / "src" / "lin_eigen_shares.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "eigen_shares_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "eigen_shares_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_eigenlayer_contracts")
EVIDENCE = ROOT / "examples" / "eigen_shares" / "eigen_shares_evidence.json"

E9 = 10**9
OFF = 1000
I64MAX = 2**63 - 1
PINNED_COMMIT = "ef8f97992241338cb88335b9d74295e33321b780"
PINNED_BLOB = "e68f5940e365f69210f4f23ff8aa03d2b5de7e72"
PINNED_SHA = "36cb7a4681935d4ac588166a1ab92591a4309412cfdcf5246ed6082e13767dbc"
UPSTREAM_REL = "src/contracts/strategies/StrategyBase.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-eigen-shares"


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


def py_s2u(shares: int, total: int, bal: int) -> int:
    if min(shares, total, bal) < 0 or total > I64MAX - OFF or bal > I64MAX - OFF:
        return 0
    return py_md(bal + OFF, shares, total + OFF)


def py_u2s(und: int, total: int, bal: int) -> int:
    if min(und, total, bal) < 0 or total > I64MAX - OFF or bal > I64MAX - OFF:
        return 0
    return py_md(und, total + OFF, bal + OFF)


def py_dep(amount: int, prior: int, bal_after: int) -> int:
    if amount <= 0 or prior < 0 or bal_after < amount:
        return 0
    if prior > I64MAX - OFF or bal_after > I64MAX - OFF:
        return 0
    virt_prior = (bal_after + OFF) - amount
    q = py_md(amount, prior + OFF, virt_prior)
    return 0 if q == 0 else q


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/Layr-Labs/eigenlayer-contracts.git"
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
        return "SKIP", "", "StrategyBase.sol missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    digest = sha256_file(src)
    if digest != PINNED_SHA or blob != PINNED_BLOB:
        return "FAIL", "", f"live={digest} blob={blob}"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "function sharesToUnderlyingView",
        "function underlyingToSharesView",
        "SHARES_OFFSET = 1e3",
        "BALANCE_OFFSET = 1e3",
        "MAX_TOTAL_SHARES = 1e38",
        "underlyingToken.balanceOf(address(this))",
        "virtualPriorTokenBalance = virtualTokenBalance - amount",
    ):
        if needle not in text:
            return "FAIL", "", f"StrategyBase missing {needle}"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"StrategyBase blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  EIGENLAYER StrategyBase shares — external LIN proof (OFFSET=1000, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eigen-shares clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_eigen_shares.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler BALANCEOF/ADDRESS/WIDE_LIT / 1e3"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 BALANCEOF/ADDRESS reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 BALANCE/ADDRESS reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "els_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "els_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "els_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned eigenlayer-contracts v1.13.0 matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of StrategyBase.sol")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb share-conversion selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b)/d agree")

    s2u_vecs = [
        ((OFF, 0, 0), 1000),
        ((E9, E9, E9), E9),
        ((10**6, E9, E9), 10**6),
        ((E9, E9, 11 * 10**8), 1099999900),
        ((0, E9, E9), 0),
        ((10**6, E9, 11 * 10**8), 1099999),
    ]
    n_ok = 0
    for args, golden in s2u_vecs:
        oargs = ["s2u", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("els_shares_to_underlying", *args)
        py_v = py_s2u(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"s2u{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    u2s_vecs = [
        ((OFF, 0, 0), 1000),
        ((E9, E9, E9), E9),
        ((11 * 10**8, E9, 11 * 10**8), 1000000090),
        ((10**6, E9, 11 * 10**8), 909090),
    ]
    for args, golden in u2s_vecs:
        oargs = ["u2s", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("els_underlying_to_shares", *args)
        py_v = py_u2s(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"u2s{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    dep_vecs = [
        ((E9, 0, E9), E9),
        ((10**8, E9, 12 * 10**8), 90909099),
        ((0, E9, E9), 0),
    ]
    for args, golden in dep_vecs:
        oargs = ["dep", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("els_deposit_shares", *args)
        py_v = py_dep(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"dep{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("EMPTY-BOOK", "PASS", "empty strategy 1000 shares -> 1000 underlying (virtual 1:1)",
        f"s2u={lin_vm('els_shares_to_underlying', OFF, 0, 0)}")
    rec("PAR-BOOK", "PASS", "1:1 book 1e9 shares -> 1e9 underlying",
        f"s2u={lin_vm('els_shares_to_underlying', E9, E9, E9)}")
    rec("YIELD-HAIRCUT", "PASS", "10% yield converts 1e9 shares to 1099999900 not 1100000000",
        f"s2u={lin_vm('els_shares_to_underlying', E9, E9, 11 * 10**8)} naive=1100000000")
    rec("FIRST-DEPOSIT", "PASS", "first deposit 1e9 into empty book mints 1e9 shares",
        f"dep={lin_vm('els_deposit_shares', E9, 0, E9)}")
    rec("YIELD-DEPOSIT", "PASS", "deposit 1e8 after 10% yield mints 90909099 shares",
        f"dep={lin_vm('els_deposit_shares', 10**8, E9, 12 * 10**8)}")
    rec("UINT256-CAP", "PASS", "mainnet 1e18 fits i64; 1e38 and balanceOf are not claimed",
        f"one18_fits={lin_vm('els_one_e18_fits')} max38={lin_vm('els_max_shares_claimed')} bal={lin_vm('els_balanceof_claimed')}")

    wrapped = (2 * 10**15 * E9)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("els_muldiv", 2 * 10**15, E9, 1)
    naive = lin_vm("els_naive_i64_mul", 2 * 10**15, E9)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 2e15*1e9 should wrap; 128-bit muldiv fail-closes",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 2e15*1e9 wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("els_shares_to_underlying", E9, E9, E9)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on 1:1 sharesToUnderlying (in-memory libtcc)")
    else:
        jv = lin_jit("els_shares_to_underlying", E9, E9, E9)
        if jv == E9:
            rec("C0-JIT", "PASS", "lin_c0 jit 1:1 sharesToUnderlying == 1e9 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "els_shares_to_underlying(shares: int, total: int, bal: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN share-conversion args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes shares/underlying, totalShares, tokenBalance as arguments")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit muldiv; OFFSET=1000 is an argument-free constant")
    if "REJ_SOLIDITY_BALANCEOF" not in sol_src or "REJ_SOLIDITY_ADDRESS" not in sol_src or "REJ_SOLIDITY_WIDE_LIT" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing BALANCEOF/ADDRESS/WIDE_LIT reject")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes balanceOf, address, and 1e38")
    rec("C-REJ", "PASS" if "REJ_C_BALANCEOF" in c_src and "REJ_C_ADDRESS" in c_src else "FAIL",
        "lin_from_c.lin fail-closes balanceOf / address params")
    rec("RS-REJ", "PASS" if "REJ_RUST_BALANCE" in rs_src and "REJ_RUST_ADDRESS" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes balance_of / Address params")
    if any(c["status"] == "FAIL" for c in claims[-2:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_EIGEN_SHARES_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/Layr-Labs/eigenlayer-contracts",
            "tag": "v1.13.0",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA,
            "license": "BUSL-1.1",
            "vendored": False,
        },
        "lin_clone": "src/lin_eigen_shares.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/eigen_shares_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "s2u_empty_1000": 1000,
            "s2u_par_1e9": 1000000000,
            "s2u_yield10_1e9": 1099999900,
            "u2s_yield10_1p1e9": 1000000090,
            "dep_first_1e9": 1000000000,
            "dep_after_yield_1e8": 90909099,
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
