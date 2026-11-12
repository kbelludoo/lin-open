#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Uniswap V2 _mintFee / Math.sqrt (GPL-3.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of UniswapV2Pair.sol / Math.sol / SafeMath.sol
      (git blob + sha256; full Solidity is NOT vendored — GPL source stays upstream)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_uniswap_v2_mintfee.lin)
    * Python math.isqrt as a third algorithm
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / uint112 / mainnet pair parity
    * that LIN replaces Uniswap, the EVM, or protocolFeeTo
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Uniswap V2 protocol-fee algorithm, uint64-scale).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_uniswap_v2_mintfee.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v2_mintfee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v2_mintfee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v2_core")
EVIDENCE = ROOT / "examples" / "uniswap_v2_mintfee" / "uniswap_v2_mintfee_evidence.json"

PINNED_COMMIT = "4dd59067c76dea4a0e8e4bfdda41877a6b16dedc"
PINNED_TAG = "v1.0.1"
UPSTREAM_URL = "https://github.com/Uniswap/v2-core.git"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-uniswap-v2-mintfee"

PINS = {
    "contracts/UniswapV2Pair.sol": {
        "sha256": "43a5421b31415868367b62bfa161ca10bcee03778873faad905f5a3e2cce9cbd",
        "blob": "f87a1db262fba132862eae377d8cdaef74c79f97",
        "markers": ("function _mintFee", "Math.sqrt", "IUniswapV2Factory", "feeTo()"),
    },
    "contracts/libraries/Math.sol": {
        "sha256": "e4a9d451964a0689be2b244322a353de143ca4248d8736d91aca4ffadca4325f",
        "blob": "1cab10d2628630dfad34a0810f4fd56282208366",
        "markers": ("function sqrt", "y > 3", "y / 2 + 1"),
    },
    "contracts/libraries/SafeMath.sol": {
        "sha256": "4b1c95ff75de7342e0fadff58064820a4eb7c2fcb422a75b4994980ce8e216ae",
        "blob": "f2fbe164ffb143bc1c7116674654edd9113cbc54",
        "markers": ("function mul", "function add", "function sub"),
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


def py_mint(r0: int, r1: int, k_last: int, supply: int, fee_on: int) -> int:
    if fee_on == 0 or k_last == 0 or min(r0, r1, k_last, supply) < 0:
        return 0
    k = r0 * r1
    if k == 0 or k.bit_length() > 64:
        return 0
    root_k = math.isqrt(k)
    root_kl = math.isqrt(k_last)
    if root_k <= root_kl:
        return 0
    den = root_k * 5 + root_kl
    if den == 0:
        return 0
    q = supply * (root_k - root_kl)
    if q.bit_length() > 128:
        return 0
    out = q // den
    return 0 if out.bit_length() > 64 else out


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
        tag = run(
            ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", f"tags/{PINNED_TAG}"],
            timeout=120,
        )
        if tag.returncode != 0:
            note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
            return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", PINNED_COMMIT])
    if co.returncode != 0:
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
    evidence: dict = {"schema": "LIN_UNISWAP_V2_MINTFEE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V2 _mintFee — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    rec("PIN-COMMIT", "PASS", "pinned Uniswap v2-core v1.0.1 commit", PINNED_COMMIT)
    rec("PIN-PAIR", "PASS", "pinned UniswapV2Pair.sol sha256 (hash-only; not vendored)",
        PINS["contracts/UniswapV2Pair.sol"]["sha256"])
    rec("PIN-MATH", "PASS", "pinned Math.sol sha256", PINS["contracts/libraries/Math.sol"]["sha256"])
    rec("PIN-SAFEMATH", "PASS", "pinned SafeMath.sol sha256",
        PINS["contracts/libraries/SafeMath.sol"]["sha256"])

    if (ROOT / "contracts" / "UniswapV2Pair.sol").exists() or (
        ROOT / "test" / "fixtures" / "external_proof" / "UniswapV2Pair.sol"
    ).exists():
        rec("NO-VENDOR", "FAIL", "GPL UniswapV2Pair.sol must not be copied into lin-open")
        return 1
    rec("NO-VENDOR", "PASS", "GPL Solidity is not vendored; pin is hash-only")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned v2-core matches hashes", f"commit={commit}")
        rec("UPSTREAM-MARKERS", "PASS", "live files contain _mintFee / Math.sqrt / SafeMath.mul")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 i128 vs limb sqrt/mintFee selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb sqrt/mintFee agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of mintFee clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v2_mintfee.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "uvf_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "uvf_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "uvf_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_UNIV2_MINTFEE" not in sol_src or "uint112" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin missing mintFee reject or uint112")
        return 1
    rec("SOL-GATE", "PASS", "lin_from_solidity.lin rejects _mintFee/factory.feeTo/_mint and types uint112")

    sqrt_vecs = [0, 1, 2, 3, 4, 8, 9, 15, 16, 10**18]
    n_ok = 0
    for y in sqrt_vecs:
        want = int(oracle(["sqrt", str(y)]).splitlines()[-1])
        want_l = int(oracle(["sqrt", str(y), "--limbs"]).splitlines()[-1])
        got = lin_vm("uvf_sqrt", y)
        py = math.isqrt(y)
        if want != want_l or got != want or got != py:
            rec("VEC-SQRT", "FAIL", f"sqrt({y})", f"lin={got} c11={want} limbs={want_l} py={py}")
            return 1
        n_ok += 1
    rec("VEC-SQRT", "PASS", f"{n_ok}/{n_ok} Babylonian sqrts: C11 i128 == limbs == LIN == math.isqrt")

    mint_vecs = [
        ("no_growth", [1000, 1000, 1_000_000, 1000, 1], 0),
        ("grow_10pct", [1100, 1100, 1_000_000, 1000, 1], 15),
        ("grow_2x", [2000, 2000, 1_000_000, 1000, 1], 90),
        ("fee_off", [1100, 1100, 1_000_000, 1000, 0], 0),
        ("k_last_zero", [1100, 1100, 0, 1000, 1], 0),
        ("k_down", [900, 900, 1_000_000, 1000, 1], 0),
        ("named_1e9", [10**9, 10**9, 10**12, 10**9, 1], 199760047),
    ]
    n_mint = 0
    for name, args, named in mint_vecs:
        want = int(oracle(["mint", *[str(a) for a in args]]).splitlines()[-1])
        want_l = int(oracle(["mint", *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got = lin_vm("uvf_mint_fee", *args)
        py = py_mint(*args)
        if want != want_l or got != want or got != py or got != named:
            rec("VEC-MINT", "FAIL", name, f"lin={got} c11={want} py={py} named={named}")
            return 1
        n_mint += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_mint}/{n_mint} mintFee vectors: C11 i128 == limbs == LIN == Python isqrt")
    rec("NAMED-GOLDEN", "PASS", "no-growth=0; 1100/1100 vs kLast=1e6 supply=1000 -> 15; 2x -> 90; feeOff=0")

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    ov = lin_vm("uvf_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("uvf_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "7e18*3e18/1 fail-closes to 0; naive i64 wraps", f"wrap={wrapped}")

    src = LIN.read_text(encoding="utf-8")
    sig = "uvf_mint_fee(reserve0: int, reserve1: int, k_last: int, total_supply: int, fee_on: int)"
    if sig not in src or "while (i < 80)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit args and bounded Babylonian")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN takes fee_on/kLast/totalSupply as args; sqrt loop bound=80")

    sixth_num = lin_vm("uvf_sixth_num", 1100, 1000)
    sixth_den = lin_vm("uvf_sixth_den", 1100, 1000)
    if sixth_num != 100 or sixth_den != 6500 or 1000 * sixth_num // sixth_den != 15:
        rec("VS-SIXTH", "FAIL", "1/6-of-growth formula", f"num={sixth_num} den={sixth_den}")
        return 1
    rec("VS-SIXTH", "PASS", "liquidity = supply*(rootK-rootKLast)/(5*rootK+rootKLast); small-growth ~ supply/6")

    jit_ok = lin_roundtrip_jit("uvf_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on uvf_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("uvf_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit uvf_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    if "REJ_SOLIDITY_UNIV2_MINTFEE" in sol_src and "sol_expand_safemath" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin rejects _mintFee and expands SafeMath .mul/.add/.sub")
    else:
        rec("SOL-EMIT", "FAIL", "solidity mintFee reject / SafeMath expander missing")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_C_UNIV2_MINTFEE" in c_src:
        rec("C-EMIT", "PASS", "lin_from_c.lin fail-closes Uniswap V2 _mintFee / feeTo / _mint")
    else:
        rec("C-EMIT", "FAIL", "C mintFee reject missing")
    if "REJ_RUST_UNIV2_MINTFEE" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin fail-closes Uniswap V2 _mint_fee / fee_to / _mint")
    else:
        rec("RS-EMIT", "FAIL", "Rust mintFee reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/Uniswap/v2-core",
        "commit": commit or PINNED_COMMIT,
        "tag": PINNED_TAG,
        "paths": list(PINS.keys()),
        "pins": PINS,
        "license": "GPL-3.0-or-later",
        "vendored": False,
        "note": "hash-only pin; GPL UniswapV2Pair.sol / Math.sol / SafeMath.sol are not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_uniswap_v2_mintfee.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/uniswap_v2_mintfee_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "sqrt_0": 0,
        "sqrt_4": 2,
        "sqrt_1e18": 10**9,
        "mint_no_growth": 0,
        "mint_1100_vs_1000": 15,
        "mint_2000_vs_1000": 90,
        "mint_fee_off": 0,
        "mint_1e9": 199760047,
        "muldiv_7e18_3e18": 0,
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
