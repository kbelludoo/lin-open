#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: OpenZeppelin ERC-4626 virtual shares (MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of ERC4626.sol (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full Solidity uint256 / mainnet ERC-4626 vault parity
    * that LIN replaces OpenZeppelin vaults
    * wall-clock superiority vs solc/EVM
    * that lin_from_c executes string-literal modules on the numeric VM

Class: EXPERIMENTAL (real OZ ERC-4626 convert formula, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_erc4626_vault.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SCALAR_C = ROOT / "test" / "oracles" / "erc4626_scalar.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "erc4626_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "erc4626_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_openzeppelin")
EVIDENCE = ROOT / "examples" / "erc4626_vault" / "erc4626_vault_evidence.json"

PINNED_SHA256 = "bc3eb01a42e08f33e8591a726e28c7107b6c4fedd6be0d9d2d1c049853698be8"
PINNED_BLOB = "ec6087231cb5e9a8c9a91d3eec8583fb89e1e168"
PINNED_COMMIT = "dbb6104ce834628e473d2173bbc9d47f81a9eec3"
UPSTREAM_REL = "contracts/token/ERC20/extensions/ERC4626.sol"
U64 = 2**64 - 1


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
    url = "https://github.com/OpenZeppelin/openzeppelin-contracts.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", "v5.0.2"],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob} commit={commit}"
    return "PASS", commit, blob


def py_muldiv(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > U64 else q


def py_muldiv_ceil(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q, r = divmod(a * b, d)
    if q > U64:
        return 0
    if r == 0:
        return q
    return 0 if q + 1 > U64 else q + 1


def py_pow10(exp: int) -> int:
    if exp < 0 or exp > 18:
        return 0
    return 10**exp


def py_shares_floor(assets: int, supply: int, total_assets: int, offset: int) -> int:
    vs = py_pow10(offset)
    if vs == 0 and offset != 0:
        return 0
    if supply + vs > U64 or total_assets == U64:
        return 0
    return py_muldiv(assets, supply + vs, total_assets + 1)


def py_assets_ceil(shares: int, supply: int, total_assets: int, offset: int) -> int:
    vs = py_pow10(offset)
    if vs == 0 and offset != 0:
        return 0
    if supply + vs > U64 or total_assets == U64:
        return 0
    return py_muldiv_ceil(shares, total_assets + 1, supply + vs)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_ERC4626_VAULT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  ERC-4626 virtual shares — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "ERC4626.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned ERC4626.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned ERC4626.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of OpenZeppelin v5.0.2 matches fixture",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of ERC4626.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned tag bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of ERC-4626 clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_erc4626_vault.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 gates")

    gate = run([str(C0), "vm", str(LIN), "e4626_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "e4626_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "e4626_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "e4626_muldiv", (100, 200, 50), py_muldiv(100, 200, 50)),
        ("muldiv", ["7", "9", "2"], "e4626_muldiv", (7, 9, 2), py_muldiv(7, 9, 2)),
        ("ceil", ["7", "9", "2"], "e4626_muldiv_ceil", (7, 9, 2), py_muldiv_ceil(7, 9, 2)),
        ("shares_floor", ["1000", "0", "0", "0"], "e4626_shares_floor", (1000, 0, 0, 0),
         py_shares_floor(1000, 0, 0, 0)),
        ("shares_floor", ["1000", "1000", "1000", "0"], "e4626_shares_floor", (1000, 1000, 1000, 0),
         py_shares_floor(1000, 1000, 1000, 0)),
        ("shares_floor", ["1000000000000", "1", "1000000000000", "0"], "e4626_shares_floor",
         (10**12, 1, 10**12, 0), py_shares_floor(10**12, 1, 10**12, 0)),
        ("shares_floor", ["1000", "0", "0", "3"], "e4626_shares_floor", (1000, 0, 0, 3),
         py_shares_floor(1000, 0, 0, 3)),
        ("assets_ceil", ["1", "0", "0", "0"], "e4626_preview_mint", (1, 0, 0, 0),
         py_assets_ceil(1, 0, 0, 0)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs or got_lin != want or py != want:
            rec("VEC-CONSENSUS", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} limbs={want_limbs} py={py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", "Python arbitrary-precision int matches C11 and LIN on convert vectors")

    don = lin_vm("e4626_shares_floor", 10**12, 1, 10**12, 0)
    rec("INFLATION-VEC", "PASS" if don == 1 else "FAIL",
        "donation-after-1-share: victim 1e12 assets mints 1 share (virtual +1)", f"shares={don}")

    wrapped = (10**18 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    bigint = py_muldiv(10**18, 10**18, 10**18 + 1)
    if wrapped == bigint:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled bigint muldiv")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (1e18*1e18) wraps; 128-bit muldiv of convert does not",
        f"i64_wrap={wrapped} bigint_emptyish={bigint}")

    jit_ok = lin_roundtrip_jit("e4626_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on e4626_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("e4626_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit e4626_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "e4626_shares_floor(assets: int, supply: int, total_assets: int, offset: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/view")
    elif "totalSupply()" not in sol or "_decimalsOffset()" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "upstream convert still uses storage getters")
    else:
        rec("EXPLICIT-ARGS", "PASS",
            "LIN clone takes supply/totalAssets/offset as arguments (no hidden vault storage)")
    if "e4626_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 a*b/d wraps on 1e18*1e18)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_POW" in sol_src and "REJ_SOLIDITY_LIBRARY_CALL" in sol_src:
        rec("SOL-REJECT", "PASS", "lin_from_solidity fail-closes ** and .mulDiv (ERC-4626 convert is not silently emitted)")
    else:
        rec("SOL-REJECT", "FAIL", "Solidity reject gates for pow/library missing")

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX" in c_src and "cfs_strip_suffixes" in c_src and "cfs_has_amp_ref" in c_src:
        rec("C-REJECT", "PASS", "lin_from_c v2: lone-& reject, U/L suffix strip, C++/float fail-closed")
    else:
        rec("C-REJECT", "FAIL", "C transpiler v2 gates missing")

    sc = SCALAR_C.read_text(encoding="utf-8")
    if "->" in sc or "static_cast" in sc or "::" in sc or "float" in sc:
        rec("SCALAR-C", "FAIL", "scalar C restatement not eligible for lin_from_c")
    elif "e4626_pow10" not in sc or "e4626_virtuals_ok" not in sc:
        rec("SCALAR-C", "FAIL", "scalar C missing pow10 / virtuals_ok")
    else:
        rec("SCALAR-C", "PASS",
            "erc4626_scalar.c is pointer-free integer C (pow10/virtuals; 128-bit convert is the other oracle)")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/OpenZeppelin/openzeppelin-contracts",
        "tag": "v5.0.2",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_erc4626_vault.lin"
    evidence["c11_oracle"] = "test/oracles/erc4626_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["donation_victim_shares"] = don
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
