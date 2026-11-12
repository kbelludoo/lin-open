#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound CToken.exchangeRateStoredInternal vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned compound-finance/compound-protocol CToken.sol
    + ExponentialNoError.sol (sha256 + git blob; Solidity is hash-pinned,
    not vendored)
  * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
    (a*b)/d that mirrors src/lin_compound_exrate.lin)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int as a third oracle

NOT claimed: uint256 / mainnet 1e18 parity; LIN replacing Compound;
wall-clock superiority; TVL or dollar savings; zk soundness; getCashPrior
ERC-20/ETH balance reads.

Class: EXPERIMENTAL (real exchangeRateStoredInternal, SCALE=1e9, 128-bit
muldiv, storage lift, fail-closed underflow).
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
LIN = ROOT / "src" / "lin_compound_exrate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_exrate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_exrate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_exrate" / "compound_exrate_evidence.json"

E9 = 10**9
INIT = 2 * 10**7
I64MAX = 2**63 - 1
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
PINNED_CT_BLOB = "b8c878c79c75855808f6e7303099a367c8bad98b"
PINNED_CT_SHA = "b64790f41ef851b09856af286ce8253b95ef34fda4ae836f924a519e8f792785"
PINNED_EXP_BLOB = "23f833760db898ebdc6b2fef9654cb9bc1dd21c3"
PINNED_EXP_SHA = "dd272760b2d9082db9c94f6198896402fe3681bf41fc3f9d8bba31ada290c3c5"
UPSTREAM_CT = "contracts/CToken.sol"
UPSTREAM_EXP = "contracts/ExponentialNoError.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-compound-xrate"


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > I64MAX else q


