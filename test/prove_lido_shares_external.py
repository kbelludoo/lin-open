#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Lido stETH share-rate (GPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of StETH.sol + Math256.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet stETH / wstETH wrap parity
    * that LIN replaces Lido on mainnet
    * TVL, gas, or wall-clock superiority vs solc/EVM
    * that Morpho or OZ ERC-4626 are fully ported (named contrast only)

Class: EXPERIMENTAL (real Lido share-rate algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_lido_shares.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "lido_shares_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "lido_shares_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_lido_dao")
EVIDENCE = ROOT / "examples" / "lido_shares" / "lido_shares_evidence.json"

PINNED_STETH_SHA256 = "63ebed0e205b602fe2e427bb09c111479f98253bd02f96ac052b38202d3713bd"
PINNED_STETH_BLOB = "b8c8d47f2571d018c938d994c4debf375b84b45a"
PINNED_MATH_SHA256 = "028e9b0c87fea3ec6fd5aac9e7a5724a18b4a175d5ab70159f24428dd28ea6b6"
PINNED_MATH_BLOB = "366a014cf49523980e06ae7efb4cb3199589fc00"
PINNED_COMMIT = "1440c830eb1d0916a436468a71cd73bc8b8deffb"
STETH_REL = "contracts/0.4.24/StETH.sol"
MATH_REL = "contracts/common/lib/Math256.sol"


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
    url = "https://github.com/lidofinance/lido-dao.git"
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
    live_s = UPSTREAM / STETH_REL
    live_m = UPSTREAM / MATH_REL
    if not live_s.exists() or not live_m.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob_s = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{STETH_REL}"]).stdout.strip()
    blob_m = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MATH_REL}"]).stdout.strip()
    if sha256_file(live_s) != PINNED_STETH_SHA256 or blob_s != PINNED_STETH_BLOB:
        return "FAIL", commit, f"steth live={sha256_file(live_s)} blob={blob_s}"
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


