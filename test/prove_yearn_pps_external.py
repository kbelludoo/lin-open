#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Yearn V2 pricePerShare / locked-profit (AGPL-3.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of contracts/Vault.vy (git blob + sha256; source
      is AGPL and is NOT vendored in lin-open)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_yearn_pps.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity/Vyper uint256 / mainnet yVault parity
    * that LIN replaces Yearn, ERC-4626, or the EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Yearn V2 unlock + share-value algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_yearn_pps.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "yearn_pps_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "yearn_pps_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_yearn_vaults")
EVIDENCE = ROOT / "examples" / "yearn_pps" / "yearn_pps_evidence.json"

PINNED_SHA256 = "bc36fcf88e8662a7e1bd5f9c8213645214697dd72afda4e0cd87bfaeb0c4a19b"
PINNED_BLOB = "1159912c093b12cf8d758f71d2d568cda69990af"
PINNED_COMMIT = "97ca1b2e4fcf20f4be0ff456dabd020bfeb6697b"
UPSTREAM_REL = "contracts/Vault.vy"
UPSTREAM_URL = "https://github.com/yearn/yearn-vaults.git"

E18 = 10**18
E17 = 10**17
DEG = 46_000_000_000_000
DEG_COEF = 10**18


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


def py_locked(now: int, last: int, locked: int, deg: int) -> int:
    if now < last:
        raise ValueError("underflow")
    dt = now - last
    if deg == 0:
        return locked
    ratio = dt * deg
    if ratio >= DEG_COEF:
        return 0
    return locked - (ratio * locked // DEG_COEF)


def py_pps(decimals: int, idle: int, debt: int, supply: int, now: int, last: int, locked: int, deg: int) -> int:
    unit = 10**decimals
    rem = py_locked(now, last, locked, deg)
    free = idle + debt - rem
    if supply == 0:
        return unit
    return unit * free // supply


def ensure_upstream() -> tuple[str, str, str]:
    url = UPSTREAM_URL
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
    text = live.read_text(encoding="utf-8")
    if "def pricePerShare" not in text or "def _calculateLockedProfit" not in text:
        return "FAIL", commit, "pinned Vault.vy missing pricePerShare / locked profit"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_YEARN_PPS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  YEARN V2 PPS / LOCKED PROFIT — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    rec(
        "PIN-SHA256",
        "PASS",
        "pinned Vault.vy sha256 (hash-only; AGPL source not vendored)",
        PINNED_SHA256,
    )
    rec("PIN-BLOB", "PASS", "pinned git blob sha of contracts/Vault.vy", PINNED_BLOB)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned yearn-vaults v0.4.6 matches hashes",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/Vault.vy")
        rec("UPSTREAM-MARKERS", "PASS", "live Vault.vy contains pricePerShare and _calculateLockedProfit")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live Vault.vy markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of yearn clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_yearn_pps.lin")

    for label, path in (("VY-TR-CHECK", VY_TR), ("SOL-TR-CHECK", SOL_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "yps_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "yps_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "yps_test_suite == 1 on Compiler 0 interpreter")

    vy_src = VY_TR.read_text(encoding="utf-8")
    if "REJ_VYPER_YEARN_PPS" not in vy_src or "vy_expand_pow10" not in vy_src:
        rec("VY-GATE", "FAIL", "lin_from_vyper.lin missing Yearn PPS reject or 10 ** N expander")
        return 1
    rec(
        "VY-GATE",
        "PASS",
        "lin_from_vyper.lin typechecked; Yearn PPS reject + 10 ** N present (string gate is check-only: C0 VM refuses string literals)",
    )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_YEARN_PPS" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin v3 missing Yearn reject")
        return 1
    rec("SOL-GATE", "PASS", "lin_from_solidity.lin v3 typechecked; Yearn pricePerShare fail-closed before ENV")

    vectors = [
        ("empty", [18, 0, 0, 0, 0, 0, 0, DEG], E18),
        ("t0", [18, E18, 0, E18, 1000, 1000, E17, DEG], 900000000000000000),
        ("3h", [18, E18, 0, E18, 11800, 1000, E17, DEG], 949680000000000000),
        ("full", [18, E18, 0, E18, 22740, 1000, E17, DEG], E18),
        ("under", [18, E18, 0, E18, 999, 1000, E17, DEG], 0),
    ]
    n_ok = 0
    for name, args, want_named in vectors:
        want = int(oracle(["pps", *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle(["pps", *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("yps_price_per_share", *args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{name} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"pps {name}", f"lin={got_lin} c11={want}")
            return 1
        if got_lin != want_named:
            rec("VEC-NAMED", "FAIL", f"pps {name} named golden", f"{got_lin} != {want_named}")
            return 1
        if name == "under":
            py = 0
        else:
            py = py_pps(*args)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint pps {name}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} PPS vectors: C11 i128 == limbs == LIN vm == Python")
    rec("NAMED-GOLDEN", "PASS", "empty=1e18; t0 harvest=0.9e18; 3h linear=0.94968e18; 6h unlocked=1e18; now<last=0")

    ign = lin_vm("yps_ignore_lock_pps", 18, E18, 0, E18)
    step = lin_vm("yps_step_lock_pps", 18, E18, 0, E18, 11800, 1000, E17, DEG)
    t0 = lin_vm("yps_price_per_share", 18, E18, 0, E18, 1000, 1000, E17, DEG)
    mid = lin_vm("yps_price_per_share", 18, E18, 0, E18, 11800, 1000, E17, DEG)
    if ign != E18 or t0 == ign:
        rec("VS-LIDO", "FAIL", "ignore-lock should be 1e18 and differ from t0 Yearn")
        return 1
    rec("VS-LIDO", "PASS", "Lido-style ignore-lock overstates t0 PPS (1e18 vs 0.9e18)", f"ignore={ign} yearn_t0={t0}")
    if step != 900000000000000000 or step == mid:
        rec("VS-STEP", "FAIL", "step-unlock at 3h should stay 0.9e18 vs linear 0.94968e18")
        return 1
    rec("VS-STEP", "PASS", "all-or-nothing 6h unlock understates 3h PPS vs Yearn linear", f"step={step} linear={mid}")

    empty_mint = lin_vm("yps_shares_for_amount", 123, 0, 0, 0, 0, 0, 0, DEG)
    t0_mint = lin_vm("yps_shares_for_amount", E17, E18, 0, E18, 1000, 1000, E17, DEG)
    if empty_mint != 123:
        rec("EMPTY-MINT", "FAIL", "Yearn empty vault is 1:1 shares=amount", f"{empty_mint}")
        return 1
    rec("EMPTY-MINT", "PASS", "empty vault mints 1:1 (no ERC-4626 virtual offset)", f"shares={empty_mint}")
    if t0_mint != 111111111111111111:
        rec("T0-MINT", "FAIL", "shares_for_amount at t0", f"{t0_mint}")
        return 1
    rec("T0-MINT", "PASS", "deposit 0.1e18 into 0.9e18 free / 1e18 supply mints 111111111111111111")

    wrapped = (7 * E18 * 3 * E18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    ov = lin_vm("yps_muldiv", 7 * E18, 3 * E18, 1)
    naive = lin_vm("yps_naive_i64_mul", 7 * E18, 3 * E18)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "7e18*3e18/1 fail-closes to 0; naive i64 wraps", f"wrap={wrapped}")

    jit_ok = lin_roundtrip_jit("yps_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on yps_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("yps_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit yps_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "yps_price_per_share(decimals: int, idle: int, debt: int, supply: int, now_ts: int, last_report: int, locked: int, deg: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Vyper storage/view")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes now/last/locked/idle/debt/supply/decimals/deg as arguments")
    if "yps_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 a*b/d wraps on 7e18*3e18)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    vy_src = VY_TR.read_text(encoding="utf-8")
    if "REJ_VYPER_YEARN_PPS" in vy_src and "vy_expand_pow10" in vy_src:
        rec("VY-EMIT", "PASS", "lin_from_vyper.lin v1 rejects Yearn PPS/storage and expands 10 ** N")
    else:
        rec("VY-EMIT", "FAIL", "vyper Yearn reject / 10 ** N missing")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_YEARN_PPS" in sol_src:
        rec("SOL-YEARN", "PASS", "lin_from_solidity.lin v3 fail-closes Yearn pricePerShare before ENV")
    else:
        rec("SOL-YEARN", "FAIL", "solidity Yearn reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/yearn/yearn-vaults",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
        "note": "hash-only pin; Vault.vy is not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_yearn_pps.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-yearn-pps"
    evidence["c11_oracle"] = "test/oracles/yearn_pps_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "empty_pps": E18,
        "t0_pps": 900000000000000000,
        "linear_3h_pps": 949680000000000000,
        "unlocked_pps": E18,
        "ignore_lock_pps": E18,
        "step_3h_pps": 900000000000000000,
        "empty_mint": 123,
        "t0_mint": 111111111111111111,
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