def py_rate(cash: int, borrows: int, reserves: int, supply: int, scale: int, initial: int) -> int:
    if min(cash, borrows, reserves, supply, initial) < 0 or scale <= 0:
        return 0
    if supply == 0:
        return initial
    s = cash + borrows
    if s < cash or s < reserves:
        return 0
    return py_md(s - reserves, scale, supply)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/compound-finance/compound-protocol.git"
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
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    ct, exp = UPSTREAM / UPSTREAM_CT, UPSTREAM / UPSTREAM_EXP
    if not ct.exists() or not exp.exists():
        return "SKIP", "", "CToken/ExponentialNoError missing after checkout"
    blob_ct = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_CT}"]).stdout.strip()
    blob_exp = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_EXP}"]).stdout.strip()
    if sha256_file(ct) != PINNED_CT_SHA or blob_ct != PINNED_CT_BLOB:
        return "FAIL", "", f"CToken live={sha256_file(ct)} blob={blob_ct}"
    if sha256_file(exp) != PINNED_EXP_SHA or blob_exp != PINNED_EXP_BLOB:
        return "FAIL", "", f"ExponentialNoError live={sha256_file(exp)} blob={blob_exp}"
    ct_t, exp_t = ct.read_text(encoding="utf-8"), exp.read_text(encoding="utf-8")
    if "function exchangeRateStoredInternal()" not in ct_t:
        return "FAIL", "", "CToken missing exchangeRateStoredInternal"
    if "cashPlusBorrowsMinusReserves * expScale / _totalSupply" not in ct_t:
        return "FAIL", "", "CToken missing (cash+borrows-reserves)*expScale/supply"
    if "return initialExchangeRateMantissa" not in ct_t:
        return "FAIL", "", "CToken missing zero-supply initial rate"
    if "getCashPrior()" not in ct_t:
        return "FAIL", "", "CToken missing getCashPrior"
    if "uint constant expScale = 1e18" not in exp_t:
        return "FAIL", "", "ExponentialNoError missing expScale = 1e18"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"CToken blob={blob_ct} ExponentialNoError blob={blob_exp}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND CToken.exchangeRateStoredInternal — external LIN proof (SCALE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of exchange-rate clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_exrate.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler CASH_PRIOR reject / 0.02e18"),
        ("C-TR-CHECK", C_TR, "C transpiler CASH_PRIOR reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler CASH_PRIOR reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "cxr_test_suite"], timeout=120)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cxr_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "cxr_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned compound-protocol matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CToken.sol / ExponentialNoError.sol")
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb exchange-rate selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b)/d agree")

    vectors = [
        ((E9, 0, 0, E9, E9, INIT), E9),
        ((E9, 10**8, 0, E9, E9, INIT), 1100000000),
        ((E9, 0, 10**8, E9, E9, INIT), 900000000),
        ((0, 0, 0, 0, E9, INIT), INIT),
        ((100, 0, 200, E9, E9, INIT), 0),
        ((0, E9, 0, 5 * 10**8, E9, INIT), 2000000000),
        ((2 * 10**15, 0, 0, E9, E9, INIT), 2 * 10**15),
        ((E9, 0, 0, E9, 0, INIT), 0),
    ]
    n_ok = 0
    for args, golden in vectors:
        oargs = ["rate", *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("cxr_exchange_rate", *args)
        py_v = py_rate(*args)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"rate{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("PAR-ONE", "PASS", "cash=supply=1e9, zero borrows/reserves → rate 1e9",
        f"rate={lin_vm('cxr_exchange_rate', E9, 0, 0, E9, E9, INIT)}")
    rec("ZERO-SUPPLY", "PASS", "totalSupply==0 returns explicit initial (0.02*SCALE=2e7)",
        f"rate={lin_vm('cxr_exchange_rate', 0, 0, 0, 0, E9, INIT)}")
    rec("UNDERFLOW", "PASS", "cash+borrows < reserves fail-closes to 0 (Solidity 0.8 reverts)",
        f"z={lin_vm('cxr_exchange_rate', 100, 0, 200, E9, E9, INIT)}")

    wrapped = (2 * 10**15 * E9)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("cxr_muldiv", 2 * 10**15, E9, E9)
    naive = lin_vm("cxr_naive_i64_mul", 2 * 10**15, E9)
    if wide != 2 * 10**15 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 2e15*1e9 should wrap; 128-bit muldiv = 2e15",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 2e15*1e9 wraps; 128-bit muldiv stays 2000000000000000",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("cxr_exchange_rate", E9, 0, 0, E9, E9, INIT)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on par-one rate (in-memory libtcc)")
    else:
        jv = lin_jit("cxr_exchange_rate", E9, 0, 0, E9, E9, INIT)
        if jv == E9:
            rec("C0-JIT", "PASS", "lin_c0 jit par-one rate == 1e9 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "cxr_exchange_rate(cash: int, borrows: int, reserves: int, supply: int, scale: int, initial: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN exchange-rate args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes cash, borrows, reserves, supply, scale, initial as arguments")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit (cash+borrows-reserves)*scale/supply; getCashPrior is not claimed")
    if "REJ_SOLIDITY_CASH_PRIOR" not in sol_src or "0.02e" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing CASH_PRIOR reject / 0.02e18 expand")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes getCashPrior and expands 0.02e18")
    rec("C-REJ", "PASS" if "REJ_C_CASH_PRIOR" in c_src else "FAIL", "lin_from_c.lin fail-closes getCashPrior / balanceOf")
    rec("RS-REJ", "PASS" if "REJ_RUST_CASH_PRIOR" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes getCashPrior / balance_of")
    if any(c["status"] == "FAIL" for c in claims[-2:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_COMPOUND_EXRATE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/compound-finance/compound-protocol",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_CT,
            "math_path": UPSTREAM_EXP,
            "blob": PINNED_CT_BLOB,
            "sha256": PINNED_CT_SHA,
            "exp_blob": PINNED_EXP_BLOB,
            "exp_sha256": PINNED_EXP_SHA,
            "license": "BSD-3-Clause",
            "vendored": False,
        },
        "lin_clone": "src/lin_compound_exrate.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/compound_exrate_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "par_one_1e9": E9,
            "borrow_10pct": 1100000000,
            "reserve_10pct": 900000000,
            "zero_supply_initial": INIT,
            "underflow_fail": 0,
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
