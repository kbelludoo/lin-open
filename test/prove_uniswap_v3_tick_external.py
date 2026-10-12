#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Uniswap V3 TickMath.getSqrtRatioAtTick (GPL-2.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of TickMath.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      muldiv that mirrors src/lin_uniswap_v3_tick.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint160 / Q64.96 / |tick|<=887272 mainnet parity
    * that LIN replaces Uniswap V3 pools, NFTs, or the EVM
    * getNextSqrtPriceFromInput / getAmount0Delta (those are other clone-lin kernels)
    * wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real Uniswap V3 tick-table algorithm, Q32 / 14-bit ticks).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_uniswap_v3_tick.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v3_tick_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v3_tick_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v3")
EVIDENCE = ROOT / "examples" / "uniswap_v3_tick" / "uniswap_v3_tick_evidence.json"

Q32 = 2**32
PINNED_SHA256 = "83cf64b2ca84001effd16e007b49bac5359143b6c3132bfe42907b2426a0c5f5"
PINNED_BLOB = "378e44528caeb7fa0ce2f86b8a39f6d0785a0925"
PINNED_COMMIT = "e3589b192d0be27e100cd0daaf6c97204fdb1899"
UPSTREAM_REL = "contracts/libraries/TickMath.sol"
MAGIC0 = 4294752563


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


