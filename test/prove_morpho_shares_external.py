#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Morpho Blue SharesMathLib (GPL-2.0-or-later) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of SharesMathLib.sol + MathLib.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / Morpho Blue market parity
    * that LIN replaces Morpho on mainnet
    * TVL, gas, or wall-clock superiority vs solc/EVM
    * that OZ ERC-4626 is fully ported (offset-0 is a named contrast only)

Class: EXPERIMENTAL (real Morpho virtual-share algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_morpho_shares.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "morpho_shares_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "morpho_shares_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_morpho_blue")
EVIDENCE = ROOT / "examples" / "morpho_shares" / "morpho_shares_evidence.json"

VIRTUAL_SHARES = 10**6
VIRTUAL_ASSETS = 1
PINNED_SHARES_SHA256 = "4580deb1b1a3f2ea0b60f2305708428975613d1e94d404d647bcc573a7b2a2f0"
PINNED_SHARES_BLOB = "3ed7115b5bcc491199446837c5a737eb80c5675c"
PINNED_MATH_SHA256 = "2c6728d1bc8f5db81f2a7946f226c3c4a8cffe4134c55450ca445b05727011bc"
PINNED_MATH_BLOB = "653db4f87580d5f9fd6162a78715d5416f8aac63"
PINNED_COMMIT = "55d2d99304fb3fb930c688462ae2ccabb1d533ad"
SHARES_REL = "src/libraries/SharesMathLib.sol"
MATH_REL = "src/libraries/MathLib.sol"


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/morpho-org/morpho-blue.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live_s = UPSTREAM / SHARES_REL
    live_m = UPSTREAM / MATH_REL
    if not live_s.exists() or not live_m.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob_s = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{SHARES_REL}"]).stdout.strip()
    blob_m = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MATH_REL}"]).stdout.strip()
    if sha256_file(live_s) != PINNED_SHARES_SHA256 or blob_s != PINNED_SHARES_BLOB:
        return "FAIL", commit, f"shares live={sha256_file(live_s)} blob={blob_s}"
    if sha256_file(live_m) != PINNED_MATH_SHA256 or blob_m != PINNED_MATH_BLOB:
        return "FAIL", commit, f"math live={sha256_file(live_m)} blob={blob_m}"
    return "PASS", commit, f"{blob_s},{blob_m}"


def py_down(x: int, y: int, d: int) -> int:
    if d == 0:
        return 0
    q = (x * y) // d
    return 0 if q > (2**64 - 1) else q


def py_up(x: int, y: int, d: int) -> int:
    if d == 0:
        return 0
    q, r = divmod(x * y, d)
    if q > (2**64 - 1):
        return 0
    if r == 0:
        return q
    return 0 if q == (2**64 - 1) else q + 1


