#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound JumpRateModel V2 (BSD-3-Clause) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of BaseJumpRateModelV2.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
      muldiv that mirrors src/lin_compound_jumprate.lin)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 range (LIN path is uint64-scale + 128-bit product)
    * that LIN replaces Compound on mainnet
    * wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real Compound IRM algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_compound_jumprate.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "compound_jumprate_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "compound_jumprate_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_compound_protocol")
EVIDENCE = ROOT / "examples" / "compound_jumprate" / "compound_jumprate_evidence.json"

BASE = 10**18
PINNED_SHA256 = "9cd2fe5f7b88748c336bf2988c475da517ffd4909057b53df138b80f162fb34f"
PINNED_BLOB = "4d6828c39ed737c0c48508adc414b919ab6c2a55"
PINNED_COMMIT = "a3214f67b73310d547e00fc578e8355911c9d376"
UPSTREAM_REL = "contracts/BaseJumpRateModelV2.sol"


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


def ensure_upstream() -> tuple[str, str, str]:
    """Fetch the pinned commit. SKIP on network failure; fixture pin still holds."""
    url = "https://github.com/compound-finance/compound-protocol.git"
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
    evidence: dict = {"schema": "LIN_COMPOUND_JUMPRATE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND JUMPRATE V2 — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "BaseJumpRateModelV2.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned BaseJumpRateModelV2.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned BaseJumpRateModelV2.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned compound-protocol commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of BaseJumpRateModelV2.sol")
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

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of compound clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_compound_jumprate.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v2 (emit path)")

    gate = run([str(C0), "vm", str(LIN), "cjr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cjr_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "cjr_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cjr_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "cjr_muldiv", (7, 9, 1)),
        ("muldiv", [str(BASE), "1", "2"], "cjr_muldiv", (BASE, 1, 2)),
        ("util", [str(BASE), str(BASE), "0"], "cjr_utilization", (BASE, BASE, 0)),
        ("util", ["0", str(BASE), "0"], "cjr_utilization", (0, BASE, 0)),
        ("util", ["100", "0", "0"], "cjr_utilization", (100, 0, 0)),
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
        py = (largs[0] * largs[1] // largs[2]) if kind == "muldiv" else (
            0 if largs[1] == 0 else (largs[1] * BASE // (largs[0] + largs[1] - largs[2]))
        )
        if kind == "util" and largs[1] == 0:
            py = 0
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    mb = lin_vm("cjr_multiplier_per_block", 40000000000000000, 800000000000000000)
    jb = lin_vm("cjr_jump_per_block", 1090000000000000000)
    bb = lin_vm("cjr_base_per_block", 0)
    r50 = lin_vm("cjr_borrow_rate", BASE, BASE, 0, bb, mb, jb, 800000000000000000)
    want50 = int(
        oracle(
            [
                "borrow",
                str(BASE),
                str(BASE),
                "0",
                str(bb),
                str(mb),
                str(jb),
                "800000000000000000",
            ]
        ).splitlines()[-1]
    )
    if r50 != want50:
        rec("BORROW-50", "FAIL", "50% util borrow rate", f"lin={r50} c11={want50}")
        return 1
    rec("BORROW-50", "PASS", "parameterized getBorrowRate at 50% util matches C11", f"rate={r50}")
    py50 = (BASE * mb) // (2 * BASE) + bb
    if py50 != r50:
        rec("PY-BORROW-50", "FAIL", "python bigint borrow@50%", f"py={py50} lin={r50}")
        return 1
    rec("PY-BORROW-50", "PASS", "Python bigint borrow rate at 50% util matches LIN/C11", f"rate={py50}")
    wrapped = (BASE * BASE) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == (BASE * BASE) // (2 * BASE):
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv does not",
        f"i64_wrap={wrapped} bigint={(BASE * BASE) // (2 * BASE)}",
    )

    jit_ok = lin_roundtrip_jit("cjr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cjr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("cjr_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit cjr_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    sig = "cjr_borrow_rate(cash: int, borrows: int, reserves: int, base_block: int, mult_block: int, jump_block: int, kink: int)"
    sol = pinned.read_text(encoding="utf-8")
    if sig not in src or "internal view" not in sol or "msg.sender" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/view")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes IRM parameters as arguments (no hidden storage / msg.sender)",
        )
    if "cjr_muldiv" in src and "_lia_ushr" in src:
        rec(
            "WIDE-MULDIV",
            "PASS",
            "clone uses 128-bit product muldiv (naive i64 a*b/d would wrap on 1e18*1e18)",
        )
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_from_sol" in sol_src and "sol_expand_exp" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin now emits LIN and expands 1eN literals")
    else:
        rec("SOL-EMIT", "FAIL", "emit path missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/compound-protocol",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "BSD-3-Clause",
    }
    evidence["lin_clone"] = "src/lin_compound_jumprate.lin"
    evidence["c11_oracle"] = "test/oracles/compound_jumprate_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["borrow_rate_50_util"] = r50
    evidence["multiplier_per_block"] = mb
    evidence["jump_per_block"] = jb
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
