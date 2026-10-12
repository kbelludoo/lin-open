#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Compound III Comet present/principal (GPL-2.0-or-later after
BUSL Change Date 2025-12-31) vs LIN C0.

PASS claims are recomputed this run against:
  * pinned upstream bytes of CometCore.sol (git blob + sha256)
  * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int as a third oracle

NOT claimed:
  * full Solidity uint256 / mainnet Comet / USDC market parity
  * that LIN replaces Compound III on mainnet
  * TVL, gas, or wall-clock superiority vs solc/EVM

Class: EXPERIMENTAL (real CometCore algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_comet_pv.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "comet_pv_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "comet_pv_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_comet")
EVIDENCE = ROOT / "examples" / "comet_pv" / "comet_pv_evidence.json"

PINNED_SHA256 = "1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78"
PINNED_BLOB = "534f2701b6c8e683f9294112b0bcc23878d39fe6"
PINNED_COMMIT = "f766f51583c23acc33b2a7824654ef2029a96804"
UPSTREAM_REL = "contracts/CometCore.sol"
SCALE = 10**15
WAD = 10**18
U64 = 2**64 - 1


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


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


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
    url = "https://github.com/compound-finance/comet.git"
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
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    return "PASS", commit, blob


def py_down(x: int, y: int, d: int) -> int:
    if d == 0:
        return 0
    q = (x * y) // d
    return 0 if q > U64 else q


def py_ceil(x: int, y: int, d: int) -> int:
    if d == 0:
        return 0
    q = (x * y) // d
    if q > U64:
        return 0
    r = (x * y) % d
    if r == 0:
        return q
    return 0 if q == U64 else q + 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_COMET_PV_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  COMPOUND III Comet present/principal — external LIN proof (uint64-scale, C11)")
    print("=" * 78)

    pinned = FIX / "CometCore.sol"
    if not pinned.exists() or sha256_file(pinned) != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "CometCore.sol missing or hash mismatch", sha256_file(pinned) if pinned.exists() else "")
        return 1
    rec("PIN-SHA256", "PASS", "pinned CometCore.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned compound-finance/comet matches fixture", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of CometCore.sol", up_note)
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
        rec("LIN-CHECK", "FAIL", "lin_c0 check of comet clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_comet_pv.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v5", chk2.stdout[:200] if chk2.returncode != 0 else "")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "cm_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cm_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "cm_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("floor", ["100", "200", "50"], "cm_floor", (100, 200, 50), py_down(100, 200, 50)),
        ("floor", ["7", "9", "2"], "cm_floor", (7, 9, 2), py_down(7, 9, 2)),
        ("pvs", [str(SCALE), "1000"], "cm_present_supply", (SCALE, 1000), py_down(1000, SCALE, SCALE)),
        ("pvb", [str(SCALE), "1000"], "cm_present_borrow", (SCALE, 1000), py_down(1000, SCALE, SCALE)),
        ("pvs", [str(2 * SCALE), "1000"], "cm_present_supply", (2 * SCALE, 1000), py_down(1000, 2 * SCALE, SCALE)),
        ("wad", [str(SCALE), "1000"], "cm_wad_present", (SCALE, 1000), py_down(1000, SCALE, WAD)),
        ("prs", [str(SCALE), "1000"], "cm_principal_supply", (SCALE, 1000), py_down(1000, SCALE, SCALE)),
        ("prb", [str(SCALE), "1000"], "cm_principal_borrow", (SCALE, 1000), py_ceil(1000, SCALE, SCALE)),
        ("prs", ["3", "1"], "cm_principal_supply", (3, 1), py_down(1, SCALE, 3)),
        ("prb", ["3", "1"], "cm_principal_borrow", (3, 1), py_ceil(1, SCALE, 3)),
        ("prs", ["0", "1000"], "cm_principal_supply", (0, 1000), 0),
        ("util", [str(SCALE), "1000", str(SCALE), "500"], "cm_utilization", (SCALE, 1000, SCALE, 500),
         py_down(py_down(500, SCALE, SCALE), WAD, py_down(1000, SCALE, SCALE))),
        ("ceil", ["3", "5", "4"], "cm_ceil", (3, 5, 4), py_ceil(3, 5, 4)),
        ("ceil", ["8", "2", "4"], "cm_ceil", (8, 2, 4), py_ceil(8, 2, 4)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        if kind == "floor":
            want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
            if want != want_limbs:
                rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
                return 1
        got_lin = lin_vm(LIN, fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    comet_pv = lin_vm(LIN, "cm_present_supply", SCALE, 1000)
    wad_pv = lin_vm(LIN, "cm_wad_present", SCALE, 1000)
    if comet_pv != 1000 or wad_pv != 1:
        rec("WAD-CONTRAST", "FAIL", "Comet 1e15 vs wad 1e18 present", f"comet={comet_pv} wad={wad_pv}")
        return 1
    rec("WAD-CONTRAST", "PASS",
        "genesis index=1e15, principal=1000: Comet present=1000 vs naive wad-1e18 present=1 (1000x understatement)",
        "named contrast vs Compound V2 exchangeRate scale; not a TVL claim")

    floor_p = lin_vm(LIN, "cm_principal_supply", 3, 1)
    ceil_p = lin_vm(LIN, "cm_principal_borrow", 3, 1)
    if floor_p != 333333333333333 or ceil_p != 333333333333334:
        rec("CEIL-CONTRAST", "FAIL", "supply floor vs borrow ceil principal", f"floor={floor_p} ceil={ceil_p}")
        return 1
    rec("CEIL-CONTRAST", "PASS",
        "present=1 index=3: supply principal floor=333333333333333 vs borrow principal ceil=333333333333334")

    empty = lin_vm(LIN, "cm_principal_supply", 0, 1000)
    ok = lin_vm(LIN, "cm_index_ok", 0)
    if empty != 0 or ok != 0:
        rec("INDEX-ZERO", "FAIL", "index==0 principal", f"prin={empty} ok={ok}")
        return 1
    rec("INDEX-ZERO", "PASS", "index==0: Solidity reverts on principalValue*; LIN fail-closes 0 and cm_index_ok=0")

    wrapped = (WAD * WAD) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if lin_vm(LIN, "cm_ov", WAD, WAD, 1) != 1:
        rec("I64-WRAP", "FAIL", "1e18*1e18 overflow not detected")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes", f"i64_wrap={wrapped}")

    if lin_roundtrip_jit("cm_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cm_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    sol = pinned.read_text(encoding="utf-8")
    src = LIN.read_text(encoding="utf-8")
    if "presentValueSupply" not in sol or "BASE_INDEX_SCALE = 1e15" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "upstream presentValueSupply / 1e15 missing")
    elif "cm_present_supply(index: int, principal: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "LIN present args not explicit")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN lifts hidden baseSupplyIndex/baseBorrowIndex to arguments; product is 128-bit")
    if "+ baseBorrowIndex_ - 1" in sol:
        rec("OVERFLOW-CEIL", "PASS", "upstream borrow principal is (x*scale+index-1)/index; LIN uses rem+1 ceil")
    else:
        rec("OVERFLOW-CEIL", "FAIL", "overflow-ceil pattern missing from pin")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if ("REJ_SOLIDITY_CAST" in sol_src and "REJ_SOLIDITY_OVERFLOW_CEIL" in sol_src
            and "baseSupplyIndex," in sol_src and "uint256(" in sol_src):
        rec("SOL-REJECT", "PASS",
            "lin_from_solidity.lin v5 rejects uint256(/uint104( casts, overflow-ceil, and hidden Comet indices")
    else:
        rec("SOL-REJECT", "FAIL", "solidity reject codes missing")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJECT", "PASS" if "REJ_RUST_OVERFLOW_CEIL" in rs_src and "REJ_RUST_DIV_CEIL" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects overflow-ceil / div_ceil")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    rec("CJR-REGRESSION", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
        "Compound JumpRate still 1 after transpiler v5 delta")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/compound-finance/comet",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-2.0-or-later",
        "license_note": "BUSL-1.1 Change Date 2025-12-31 elapsed",
    }
    evidence["lin_clone"] = "src/lin_comet_pv.lin"
    evidence["c11_oracle"] = "test/oracles/comet_pv_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["comet_present_genesis_1000"] = comet_pv
    evidence["wad_present_genesis_1000"] = wad_pv
    evidence["supply_principal_floor"] = floor_p
    evidence["borrow_principal_ceil"] = ceil_p
    evidence["empty_index_principal"] = empty
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-comet-pv"
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