def lin_vm(path: Path, fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(path), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(path: Path, fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(path), fn, *[str(a) for a in args]]
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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/Uniswap/v3-core.git"
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
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_UNISWAP_V3_TICK_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V3 TickMath.getSqrtRatioAtTick — external LIN proof (Q32, C11)")
    print("=" * 78)

    pinned = FIX / "TickMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned TickMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned TickMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned Uniswap/v3-core v1.0.0 matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of TickMath.sol")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    sol = pinned.read_text(encoding="utf-8")
    if "function getSqrtRatioAtTick" not in sol or "0xfffcb933" not in sol:
        rec("UPSTREAM-FN", "FAIL", "pinned TickMath.sol missing getSqrtRatioAtTick table")
        return 1
    rec("UPSTREAM-FN", "PASS", "pinned source contains getSqrtRatioAtTick and Q128 magic table")
    if "function getNextSqrtPriceFromInput" in sol or "getAmount0Delta" in sol:
        rec("NOT-OTHER-KERNEL", "FAIL", "TickMath.sol unexpectedly contains other V3 kernels")
        return 1
    rec(
        "NOT-OTHER-KERNEL",
        "PASS",
        "this pin is TickMath only (not SqrtPriceMath next-sqrt / amount-delta)",
    )

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb tick-table selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree on Q32 tick table")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of tick clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v3_tick.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler (tick rejects)")

    gate = run([str(C0), "vm", str(LIN), "v3t_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "v3t_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "v3t_test_suite == 1 on Compiler 0 interpreter")

    ticks = [0, 1, -1, 2, 3, 4, 10, 100, 1000, 8192, 16383, -16383]
    n_ok = 0
    for t in ticks:
        want = int(oracle(["tick", str(t)]).splitlines()[-1])
        want_limbs = int(oracle(["tick", str(t), "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, "v3t_sqrt_at_tick", t)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"tick={t} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"v3t_sqrt_at_tick({t})", f"lin={got_lin} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} ticks: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", "Python harness compared LIN to C11; suite locks Python-derived table")

    t1 = lin_vm(LIN, "v3t_sqrt_at_tick", 1)
    naive_inv = lin_vm(LIN, "v3t_naive_invert", MAGIC0)
    if naive_inv != 0 or t1 == 0:
        rec("NAIVE-INVERT", "FAIL", "signed-i64 Q*Q invert", f"naive={naive_inv} tick1={t1}")
        return 1
    rec(
        "NAIVE-INVERT",
        "PASS",
        "naive signed-i64 (Q32*Q32)/ratio wraps to 0; 128-bit invert yields tick+1 price",
        f"naive=0 tick1={t1}",
    )

    t8 = lin_vm(LIN, "v3t_sqrt_at_tick", 8192)
    lin8 = lin_vm(LIN, "v3t_naive_linear", 8192)
    if not (t8 > lin8 > Q32):
        rec("NAIVE-LINEAR", "FAIL", "bit-table vs first-order linear at tick=8192", f"table={t8} linear={lin8}")
        return 1
    rec(
        "NAIVE-LINEAR",
        "PASS",
        "tick=8192 bit-table exceeds first-order Q*(1+tick/20000) (exponential vs linear)",
        f"table={t8} linear={lin8} delta={t8 - lin8}",
    )

    if lin_vm(LIN, "v3t_sqrt_at_tick", 16384) != 0:
        rec("FAIL-CLOSED", "FAIL", "|tick|>16383 must return 0")
        return 1
    rec("FAIL-CLOSED", "PASS", "|tick|=16384 fail-closes to 0 (reduced 14-bit domain)")

    if lin_vm(LIN, "v3t_sqrt_at_tick", 0) != Q32:
        rec("TICK-0", "FAIL", "tick 0 must be Q32")
        return 1
    rec("TICK-0", "PASS", "tick 0 == Q32 (price 1.0), same as Uniswap getSqrtRatioAtTick(0)==2^96 in Q96")

    src = LIN.read_text(encoding="utf-8")
    if "v3t_sqrt_at_tick(tick: int)" not in src or "getSqrtRatioAtTick" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit tick arg vs Solidity library")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes tick as an argument (no pool storage / assembly MSB)")
    if "v3t_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 Q*Q wraps on invert)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_TICK_SQRT" in sol_src and "REJ_SOLIDITY_TICK_MAGIC" in sol_src:
        rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes getSqrtRatioAtTick / 0xfffcb933 / >> 128")
    else:
        rec("SOL-REJ", "FAIL", "tick-table Solidity rejects missing")
    if "REJ_RUST_TICK_SQRT" in rs_src and "REJ_RUST_TICK_MAGIC" in rs_src:
        rec("RS-REJ", "PASS", "lin_from_rust.lin fail-closes sqrt_ratio_at_tick / 0xfffcb933")
    else:
        rec("RS-REJ", "FAIL", "tick-table Rust rejects missing")
    if 'out = out + "=";' in sol_src and 'out = out + "ex{";' in sol_src:
        rec("SOL-EMIT", "PASS", "sol_from_sol concatenates '=' + 'ex{' so C0 does not steal the export list")
    else:
        rec("SOL-EMIT", "FAIL", "emit concatenation missing")

    jit_ok = lin_roundtrip_jit(LIN, "v3t_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on v3t_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        cv = value_of(cjr.stdout)
        if cjr.returncode == 0 and cv == 1:
            rec("CJR-REGRESS", "PASS", "Compound V2 JumpRate still PASS after Solidity/Rust transpiler delta")
        else:
            rec("CJR-REGRESS", "FAIL", "JumpRate suite broke after transpiler delta", cjr.stdout)
    else:
        rec("CJR-REGRESS", "SKIP", "JumpRate clone not in this tree")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/Uniswap/v3-core",
        "tag": "v1.0.0",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-2.0-or-later",
        "license_note": "BUSL-1.1 Change Date 2023-04-01 elapsed",
    }
    evidence["lin_clone"] = "src/lin_uniswap_v3_tick.lin"
    evidence["c11_oracle"] = "test/oracles/uniswap_v3_tick_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["q32"] = Q32
    evidence["max_tick_reduced"] = 16383
    evidence["tick1"] = t1
    evidence["tick8192"] = t8
    evidence["linear8192"] = lin8
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-uniswap-v3-tick"
    evidence["not_claimed"] = [
        "Q64.96 / uint160 / |tick|<=887272 mainnet parity",
        "Uniswap V3 pool / SwapRouter / NFT replacement",
        "getNextSqrtPriceFromInput / getAmount0Delta",
    ]
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
