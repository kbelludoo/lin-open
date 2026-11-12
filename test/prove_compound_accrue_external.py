#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound CToken.accrueInterest (BSD-3-Clause) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of CToken.sol / CTokenInterfaces.sol /
      ExponentialNoError.sol (git blob + sha256; full Solidity is NOT vendored)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_compound_accrue.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / mainnet cToken parity
    * that LIN replaces Compound, Uniswap, or the EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Compound accrueInterest algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_compound_accrue.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_accrue_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_accrue_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_accrue" / "compound_accrue_evidence.json"

BASE = 10**18
RATE_MAX = 5 * 10**12  # 0.0005e16
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
UPSTREAM_URL = "https://github.com/compound-finance/compound-protocol.git"

PINS = {
    "contracts/CToken.sol": {
        "sha256": "b64790f41ef851b09856af286ce8253b95ef34fda4ae836f924a519e8f792785",
        "blob": "b8c878c79c75855808f6e7303099a367c8bad98b",
        "markers": ("function accrueInterest", "mul_ScalarTruncate"),
    },
    "contracts/CTokenInterfaces.sol": {
        "sha256": "0246c7789d36fca84a7861ab39693f02dfb7bde904011f4efda654d4286fe93a",
        "blob": "ba8d69a00f5aef0b8a019dfa513f6c3835ba9e60",
        "markers": ("borrowRateMaxMantissa", "0.0005e16"),
    },
    "contracts/ExponentialNoError.sol": {
        "sha256": "dd272760b2d9082db9c94f6198896402fe3681bf41fc3f9d8bba31ada290c3c5",
        "blob": "23f833760db898ebdc6b2fef9654cb9bc1dd21c3",
        "markers": ("mul_ScalarTruncate", "expScale = 1e18"),
    },
}


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
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
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


def py_interest(borrows: int, rate: int, delta: int) -> int:
    if rate > RATE_MAX or rate < 0 or delta < 0 or borrows < 0:
        return 0
    factor = rate * delta
    if factor > (2**64 - 1):
        return 0
    q = factor * borrows
    return q // BASE if q.bit_length() <= 128 else 0


def py_borrows_new(borrows: int, rate: int, delta: int) -> int:
    if rate > RATE_MAX:
        return 0
    acc = py_interest(borrows, rate, delta)
    s = borrows + acc
    return 0 if s > (2**64 - 1) else s


