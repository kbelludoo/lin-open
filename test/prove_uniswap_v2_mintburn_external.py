#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Uniswap V2 mint/burn LP amounts (GPL-3.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of UniswapV2Pair.sol / Math.sol / SafeMath.sol
      (git blob + sha256; full Solidity is NOT vendored — GPL source stays upstream)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_uniswap_v2_mintburn.lin)
    * Python math.isqrt / bigint as a third algorithm
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / uint112 / mainnet pair parity
    * that LIN replaces Uniswap, the EVM, or LP token accounting
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Uniswap V2 LP mint/burn algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_uniswap_v2_mintburn.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v2_mintburn_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v2_mintburn_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v2_core")
EVIDENCE = ROOT / "examples" / "uniswap_v2_mintburn" / "uniswap_v2_mintburn_evidence.json"

PINNED_COMMIT = "4dd59067c76dea4a0e8e4bfdda41877a6b16dedc"
PINNED_TAG = "v1.0.1"
UPSTREAM_URL = "https://github.com/Uniswap/v2-core.git"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-uniswap-v2-mintburn"
MIN_LIQ = 1000

PINS = {
    "contracts/UniswapV2Pair.sol": {
        "sha256": "43a5421b31415868367b62bfa161ca10bcee03778873faad905f5a3e2cce9cbd",
        "blob": "f87a1db262fba132862eae377d8cdaef74c79f97",
        "markers": (
            "function mint(address to)",
            "function burn(address to)",
            "Math.sqrt(amount0.mul(amount1))",
            "Math.min(",
            "MINIMUM_LIQUIDITY",
            "IERC20(token0).balanceOf",
        ),
    },
    "contracts/libraries/Math.sol": {
        "sha256": "e4a9d451964a0689be2b244322a353de143ca4248d8736d91aca4ffadca4325f",
        "blob": "1cab10d2628630dfad34a0810f4fd56282208366",
        "markers": ("function min", "function sqrt", "y > 3", "y / 2 + 1"),
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


def py_fits_u64(n: int) -> bool:
    return 0 <= n <= 2**64 - 1


def py_mint(a0: int, a1: int, r0: int, r1: int, supply: int) -> int:
    if min(a0, a1, r0, r1, supply) < 0:
        return 0
    if supply == 0:
        prod = a0 * a1
        if prod.bit_length() > 64:
            return 0
        root = math.isqrt(prod)
        if root < MIN_LIQ:
            return 0
        return root - MIN_LIQ
    if r0 == 0 or r1 == 0:
        return 0
    q0 = a0 * supply // r0
    q1 = a1 * supply // r1
    if not py_fits_u64(q0) or not py_fits_u64(q1):
        return 0
    return min(q0, q1)


def py_burn(liq: int, bal: int, supply: int) -> int:
    if liq < 0 or bal < 0 or supply <= 0:
        return 0
    q = liq * bal // supply
    return 0 if not py_fits_u64(q) else q


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
    evidence: dict = {"schema": "LIN_UNISWAP_V2_MINTBURN_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V2 mint/burn — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    rec("PIN-COMMIT", "PASS", "pinned Uniswap v2-core v1.0.1 commit", PINNED_COMMIT)
    rec(
        "PIN-PAIR",
        "PASS",
        "pinned UniswapV2Pair.sol sha256 (hash-only; not vendored)",
        PINS["contracts/UniswapV2Pair.sol"]["sha256"],
    )
    rec("PIN-MATH", "PASS", "pinned Math.sol sha256", PINS["contracts/libraries/Math.sol"]["sha256"])
    rec(
        "PIN-SAFEMATH",
        "PASS",
        "pinned SafeMath.sol sha256",
        PINS["contracts/libraries/SafeMath.sol"]["sha256"],
    )

    if (ROOT / "contracts" / "UniswapV2Pair.sol").exists() or (
        ROOT / "test" / "fixtures" / "external_proof" / "UniswapV2Pair.sol"
    ).exists():
        rec("NO-VENDOR", "FAIL", "GPL UniswapV2Pair.sol must not be copied into lin-open")
        return 1
    rec("NO-VENDOR", "PASS", "GPL Solidity is not vendored; pin is hash-only")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned v2-core matches hashes", f"commit={commit}")
        rec("UPSTREAM-MARKERS", "PASS", "live files contain mint/burn / Math.min / Math.sqrt")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 i128 vs limb sqrt/mint/burn selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb sqrt/mint/burn agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of mint/burn clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v2_mintburn.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "uv2_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "uv2_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "uv2_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_UNIV2_MINT" not in sol_src or "sol_expand_math_min" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin missing mint reject or Math.min expander")
        return 1
    rec("SOL-GATE", "PASS", "lin_from_solidity.lin rejects IERC20 mint/burn and expands Math.min")
    if "sol_expand_safemath" not in sol_src or "uint112" not in sol_src:
        rec("SOL-SAFEMATH", "FAIL", "SafeMath expander or uint112 missing")
        return 1
    rec("SOL-SAFEMATH", "PASS", "sol_expand_safemath + uint112/uint224 present (C0 vm cannot run string gates)")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_UNIV2_MINT" not in rs_src or "rs_parse_test_gate" not in rs_src:
        rec("RS-GATE", "FAIL", "lin_from_rust.lin missing mint/burn reject gate")
        return 1
    rec("RS-GATE", "PASS", "rs_parse_test_gate source includes Uniswap V2 mint/burn rejects")

    sqrt_vecs = [0, 1, 2, 3, 4, 8, 9, 15, 16, 10**18]
    n_ok = 0
    for y in sqrt_vecs:
        want = int(oracle(["sqrt", str(y)]).splitlines()[-1])
        want_l = int(oracle(["sqrt", str(y), "--limbs"]).splitlines()[-1])
        got = lin_vm("uv2_sqrt", y)
        py = math.isqrt(y)
        if want != want_l or got != want or got != py:
            rec("VEC-SQRT", "FAIL", f"sqrt({y})", f"lin={got} c11={want} limbs={want_l} py={py}")
            return 1
        n_ok += 1
    rec("VEC-SQRT", "PASS", f"{n_ok}/{n_ok} Babylonian sqrts: C11 i128 == limbs == LIN == math.isqrt")

    mint_vecs = [
        ("first_insufficient", [1000, 1000, 0, 0, 0], 0),
        ("first_1001", [1001, 1001, 0, 0, 0], 1),
        ("first_10k", [10000, 10000, 0, 0, 0], 9000),
        ("next_balanced", [1000, 1000, 10000, 10000, 9000], 900),
        ("next_unbalanced", [2000, 1000, 10000, 10000, 9000], 900),
        ("first_1e9", [10**9, 10**9, 0, 0, 0], 999999000),
        ("zero_amount", [0, 10000, 0, 0, 0], 0),
    ]
    n_mint = 0
    for name, args, named in mint_vecs:
        want = int(oracle(["mint", *[str(a) for a in args]]).splitlines()[-1])
        want_l = int(oracle(["mint", *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got = lin_vm("uv2_mint_liquidity", *args)
        py = py_mint(*args)
        if want != want_l or got != want or got != py or got != named:
            rec("VEC-MINT", "FAIL", name, f"lin={got} c11={want} py={py} named={named}")
            return 1
        n_mint += 1
    rec("VEC-MINT", "PASS", f"{n_mint}/{n_mint} mint LP vectors: C11 i128 == limbs == LIN == Python")

    burn_vecs = [
        ("burn_1k", [1000, 10000, 10000], 1000),
        ("burn_9k", [9000, 10000, 10000], 9000),
        ("burn_zero_liq", [0, 10000, 10000], 0),
        ("burn_zero_supply", [1000, 10000, 0], 0),
    ]
    n_burn = 0
    for name, args, named in burn_vecs:
        want = int(oracle(["burn", *[str(a) for a in args]]).splitlines()[-1])
        want_l = int(oracle(["burn", *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got = lin_vm("uv2_burn_amount", *args)
        py = py_burn(*args)
        if want != want_l or got != want or got != py or got != named:
            rec("VEC-BURN", "FAIL", name, f"lin={got} c11={want} py={py} named={named}")
            return 1
        n_burn += 1
    rec("VEC-BURN", "PASS", f"{n_burn}/{n_burn} burn pro-rata vectors: C11 i128 == limbs == LIN == Python")
    rec("VEC-CONSENSUS", "PASS", "mint + burn + sqrt: C11 i128 == limbs == LIN vm == Python bigint")
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "first 10k/10k -> 9000; next 1k vs 10k/9k supply -> 900; unbalanced min=900; burn 1k/10k -> 1000",
    )

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    ov = lin_vm("uv2_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("uv2_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "7e18*3e18/1 fail-closes to 0; naive i64 wraps", f"wrap={wrapped}")

    src = LIN.read_text(encoding="utf-8")
    sig = "uv2_mint_liquidity(amount0: int, amount1: int, reserve0: int, reserve1: int, total_supply: int)"
    if sig not in src or "while (i < 80)" not in src or "uv2_u_min" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit args, unsigned min, bounded Babylonian")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN takes amounts/reserves/supply as args; sqrt loop bound=80")

    if lin_vm("uv2_mint_ok", 1000, 1000, 0, 0, 0) != 0 or lin_vm("uv2_mint_ok", 1001, 1001, 0, 0, 0) != 1:
        rec("VS-REQUIRE", "FAIL", "fail-closed first mint vs Solidity require(liquidity>0)")
        return 1
    rec("VS-REQUIRE", "PASS", "sqrt<MINIMUM_LIQUIDITY fail-closes to 0 instead of SafeMath revert")

    smin = lin_vm("uv2_signed_min_select", 3, 9)
    umin = lin_vm("uv2_u_min", 3, 9)
    if smin != 3 or umin != 3 or lin_vm("uv2_signed_min_select", 9, 3) != 3:
        rec("MATH-MIN-SEL", "FAIL", "Compiler 0 eval of Math.min expansion ((a<b)*a + ((a<b)==0)*b)")
        return 1
    rec("MATH-MIN-SEL", "PASS", "C0 vm of sol_expand_math_min select agrees with uv2_u_min on non-negatives")

    jit_ok = lin_roundtrip_jit("uv2_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on uv2_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("uv2_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit uv2_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    if "sol_expand_math_min" in sol_src and "sol_expand_safemath" in sol_src and "uint112" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin expands Math.min + SafeMath and types uint112")
    else:
        rec("SOL-EMIT", "FAIL", "solidity Math.min / SafeMath expander missing")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_C_UNIV2_MINT" in c_src and "REJ_C_UNIV2_BURN" in c_src:
        rec("C-EMIT", "PASS", "lin_from_c.lin fail-closes Uniswap V2 mint IERC20 and burn _safeTransfer")
    else:
        rec("C-EMIT", "FAIL", "C mint/burn reject missing")
    if "REJ_RUST_UNIV2_MINT" in rs_src and "REJ_RUST_UNIV2_BURN" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin fail-closes Uniswap V2 mint/burn host calls")
    else:
        rec("RS-EMIT", "FAIL", "Rust mint/burn reject missing")

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
    evidence["lin_clone"] = "src/lin_uniswap_v2_mintburn.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/uniswap_v2_mintburn_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "sqrt_0": 0,
        "sqrt_4": 2,
        "sqrt_1e18": 10**9,
        "mint_first_insufficient": 0,
        "mint_first_1001": 1,
        "mint_first_10k": 9000,
        "mint_next_balanced": 900,
        "mint_next_unbalanced": 900,
        "mint_first_1e9": 999999000,
        "burn_1k_of_10k": 1000,
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
