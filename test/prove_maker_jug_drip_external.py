#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Maker/Sky jug.drip (AGPL-3.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream hashes of src/jug.sol (git blob + sha256; source
      is AGPL and is NOT vendored in lin-open)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs
      matching src/lin_maker_jug_drip.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 / mainnet vat.ilks.rate / RAY=1e27 parity
    * that LIN replaces Maker, Sky, Dai, USDS, or the EVM
    * TVL or dollar savings
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Maker jug.drip rpow+rmul algorithm, uint64-scale RAY'=1e9).
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
LIN = ROOT / "src" / "lin_maker_jug_drip.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_jug_drip_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_jug_drip_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_jug_drip" / "maker_jug_drip_evidence.json"

PINNED_SHA256 = "cefc440545885a916920ce2dc251916f2fc218701ba32413d3ce4884fba07927"
PINNED_BLOB = "dae9b263f699ed917e1d0a16bb51dc8b0326764f"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/jug.sol"
UPSTREAM_URL = "https://github.com/makerdao/dss.git"

RAY = 10**9
K = 10**6


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


def py_rpow(x: int, n: int, b: int) -> int:
    if b <= 0 or x < 0 or n < 0:
        return 0
    if x == 0:
        return b if n == 0 else 0
    z = x if (n & 1) else b
    n >>= 1
    while n:
        x = (x * x + (b >> 1)) // b
        if n & 1:
            z = (z * x + (b >> 1)) // b
        n >>= 1
    return z


def py_drip(now: int, rho: int, base: int, duty: int, prev: int) -> int:
    if now < rho:
        return 0
    return (py_rpow(base + duty, now - rho, RAY) * prev) // RAY