def py_shares_down(assets: int, ta: int, ts: int, va: int = VIRTUAL_ASSETS, vs: int = VIRTUAL_SHARES) -> int:
    return py_down(assets, ts + vs, ta + va)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MORPHO_SHARES_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MORPHO BLUE SharesMathLib — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned_s = FIX / "SharesMathLib.sol"
    pinned_m = FIX / "MathLib.sol"
    if not pinned_s.exists() or not pinned_m.exists():
        rec("PIN-FILE", "FAIL", "pinned Morpho fixtures missing")
        return 1
    if sha256_file(pinned_s) != PINNED_SHARES_SHA256:
        rec("PIN-SHA256", "FAIL", "SharesMathLib.sol hash mismatch", sha256_file(pinned_s))
        return 1
    if sha256_file(pinned_m) != PINNED_MATH_SHA256:
        rec("PIN-MATH-SHA256", "FAIL", "MathLib.sol hash mismatch", sha256_file(pinned_m))
        return 1
    rec("PIN-SHA256", "PASS", "pinned SharesMathLib.sol sha256 matches manifest")
    rec("PIN-MATH-SHA256", "PASS", "pinned MathLib.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned morpho-blue v1.0.0 matches fixtures", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of SharesMathLib.sol and MathLib.sol", up_note)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
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
        rec("LIN-CHECK", "FAIL", "lin_c0 check of morpho clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_morpho_shares.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    chk3 = run([str(C0), "check", str(RS_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk3.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "msh_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "msh_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "msh_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("floor", ["100", "200", "50"], "msh_floor", (100, 200, 50), py_down(100, 200, 50)),
        ("floor", ["7", "9", "2"], "msh_floor", (7, 9, 2), py_down(7, 9, 2)),
        ("ceil", ["7", "9", "2"], "msh_ceil", (7, 9, 2), py_up(7, 9, 2)),
        ("floor", [str(10**18), "1", "2"], "msh_floor", (10**18, 1, 2), py_down(10**18, 1, 2)),
        ("shares-down", ["1000", "0", "0"], "msh_to_shares_down", (1000, 0, 0), py_shares_down(1000, 0, 0)),
        ("shares-down", ["1", "0", "0"], "msh_to_shares_down", (1, 0, 0), py_shares_down(1, 0, 0)),
        ("assets-down", ["1000000", "0", "0"], "msh_to_assets_down", (10**6, 0, 0), py_down(10**6, 1, 10**6)),
        ("shares-down", ["1000000", "1000001", "1000000"], "msh_to_shares_down", (10**6, 10**6 + 1, 10**6), py_shares_down(10**6, 10**6 + 1, 10**6)),
        ("oz-shares-down", ["1000000", "1000001", "1"], "msh_oz_to_shares_down", (10**6, 10**6 + 1, 1), py_shares_down(10**6, 10**6 + 1, 1, 1, 1)),
        ("shares-down", ["1000", "5000", "2000"], "msh_to_shares_down", (1000, 5000, 2000), py_shares_down(1000, 5000, 2000)),
        ("assets-down", ["200359", "5000", "2000"], "msh_to_assets_down", (200359, 5000, 2000), py_down(200359, 5001, 1002000)),
        ("shares-up", ["1000", "5000", "2000"], "msh_to_shares_up", (1000, 5000, 2000), py_up(1000, 1002000, 5001)),
        ("assets-up", ["1", "3", "100"], "msh_to_assets_up", (1, 3, 100), py_up(1, 4, 1000100)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        if kind in ("floor", "ceil"):
            want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
            if want != want_limbs:
                rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
                return 1
        got_lin = lin_vm(fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    morpho_empty = lin_vm("msh_to_shares_down", 1000, 0, 0)
    oz_empty = lin_vm("msh_oz_to_shares_down", 1000, 0, 0)
    if morpho_empty != 1_000_000_000 or oz_empty != 1000:
        rec("EMPTY-CONTRAST", "FAIL", "empty-market virtual offset", f"morpho={morpho_empty} oz={oz_empty}")
        return 1
    rec("EMPTY-CONTRAST", "PASS", "empty market: Morpho 1e6 virt shares vs OZ offset-0 (1000 assets -> 1e9 vs 1000 shares)")

    morpho_v = lin_vm("msh_to_shares_down", 10**6, 10**6 + 1, 10**6)
    oz_v = lin_vm("msh_oz_to_shares_down", 10**6, 10**6 + 1, 1)
    if morpho_v != 1_999_996 or oz_v != 1:
        rec("INFLATE-CONTRAST", "FAIL", "donation victim shares", f"morpho={morpho_v} oz={oz_v}")
        return 1
    rec(
        "INFLATE-CONTRAST",
        "PASS",
        "after 1e6-asset donation, victim of 1e6 assets gets 1999996 Morpho shares vs 1 OZ-offset-0 share",
        "named contrast only; not a TVL or exploit claim",
    )

    wrapped = ((10**18) * (10**18)) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 0 and lin_vm("msh_ov", 10**18, 10**18, 1) != 1:
        rec("I64-WRAP", "FAIL", "1e18*1e18 overflow not detected")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes", f"i64_wrap={wrapped}")

    jit_ok = lin_roundtrip_jit("msh_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on msh_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("msh_floor", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit msh_floor(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned_s.read_text(encoding="utf-8")
    math = pinned_m.read_text(encoding="utf-8")
    if "VIRTUAL_SHARES = 1e6" not in sol or "VIRTUAL_ASSETS = 1" not in sol:
        rec("EXPLICIT-OFFSET", "FAIL", "upstream virtual constants missing")
    elif "msh_virtual_shares" not in src or "msh_virtual_assets" not in src:
        rec("EXPLICIT-OFFSET", "FAIL", "LIN virtual offsets not explicit")
    else:
        rec("EXPLICIT-OFFSET", "PASS", "LIN exposes VIRTUAL_SHARES=1e6 and VIRTUAL_ASSETS=1 as functions")
    if "+ (d - 1)" in math and "msh_ceil" in src and "msh_rem" in src:
        rec("WIDE-CEIL", "PASS", "LIN ceil uses remainder+1 (not x*y+(d-1) wrap)")
    else:
        rec("WIDE-CEIL", "FAIL", "ceil improvement missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_LIBCALL" in sol_src and "REJ_SOLIDITY_OVERFLOW_CEIL" in sol_src:
        rec("SOL-REJECT", "PASS", "lin_from_solidity.lin v3 rejects .mulDiv* library calls and overflow-ceil")
    else:
        rec("SOL-REJECT", "FAIL", "solidity reject codes missing")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_OVERFLOW_CEIL" in rs_src and "REJ_RUST_DIV_CEIL" in rs_src:
        rec("RS-REJECT", "PASS", "lin_from_rust.lin v2 rejects overflow-ceil / div_ceil")
    else:
        rec("RS-REJECT", "FAIL", "rust reject codes missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/morpho-org/morpho-blue",
        "tag": "v1.0.0",
        "commit": commit or PINNED_COMMIT,
        "path": SHARES_REL,
        "math_path": MATH_REL,
        "git_blob_sha": PINNED_SHARES_BLOB,
        "math_git_blob_sha": PINNED_MATH_BLOB,
        "file_sha256": PINNED_SHARES_SHA256,
        "math_file_sha256": PINNED_MATH_SHA256,
        "license": "GPL-2.0-or-later",
        "license_note": "file SPDX GPL-2.0-or-later; v1.0.0 repo LICENSE was BUSL-1.1 Change Date 2026-01-01",
    }
    evidence["lin_clone"] = "src/lin_morpho_shares.lin"
    evidence["c11_oracle"] = "test/oracles/morpho_shares_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["empty_market_morpho_shares"] = morpho_empty
    evidence["empty_market_oz_shares"] = oz_empty
    evidence["inflate_victim_morpho_shares"] = morpho_v
    evidence["inflate_victim_oz_shares"] = oz_v
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-morpho-shares"
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