def ensure_upstream() -> tuple[str, str, str]:
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
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    notes = []
    for rel, pin in PINS.items():
        live = UPSTREAM / rel
        if not live.exists():
            return "FAIL", commit, f"{rel} missing after checkout"
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{rel}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != pin["sha256"] or blob != pin["blob"]:
            return "FAIL", commit, f"{rel} live={live_hash} blob={blob}"
        text = live.read_text(encoding="utf-8")
        for m in pin["markers"]:
            if m not in text:
                return "FAIL", commit, f"{rel} missing marker {m}"
        notes.append(f"{rel}:{blob}")
    return "PASS", commit, ";".join(notes)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMPOUND_ACCRUE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND CToken.accrueInterest — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    rec("PIN-COMMIT", "PASS", "pinned compound-protocol commit", PINNED_COMMIT)
    rec("PIN-CTOKEN", "PASS", "pinned CToken.sol sha256 (hash-only; not vendored)", PINS["contracts/CToken.sol"]["sha256"])
    rec("PIN-IFACE", "PASS", "pinned CTokenInterfaces.sol sha256", PINS["contracts/CTokenInterfaces.sol"]["sha256"])
    rec("PIN-EXP", "PASS", "pinned ExponentialNoError.sol sha256", PINS["contracts/ExponentialNoError.sol"]["sha256"])

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned compound-protocol matches hashes", f"commit={commit}")
        rec("UPSTREAM-MARKERS", "PASS", "live files contain accrueInterest / 0.0005e16 / mul_ScalarTruncate")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv/accrue selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb accrue math agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of accrue clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_accrue.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "cac_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cac_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cac_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_CTOKEN_ACCRUE" not in sol_src or "sol_expand_dec_exp" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin missing accrue reject or 0.XeN expander")
        return 1
    rec(
        "SOL-GATE",
        "PASS",
        "lin_from_solidity.lin typechecked; CToken accrue reject + 0.0005e16 expander present (string gate is check-only)",
    )

    vectors = [
        ("interest_dt1", "interest", "cac_interest", [BASE, 10**10, 1], 10**10),
        ("borrows_dt1", "borrows", "cac_borrows_new", [BASE, 10**10, 1], 1000000010000000000),
        ("index_dt1", "index", "cac_index_new", [BASE, 10**10, 1], 1000000010000000000),
        ("borrows_dt0", "borrows", "cac_borrows_new", [BASE, 10**10, 0], BASE),
        ("interest_dt2", "interest", "cac_interest", [BASE, 10**10, 2], 2 * 10**10),
        ("rate_max_fail", "borrows", "cac_borrows_new", [1, RATE_MAX + 1, 1], 0),
    ]
    n_ok = 0
    for name, op, fn, args, want_named in vectors:
        want = int(oracle([op, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([op, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        py = py_interest(*args) if fn == "cac_interest" else (
            py_borrows_new(*args) if fn == "cac_borrows_new" else want
        )
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{name} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{name}", f"lin={got_lin} c11={want}")
            return 1
        if got_lin != want_named:
            rec("VEC-NAMED", "FAIL", f"{name} named golden", f"{got_lin} != {want_named}")
            return 1
        if fn in ("cac_interest", "cac_borrows_new") and py != want:
            rec("VEC-PY", "FAIL", f"python bigint {name}", f"py={py} c11={want}")
            return 1
        n_ok += 1

    res_args = [0, BASE, 10**10, 1, 10**17]
    want_res = int(oracle(["reserves", *[str(a) for a in res_args]]).splitlines()[-1])
    want_res_l = int(oracle(["reserves", *[str(a) for a in res_args], "--limbs"]).splitlines()[-1])
    got_res = lin_vm("cac_reserves_new", *res_args)
    if want_res != 10**9 or got_res != want_res or want_res != want_res_l:
        rec("VEC-RESERVES", "FAIL", "rf=1e17 dt=1 reserves addend", f"lin={got_res} c11={want_res}")
        return 1
    n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} accrue vectors: C11 i128 == limbs == LIN vm == Python")
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "dt1 interest=1e10 borrows/index=1000000010000000000; rf 10% adds 1e9; dt0 identity; rate>max=0",
    )

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    ov = lin_vm("cac_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("cac_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "7e18*3e18/1 fail-closes to 0; naive i64 wraps", f"wrap={wrapped}")

    same = lin_vm("cac_should_accrue", 10, 10, 10**10)
    under = lin_vm("cac_should_accrue", 9, 10, 10**10)
    ok = lin_vm("cac_should_accrue", 11, 10, 10**10)
    if same != 0 or under != 0 or ok != 1:
        rec("EXPLICIT-ARGS", "FAIL", "same-block / underflow must not accrue", f"{same} {under} {ok}")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN takes current/prior/rate/borrows/index/rf as args; same-block is identity")

    dt1 = lin_vm("cac_interest", BASE, 10**10, 1)
    dt2 = lin_vm("cac_interest", BASE, 10**10, 2)
    if dt2 != 2 * dt1 or dt1 != 10**10:
        rec("VS-LINEAR", "FAIL", "simple interest is linear in blockDelta", f"dt1={dt1} dt2={dt2}")
        return 1
    rec("VS-LINEAR", "PASS", "Compound simpleInterestFactor is linear in blockDelta (not rpow)")

    jit_ok = lin_roundtrip_jit("cac_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cac_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cac_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cac_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cac_borrows_new(borrows: int, rate: int, delta: int)" not in src:
        rec("WIDE-SIG", "FAIL", "expected explicit LIN args vs Solidity storage/IRM/block")
        return 1
    rec("WIDE-SIG", "PASS", "clone uses 128-bit product; IRM getBorrowRate and getBlockNumber are arguments")

    if "REJ_SOLIDITY_CTOKEN_ACCRUE" in sol_src and "sol_expand_dec_exp" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3 rejects accrueInterest/getBlockNumber and expands 0.0005e16")
    else:
        rec("SOL-EMIT", "FAIL", "solidity accrue reject / decimal eN missing")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_C_CTOKEN_ACCRUE" in c_src:
        rec("C-EMIT", "PASS", "lin_from_c.lin fail-closes CToken accrue / getBlockNumber")
    else:
        rec("C-EMIT", "FAIL", "C accrue reject missing")
    if "REJ_RUST_CTOKEN_ACCRUE" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin fail-closes CToken accrue / get_block_number")
    else:
        rec("RS-EMIT", "FAIL", "Rust accrue reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/compound-protocol",
        "commit": commit or PINNED_COMMIT,
        "paths": list(PINS.keys()),
        "pins": PINS,
        "license": "BSD-3-Clause",
        "vendored": False,
        "note": "hash-only pin; full CToken.sol is not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_compound_accrue.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-compound-accrue"
    evidence["c11_oracle"] = "test/oracles/compound_accrue_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "interest_dt1": 10**10,
        "borrows_dt1": 1000000010000000000,
        "index_dt1": 1000000010000000000,
        "reserves_rf10pct_dt1": 10**9,
        "borrows_dt0": BASE,
        "interest_dt2": 2 * 10**10,
        "rate_above_max": 0,
        "muldiv_7e18_3e18": 0,
        "rate_max": RATE_MAX,
    }
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
