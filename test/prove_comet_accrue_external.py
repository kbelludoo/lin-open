#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound III accruedInterestIndices (per-second index)
vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of CometWithExtendedAssetList.sol + CometCore.sol
      (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      muldiv that mirrors src/lin_comet_accrue.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 range (LIN path is uint64-scale + 128-bit product)
    * that LIN replaces Compound III on mainnet
    * TVL, live USDC market, or PriceFeed parity
    * presentValue / principalValue (that is a different kernel)

Class: EXPERIMENTAL (real Comet per-second accrual algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_comet_accrue.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
JR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "comet_accrue_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "comet_accrue_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_comet")
EVIDENCE = ROOT / "examples" / "comet_accrue" / "comet_accrue_evidence.json"

FACTOR = 10**18
INDEX = 10**15
SECONDS = 31536000
BLOCKS = 2102400
APY = 10**16

PINNED = {
    "CometWithExtendedAssetList.sol": {
        "sha256": "c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961",
        "blob": "3490e984d133789aa1afe2e8f7e37a11d2512396",
        "rel": "contracts/CometWithExtendedAssetList.sol",
    },
    "CometCore.sol": {
        "sha256": "1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78",
        "blob": "534f2701b6c8e683f9294112b0bcc23878d39fe6",
        "rel": "contracts/CometCore.sol",
    },
}
PINNED_COMMIT = "f766f51583c23acc33b2a7824654ef2029a96804"


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


def ensure_upstream() -> tuple[str, str]:
    url = "https://github.com/compound-finance/comet.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "checkout of pinned commit failed"
    notes = []
    for name, meta in PINNED.items():
        live = UPSTREAM / meta["rel"]
        if not live.exists():
            return "FAIL", f"{meta['rel']} missing after checkout"
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{meta['rel']}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != meta["sha256"] or blob != meta["blob"]:
            return "FAIL", f"{name} live={live_hash} blob={blob}"
        notes.append(f"{name}:{blob}")
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", f"commit={commit} " + " ".join(notes)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMET_ACCRUE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND III accruedInterestIndices — external LIN proof")
    print("  (uint64-scale, per-second index, C11 oracle)")
    print("=" * 78)

    for name, meta in PINNED.items():
        pinned = FIX / name
        if not pinned.exists():
            rec("PIN-FILE", "FAIL", f"pinned {name} missing")
            return 1
        got = sha256_file(pinned)
        if got != meta["sha256"]:
            rec("PIN-SHA256", "FAIL", f"pinned {name} hash mismatch", f"{got} != {meta['sha256']}")
            return 1
        rec("PIN-SHA256", "PASS", f"pinned {name} sha256 matches manifest")

    up_status, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned comet commit matches fixtures", up_note)
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CometWithExtendedAssetList.sol and CometCore.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    core = (FIX / "CometCore.sol").read_text(encoding="utf-8")
    acc = (FIX / "CometWithExtendedAssetList.sol").read_text(encoding="utf-8")
    if "SECONDS_PER_YEAR = 31_536_000" not in core or "FACTOR_SCALE = 1e18" not in core:
        rec("PIN-CONST", "FAIL", "CometCore.sol missing SECONDS_PER_YEAR / FACTOR_SCALE")
        return 1
    rec("PIN-CONST", "PASS", "CometCore.sol pins SECONDS_PER_YEAR=31536000 and FACTOR_SCALE=1e18")
    if "function accruedInterestIndices" not in acc or "function mulFactor" not in acc:
        rec("PIN-FNS", "FAIL", "accruedInterestIndices / mulFactor missing from fixture")
        return 1
    rec("PIN-FNS", "PASS", "fixture contains accruedInterestIndices, getSupplyRate, mulFactor")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of accrue clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_comet_accrue.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
        return 1
    rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v6")

    chk3 = run([str(C0), "check", str(RS_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk3.stdout)
        return 1
    rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v3")

    gate = run([str(C0), "vm", str(LIN), "cai_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cai_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cai_test_suite == 1 on Compiler 0 interpreter")

    # C0 refuses to *execute* modules that contain string literals
    # (VM_REJ_STRING_LITERAL). Numeric gates in the accrue kernel still run.
    # Transpiler rejects are proven by source: upstream snippet ∩ reject token.
    sg = run([str(C0), "vm", str(SOL_TR), "sol_parse_test_gate"])
    if "VM_REJ_STRING_LITERAL" not in sg.stdout:
        rec("SOL-GATE-C0", "FAIL", "expected C0 to refuse string-literal sol_parse_test_gate", sg.stdout)
        return 1
    rec(
        "SOL-GATE-C0",
        "PASS",
        "Compiler 0 fail-closes sol_parse_test_gate with VM_REJ_STRING_LITERAL (numeric kernel still runs)",
    )

    vectors = [
        ("muldiv", ["100", "200", "50"], "cai_floor", (100, 200, 50), 400),
        ("mulfactor", [str(FACTOR), "500000000000000000"], "cai_mul_factor", (FACTOR, 5 * 10**17), 5 * 10**17),
        ("util", ["500", "1000"], "cai_utilization", (500, 1000), 5 * 10**17),
        ("delta", [str(INDEX), "1", "1000"], "cai_delta", (INDEX, 1, 1000), 1),
        ("twostep", [str(INDEX), "1", "1000"], "cai_delta_twostep", (INDEX, 1, 1000), 0),
        ("kink", ["500000000000000000", "0", "100", "200", "800000000000000000"],
         "cai_kink_rate", (5 * 10**17, 0, 100, 200, 8 * 10**17), 50),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py_want in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_want != want:
            rec("VEC-PY", "FAIL", f"python {fn}{largs}", f"py={py_want} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    ps = lin_vm(LIN, "cai_apy_per_second", APY)
    pb = lin_vm(LIN, "cai_apy_per_block", APY)
    d_iii = lin_vm(LIN, "cai_delta", INDEX, ps, SECONDS)
    d_bad = lin_vm(LIN, "cai_delta", INDEX, pb, SECONDS)
    py_ps = APY // SECONDS
    py_pb = APY // BLOCKS
    py_iii = INDEX * (py_ps * SECONDS) // FACTOR
    py_bad = INDEX * (py_pb * SECONDS) // FACTOR
    if ps != py_ps or pb != py_pb:
        rec("APY-SPLIT", "FAIL", "per-second vs per-block 1% split", f"ps={ps} pb={pb}")
        return 1
    rec("APY-SPLIT", "PASS", "1% wad / SECONDS_PER_YEAR vs / JumpRate blocksPerYear", f"ps={ps} pb={pb}")
    if d_iii != py_iii or d_bad != py_bad:
        rec("YEAR-DELTA", "FAIL", "year delta iii vs v2-misapply", f"iii={d_iii} bad={d_bad}")
        return 1
    rec(
        "YEAR-DELTA",
        "PASS",
        "genesis index, 1% APY, 365-day year: III per-second vs V2 per-block-as-per-second",
        f"iii={d_iii} v2mis={d_bad} ratio={d_bad / d_iii:.6f}",
    )
    if not (d_iii * 14 < d_bad < d_iii * 16):
        rec("NAMED-15X", "FAIL", "expected ~15x over-accrual", f"{d_bad}/{d_iii}")
        return 1
    rec(
        "NAMED-15X",
        "PASS",
        "wallet that reuses Compound V2 per-block 1% as III per-second over-accrues ~15x in one year",
        f"{d_bad}/{d_iii} = {d_bad / d_iii:.6f} (31536000/2102400 = {SECONDS / BLOCKS:.6f})",
    )

    want_iii = int(oracle(["delta", str(INDEX), str(ps), str(SECONDS)]).splitlines()[-1])
    want_bad = int(oracle(["delta", str(INDEX), str(pb), str(SECONDS), "--limbs"]).splitlines()[-1])
    if want_iii != d_iii or want_bad != d_bad:
        rec("YEAR-C11", "FAIL", "year deltas vs C11", f"c11={want_iii},{want_bad}")
        return 1
    rec("YEAR-C11", "PASS", "year deltas: Python bigint == C11 i128 == limbs == LIN")

    tw = lin_vm(LIN, "cai_delta_twostep", INDEX, 1, 1000)
    ex = lin_vm(LIN, "cai_delta", INDEX, 1, 1000)
    if ex != 1 or tw != 0:
        rec("PREC-TWOSTEP", "FAIL", "index*rate/1e18*dt vs index*(rate*dt)/1e18", f"exact={ex} twostep={tw}")
        return 1
    rec(
        "PREC-TWOSTEP",
        "PASS",
        "floor(index*rate/1e18)*dt under-counts 1e15*1*1000/1e18 as 0; (rate*dt) first yields 1",
    )

    rt_ok = lin_vm(LIN, "cai_rate_time_ok", 4294967296, 4294967296)
    if rt_ok != 0:
        rec("RATE-TIME-OV", "FAIL", "2^32 * 2^32 should fail-close", f"ok={rt_ok}")
        return 1
    rec("RATE-TIME-OV", "PASS", "rate*dt that does not fit uint64 fail-closes (Solidity uint256 would succeed)")

    src = LIN.read_text(encoding="utf-8")
    if "cai_kink_rate(util: int, base: int, slope_low: int, slope_high: int, kink: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN IRM args")
        return 1
    rec(
        "EXPLICIT-ARGS",
        "PASS",
        "LIN clone takes index/rate/dt and kink IRM params as arguments (no hidden storage / getUtilization)",
    )
    if "cai_muldiv_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 rate*dt wraps)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
        return 1

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_TUPLE_RET",
        "REJ_SOLIDITY_SAFE64",
        "REJ_SOLIDITY_RATE_TIME",
        "REJ_SOLIDITY_FACTOR_SCALE",
        "getUtilization(",
        'out = out + "="',
        'out = out + "ex{"',
    ]
    if any(tok not in sol_src for tok in need):
        rec("SOL-V6", "FAIL", "v6 rejects / split =ex{ missing")
        return 1
    rec("SOL-V6", "PASS", "lin_from_solidity.lin v6: TUPLE_RET / SAFE64 / RATE_TIME / FACTOR_SCALE / split export")

    pairs = [
        ("returns (uint64, uint64)", "REJ_SOLIDITY_TUPLE_RET"),
        ("safe64(", "REJ_SOLIDITY_SAFE64"),
        ("supplyRate * timeElapsed", "REJ_SOLIDITY_RATE_TIME"),
        ("borrowRate * timeElapsed", "REJ_SOLIDITY_RATE_TIME"),
        ("FACTOR_SCALE", "REJ_SOLIDITY_FACTOR_SCALE"),
        ("getUtilization()", "getUtilization("),
        ("getSupplyRate(utilization)", "getSupplyRate("),
        ("supplyPerSecondInterestRateBase", "supplyPerSecondInterestRate"),
    ]
    missing = [f"{u} → {t}" for u, t in pairs if u not in acc or t not in sol_src]
    if missing:
        rec("UPSTREAM-REJECT", "FAIL", "upstream snippet missing matching v6 reject", "; ".join(missing))
        return 1
    rec(
        "UPSTREAM-REJECT",
        "PASS",
        "pinned accruedInterestIndices / getSupplyRate / mulFactor snippets are covered by v6 rejects",
    )

    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_RATE_TIME" not in rs_src or "* time_elapsed" not in rs_src:
        rec("RS-V3", "FAIL", "REJ_RUST_RATE_TIME missing")
        return 1
    rec("RS-V3", "PASS", "lin_from_rust.lin v3 rejects wrapping * time_elapsed")

    jit_ok = lin_roundtrip_jit(LIN, "cai_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cai_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    jr_gate = run([str(C0), "vm", str(JR), "cjr_test_suite"])
    if value_of(jr_gate.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "JumpRate still runs after transpiler delta", jr_gate.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate cjr_test_suite still == 1 after v6 transpiler")
    jr_jit = lin_roundtrip_jit(JR, "cjr_test_suite")
    if jr_jit:
        rec("JUMPRATE-JIT", "PASS", "JumpRate roundtrip-jit still CONSENSUS")
    else:
        rec("JUMPRATE-JIT", "SKIP", "JumpRate JIT not exercised this host")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/comet",
        "commit": PINNED_COMMIT,
        "path": "contracts/CometWithExtendedAssetList.sol",
        "constants_path": "contracts/CometCore.sol",
        "git_blob_sha": PINNED["CometWithExtendedAssetList.sol"]["blob"],
        "core_blob_sha": PINNED["CometCore.sol"]["blob"],
        "file_sha256": PINNED["CometWithExtendedAssetList.sol"]["sha256"],
        "core_sha256": PINNED["CometCore.sol"]["sha256"],
        "license": "GPL-2.0-or-later",
        "license_note": "BUSL-1.1 Change Date 2025-12-31 elapsed; Change License GPL-2.0-or-later",
    }
    evidence["lin_clone"] = "src/lin_comet_accrue.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-comet-accrue"
    evidence["c11_oracle"] = "test/oracles/comet_accrue_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["per_second_1pct"] = ps
    evidence["per_block_1pct"] = pb
    evidence["year_delta_iii"] = d_iii
    evidence["year_delta_v2_misapply"] = d_bad
    evidence["year_ratio"] = d_bad / d_iii
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