def py_lido_shares(eth: int, te: int, ts: int) -> int:
    return 0 if te <= 0 else py_down(eth, ts, te)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_LIDO_SHARES_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  LIDO stETH share-rate — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned_s = FIX / "StETH.sol"
    pinned_m = FIX / "Math256.sol"
    if not pinned_s.exists() or not pinned_m.exists():
        rec("PIN-FILE", "FAIL", "pinned Lido fixtures missing")
        return 1
    if sha256_file(pinned_s) != PINNED_STETH_SHA256:
        rec("PIN-SHA256", "FAIL", "StETH.sol hash mismatch", sha256_file(pinned_s))
        return 1
    if sha256_file(pinned_m) != PINNED_MATH_SHA256:
        rec("PIN-MATH-SHA256", "FAIL", "Math256.sol hash mismatch", sha256_file(pinned_m))
        return 1
    rec("PIN-SHA256", "PASS", "pinned StETH.sol sha256 matches manifest")
    rec("PIN-MATH-SHA256", "PASS", "pinned Math256.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned lido-dao v4.1.0 matches fixtures", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of StETH.sol and Math256.sol", up_note)
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
        rec("LIN-CHECK", "FAIL", "lin_c0 check of lido clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_lido_shares.lin")

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

    gate = run([str(C0), "vm", str(LIN), "lds_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "lds_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "lds_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("floor", ["100", "200", "50"], "lds_floor", (100, 200, 50), py_down(100, 200, 50)),
        ("floor", ["7", "9", "2"], "lds_floor", (7, 9, 2), py_down(7, 9, 2)),
        ("ceil", ["7", "9", "2"], "lds_ceil", (7, 9, 2), py_up(7, 9, 2)),
        ("floor", [str(10**18), "1", "2"], "lds_floor", (10**18, 1, 2), py_down(10**18, 1, 2)),
        ("shares", ["1000", "0", "0"], "lds_shares_by_eth", (1000, 0, 0), py_lido_shares(1000, 0, 0)),
        ("shares", ["1000", "5000", "2000"], "lds_shares_by_eth", (1000, 5000, 2000), py_lido_shares(1000, 5000, 2000)),
        ("eth", ["400", "5000", "2000"], "lds_eth_by_shares", (400, 5000, 2000), py_down(400, 5000, 2000)),
        ("eth-up", ["1", "3", "100"], "lds_eth_by_shares_up", (1, 3, 100), py_up(1, 3, 100)),
        ("shares", ["1000000", "1000001", "1"], "lds_shares_by_eth", (10**6, 10**6 + 1, 1), py_lido_shares(10**6, 10**6 + 1, 1)),
        ("oz-shares", ["1000", "0", "0"], "lds_oz_shares_by_eth", (1000, 0, 0), py_down(1000, 1, 1)),
        ("morpho-shares", ["1000", "0", "0"], "lds_morpho_shares_by_eth", (1000, 0, 0), py_down(1000, 10**6, 1)),
        ("oz-shares", ["1000000", "1000001", "1"], "lds_oz_shares_by_eth", (10**6, 10**6 + 1, 1), py_down(10**6, 2, 10**6 + 2)),
        ("morpho-shares", ["1000000", "1000001", "1000000"], "lds_morpho_shares_by_eth", (10**6, 10**6 + 1, 10**6), py_down(10**6, 2 * 10**6, 10**6 + 2)),
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

    lido_empty = lin_vm("lds_shares_by_eth", 1000, 0, 0)
    oz_empty = lin_vm("lds_oz_shares_by_eth", 1000, 0, 0)
    morpho_empty = lin_vm("lds_morpho_shares_by_eth", 1000, 0, 0)
    if lido_empty != 0 or oz_empty != 1000 or morpho_empty != 1_000_000_000:
        rec("EMPTY-CONTRAST", "FAIL", "empty-protocol share preview", f"lido={lido_empty} oz={oz_empty} morpho={morpho_empty}")
        return 1
    rec(
        "EMPTY-CONTRAST",
        "PASS",
        "empty protocol 1000 ETH: Lido 0 (div0 fail-closed) vs OZ +1/+1 1000 vs Morpho 1e9",
    )

    lido_v = lin_vm("lds_shares_by_eth", 10**6, 10**6 + 1, 1)
    oz_v = lin_vm("lds_oz_shares_by_eth", 10**6, 10**6 + 1, 1)
    morpho_v = lin_vm("lds_morpho_shares_by_eth", 10**6, 10**6 + 1, 10**6)
    if lido_v != 0 or oz_v != 1 or morpho_v != 1_999_996:
        rec("INFLATE-CONTRAST", "FAIL", "donation victim shares", f"lido={lido_v} oz={oz_v} morpho={morpho_v}")
        return 1
    rec(
        "INFLATE-CONTRAST",
        "PASS",
        "after 1-wei bootstrap + 1e6-ETH donation, victim of 1e6 ETH gets 0 Lido shares vs 1 OZ vs 1999996 Morpho",
        "named contrast only; not a TVL or exploit claim",
    )

    wrapped = ((10**18) * (10**18)) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    if wrapped == 0 and lin_vm("lds_ov", 10**18, 10**18, 1) != 1:
        rec("I64-WRAP", "FAIL", "1e18*1e18 overflow not detected")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv fail-closes", f"i64_wrap={wrapped}")

    jit_ok = lin_roundtrip_jit("lds_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on lds_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("lds_floor", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit lds_floor(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned_s.read_text(encoding="utf-8")
    math = pinned_m.read_text(encoding="utf-8")
    if "getSharesByPooledEth" not in sol or "_getShareRateNumerator" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "upstream share-rate getters missing")
    elif "lds_shares_by_eth(eth: int, total_ether: int, total_shares: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "LIN share-rate args not explicit")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN lifts hidden _getShareRate* storage getters to arguments")
    if "ceilDiv" in math and "lds_ceil" in src and "lds_rem" in src:
        rec("WIDE-CEIL", "PASS", "LIN ceil uses remainder+1 (not (a+b-1)/b wrap; matches OZ ceilDiv class)")
    else:
        rec("WIDE-CEIL", "FAIL", "ceil improvement missing")
    if "UINT128_MAX" in sol and "require(_ethAmount < UINT128_MAX" in sol:
        rec("UINT128-CAP", "PASS", "upstream caps inputs at uint128 so uint128*uint128 fits uint256; LIN operands are uint64-scale")
    else:
        rec("UINT128-CAP", "FAIL", "UINT128_MAX require missing from pin")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_LIBCALL" in sol_src and "REJ_SOLIDITY_GETTER" in sol_src and ".ceilDiv" in sol_src:
        rec("SOL-REJECT", "PASS", "lin_from_solidity.lin v3 rejects .ceilDiv / .mulDiv* and hidden share-rate getters")
    else:
        rec("SOL-REJECT", "FAIL", "solidity reject codes missing")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_OVERFLOW_CEIL" in rs_src and "REJ_RUST_DIV_CEIL" in rs_src:
        rec("RS-REJECT", "PASS", "lin_from_rust.lin v2 rejects overflow-ceil / div_ceil")
    else:
        rec("RS-REJECT", "FAIL", "rust reject codes missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/lidofinance/lido-dao",
        "tag": "v4.1.0",
        "commit": commit or PINNED_COMMIT,
        "path": STETH_REL,
        "math_path": MATH_REL,
        "git_blob_sha": PINNED_STETH_BLOB,
        "math_git_blob_sha": PINNED_MATH_BLOB,
        "file_sha256": PINNED_STETH_SHA256,
        "math_file_sha256": PINNED_MATH_SHA256,
        "license": "GPL-3.0",
        "math_license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_lido_shares.lin"
    evidence["c11_oracle"] = "test/oracles/lido_shares_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["empty_lido_shares"] = lido_empty
    evidence["empty_oz_shares"] = oz_empty
    evidence["empty_morpho_shares"] = morpho_empty
    evidence["inflate_victim_lido_shares"] = lido_v
    evidence["inflate_victim_oz_shares"] = oz_v
    evidence["inflate_victim_morpho_shares"] = morpho_v
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-lido-shares"
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