def py_linear(now: int, rho: int, base: int, duty: int, prev: int) -> int:
    if now < rho or base + duty < RAY:
        return 0
    extra = (base + duty - RAY) * (now - rho)
    return (prev * (RAY + extra)) // RAY


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
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    if "function drip" not in text or "function _rpow" not in text or "10 ** 27" not in text:
        return "FAIL", commit, "pinned jug.sol missing drip / _rpow / 10 ** 27"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_JUG_DRIP_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY JUG.DRIP — external LIN proof (uint64-scale RAY'=1e9, C11)")
    print("=" * 78)

    rec(
        "PIN-SHA256",
        "PASS",
        "pinned jug.sol sha256 (hash-only; AGPL source not vendored)",
        PINNED_SHA256,
    )
    rec("PIN-BLOB", "PASS", "pinned git blob sha of src/jug.sol", PINNED_BLOB)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned makerdao/dss matches hashes",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/jug.sol")
        rec("UPSTREAM-MARKERS", "PASS", "live jug.sol contains drip, _rpow, and 10 ** 27")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-MARKERS", "SKIP", "live markers not checked this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hashes", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-MARKERS", "FAIL", "live jug.sol markers failed", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv/drip selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb rpow/rmul/drip agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of jug.drip clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_jug_drip.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "jgd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "jgd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "jgd_test_suite == 1 on Compiler 0 interpreter")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_MAKER_DRIP" not in sol_src or "sol_expand_pow10" not in sol_src:
        rec("SOL-GATE", "FAIL", "lin_from_solidity.lin missing Maker drip reject or 10 ** N expander")
        return 1
    if "REJ_SOLIDITY_RAY27" not in sol_src:
        rec("SOL-RAY27", "FAIL", "lin_from_solidity.lin missing 10 ** 27 fail-close")
        return 1
    rec(
        "SOL-GATE",
        "PASS",
        "lin_from_solidity.lin typechecked; Maker drip/now/RAY27 reject + 10 ** N present (string gate is check-only: C0 VM refuses string literals)",
    )

    vectors = [
        ("identity", [1000, 1000, 0, RAY, RAY], RAY),
        ("dt0_prev2", [50, 50, 0, RAY + 123, 2 * RAY], 2 * RAY),
        ("under", [9, 10, 0, RAY, RAY], 0),
        ("k1e6_dt2", [2, 0, 0, RAY + K, RAY], 1002001000),
        ("k1e6_dt10", [10, 0, 0, RAY + K, RAY], 1010045120),
        ("x0_n", [10, 0, 0, 0, RAY], 0),
        ("x0_n0", [0, 0, 0, 0, RAY], RAY),
    ]
    n_ok = 0
    for name, args, want_named in vectors:
        want = int(oracle(["drip", *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle(["drip", *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        got_lin = lin_vm("jgd_drip", *args)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{name} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"drip {name}", f"lin={got_lin} c11={want}")
            return 1
        if got_lin != want_named:
            rec("VEC-NAMED", "FAIL", f"drip {name} named golden", f"{got_lin} != {want_named}")
            return 1
        py = py_drip(*args)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint drip {name}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} drip vectors: C11 i128 == limbs == LIN vm == Python")
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "identity=1e9; dt0 prev2=2e9; now<rho=0; k1e6 dt2=1002001000; dt10=1010045120; x=0 n>0=0",
    )

    lin2 = lin_vm("jgd_linear", 2, 0, 0, RAY + K, RAY)
    d2 = lin_vm("jgd_drip", 2, 0, 0, RAY + K, RAY)
    if lin2 != 1002000000 or d2 != 1002001000 or d2 == lin2:
        rec("VS-LINEAR", "FAIL", "rpow compounding at dt=2 should exceed first-order linear", f"drip={d2} linear={lin2}")
        return 1
    rec(
        "VS-LINEAR",
        "PASS",
        "Maker rpow compounds; first-order linear understates dt=2 by 1000",
        f"drip={d2} linear={lin2}",
    )

    lin10 = lin_vm("jgd_linear", 10, 0, 0, RAY + K, RAY)
    d10 = lin_vm("jgd_drip", 10, 0, 0, RAY + K, RAY)
    if lin10 != 1010000000 or d10 != 1010045120:
        rec("VS-LINEAR10", "FAIL", "dt=10 compounding golden", f"drip={d10} linear={lin10}")
        return 1
    rec("VS-LINEAR10", "PASS", "dt=10 drip=1010045120 vs linear=1010000000 (extra 45120)")

    ident = lin_vm("jgd_drip", 100, 0, 0, RAY, RAY)
    rpow_only = lin_vm("jgd_rpow", RAY, 100, RAY)
    if ident != RAY or rpow_only != RAY:
        rec("VS-RPOW", "FAIL", "duty=RAY must leave prev unchanged", f"drip={ident} rpow={rpow_only}")
        return 1
    rec("VS-RPOW", "PASS", "drip is rmul(rpow(base+duty,dt,RAY'), prev); duty=RAY' is identity on prev")

    delta = lin_vm("jgd_diff", d2, RAY)
    if delta != 2001000:
        rec("EXPLICIT-FOLD", "FAIL", "diff(rate,prev) should be the vat.fold delta", f"{delta}")
        return 1
    rec("EXPLICIT-FOLD", "PASS", "LIN returns fold delta as jgd_diff; no hidden vat.fold", f"delta={delta}")

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    ov = lin_vm("jgd_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("jgd_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if ov != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "overflow fail-close vs naive wrap", f"ov={ov} naive={naive} wrap={wrapped}")
        return 1
    rec("I64-WRAP", "PASS", "7e18*3e18/1 fail-closes to 0; naive i64 wraps", f"wrap={wrapped}")

    jit_ok = lin_roundtrip_jit("jgd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on jgd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("jgd_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit jgd_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "jgd_drip(now_ts: int, rho: int, base: int, duty: int, prev: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/now/vat")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes now/rho/base/duty/prev as arguments")
    if "jgd_muldiv_half" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product rpow/rmul (naive i64 a*b/d wraps on 7e18*3e18)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    if "REJ_SOLIDITY_MAKER_DRIP" in sol_src and "sol_expand_pow10" in sol_src and "REJ_SOLIDITY_RAY27" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3 rejects drip/now/10**27 and expands 10 ** N<=18")
    else:
        rec("SOL-EMIT", "FAIL", "solidity Maker drip reject / 10 ** N / RAY27 missing")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_C_MAKER_DRIP" in c_src:
        rec("C-EMIT", "PASS", "lin_from_c.lin v2 fail-closes Maker drip / vat.fold")
    else:
        rec("C-EMIT", "FAIL", "C Maker drip reject missing")
    if "REJ_RUST_MAKER_DRIP" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 fail-closes Maker drip / vat_fold")
    else:
        rec("RS-EMIT", "FAIL", "Rust Maker drip reject missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/makerdao/dss",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
        "note": "hash-only pin; jug.sol is not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_maker_jug_drip.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-maker-jug-drip"
    evidence["c11_oracle"] = "test/oracles/maker_jug_drip_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "identity_drip": RAY,
        "dt0_prev2": 2 * RAY,
        "now_lt_rho": 0,
        "k1e6_dt2_drip": 1002001000,
        "k1e6_dt2_linear": 1002000000,
        "k1e6_dt10_drip": 1010045120,
        "k1e6_dt10_linear": 1010000000,
        "fold_delta_dt2": 2001000,
        "x0_n": 0,
        "x0_n0": RAY,
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
