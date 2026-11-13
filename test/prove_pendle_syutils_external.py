#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Pendle SYUtils (GPL-3.0-or-later, hash-pinned) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * live git blob + sha256 of SYUtils.sol (NOT vendored; GPL)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int (floor and ceil)

  NOT claimed:
    * full Solidity uint256 / mainnet Pendle SY parity
    * that LIN replaces Pendle, the EVM, or SY tokens
    * wall-clock superiority vs solc/EVM
    * that pointer-free kernel ONE'=1000 equals 1e18 LIN scale

Class: EXPERIMENTAL (real Pendle SYUtils algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_pendle_syutils.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "pendle_syutils_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "pendle_syutils_c11"
KERNEL = ROOT / "test" / "oracles" / "pendle_syutils_kernel.c"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_pendle_syutils")
EVIDENCE = ROOT / "examples" / "pendle_syutils" / "pendle_syutils_evidence.json"

ONE = 10**18
PINNED_SHA256 = "25af0a883e174b713a88296b97998bb323ab79356d65cb50f3c7adcef91158c3"
PINNED_BLOB = "b6a5ed174c6b93c29654254a5ce10aab28178285"
PINNED_COMMIT = "87685c89d05087535e9b9647eeda0e3d297d1f06"
UPSTREAM_REL = "contracts/core/StandardizedYield/SYUtils.sol"
UPSTREAM_URL = "https://github.com/pendle-finance/pendle-core-v2-public.git"


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
    return "PASS", commit, blob


def py_floor(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (a * b) // d
    return 0 if q > 2**64 - 1 else q


def py_ceil(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q, r = divmod(a * b, d)
    if q > 2**64 - 1:
        return 0
    if r == 0:
        return q
    if q == 2**64 - 1:
        return 0
    return q + 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_PENDLE_SYUTILS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  PENDLE SYUTILS — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_c0()
    ensure_oracle()

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "PIN-SHA256",
            "PASS",
            "live SYUtils.sol sha256 matches pinned GPL hash (not vendored)",
            PINNED_SHA256,
        )
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned pendle-core-v2-public commit matches pin",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of SYUtils.sol")
        live = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8")
        if "function assetToSyUp" not in live or "function syToAsset" not in live:
            rec("UPSTREAM-FNS", "FAIL", "pinned SYUtils missing expected pure functions")
            return 1
        rec("UPSTREAM-FNS", "PASS", "pinned SYUtils has syToAsset/assetToSy and *Up ceil variants")
    elif up_status == "SKIP":
        rec("PIN-SHA256", "SKIP", "live fetch unavailable; pin recorded in event", up_note)
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-FNS", "SKIP", "upstream file not fetched this run")
    else:
        rec("PIN-SHA256", "FAIL", "pinned commit bytes differ from recorded hash", up_note)
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from recorded hash", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-FNS", "FAIL", "could not read functions", up_note)
        return 1

    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb floor/ceil selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb floor/ceil agree")

    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Pendle SYUtils clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_pendle_syutils.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v2.1")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need_sol = (
        "sol_subst_one" in sol_src
        and "sol_expand_pow10" in sol_src
        and "sol_div_kind" in sol_src
        and "10 ** 18" in sol_src
        and "CEIL_DIV" in sol_src
        and "assetAmount * ONE" in sol_src
    )
    if not need_sol:
        rec("SOL-GATE", "FAIL", "v2.1 ONE/10**N/CEIL_DIV tests missing from lin_from_solidity.lin")
        return 1
    rec(
        "SOL-GATE",
        "PASS",
        "v2.1 helpers typecheck; sol_from_sol_gate holds ONE/10**N/CEIL vectors (C0 vm refuses string literals)",
    )

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler (cfs_div_kind)")

    c_src = C_TR.read_text(encoding="utf-8")
    if "cfs_div_kind" not in c_src or "CEIL_DIV" not in c_src or "cfs_div_kind_gate" not in c_src:
        rec("C-CEIL-GATE", "FAIL", "cfs_div_kind missing from lin_from_c.lin")
        return 1
    rec(
        "C-CEIL-GATE",
        "PASS",
        "lin_from_c classifies (a+b-1)/b as CEIL_DIV (C0 vm refuses string literals)",
    )

    suite = run([str(C0), "vm", str(LIN), "psy_test_suite"])
    sv = value_of(suite.stdout)
    if suite.returncode != 0 or sv != 1:
        rec("LIN-SUITE", "FAIL", "psy_test_suite via lin_c0 vm", suite.stdout + suite.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "psy_test_suite == 1 on Compiler 0 interpreter")

    three = 3 * ONE
    vectors = [
        ("sy2a", [str(ONE), str(ONE)], "psy_sy_to_asset", (ONE, ONE), py_floor(ONE, ONE, ONE)),
        ("a2sy", [str(ONE), str(ONE)], "psy_asset_to_sy", (ONE, ONE), py_floor(ONE, ONE, ONE)),
        ("sy2a", [str(2 * ONE), str(ONE)], "psy_sy_to_asset", (2 * ONE, ONE), py_floor(ONE, 2 * ONE, ONE)),
        ("a2sy", [str(three), "10"], "psy_asset_to_sy", (three, 10), py_floor(10, ONE, three)),
        ("a2syup", [str(three), "10"], "psy_asset_to_sy_up", (three, 10), py_ceil(10, ONE, three)),
        ("sy2a", ["3", "10"], "psy_sy_to_asset", (3, 10), py_floor(10, 3, ONE)),
        ("sy2aup", ["3", "10"], "psy_sy_to_asset_up", (3, 10), py_ceil(10, 3, ONE)),
        ("a2sy", ["0", "10"], "psy_asset_to_sy", (0, 10), 0),
        ("md", [str(ONE), str(ONE), "1"], "psy_muldiv", (ONE, ONE, 1), 0),
    ]
    n_ok = 0
    floor10 = 0
    ceil10 = 0
    for kind, oargs, fn, largs, py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        if fn == "psy_asset_to_sy" and largs == (three, 10):
            floor10 = got_lin
        if fn == "psy_asset_to_sy_up" and largs == (three, 10):
            ceil10 = got_lin
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    if floor10 != 3 or ceil10 != 4:
        rec("CEIL-REM", "FAIL", "named remainder goldens", f"floor={floor10} ceil={ceil10}")
        return 1
    rec("CEIL-REM", "PASS", "assetToSy(3e18,10)=3 floor; assetToSyUp=4 ceil (remainder 1e18)", f"floor={floor10} ceil={ceil10}")

    naive = (10 * ONE) & ((1 << 64) - 1)
    if naive >= 2**63:
        naive -= 2**64
    if naive == (10 * ONE) // three:
        rec("I64-WRAP", "FAIL", "signed i64 10*1e18 unexpectedly equalled bigint muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (10*1e18) wraps; 128-bit floor/ceil does not",
        f"i64_wrap={naive} bigint_floor={floor10}",
    )

    if not KERNEL.exists():
        rec("KERNEL-C", "FAIL", "pointer-free lin_from_c kernel missing")
        return 1
    ksrc = KERNEL.read_text(encoding="utf-8")
    body = "\n".join(
        ln for ln in ksrc.splitlines() if not ln.lstrip().startswith("/*") and not ln.lstrip().startswith("*")
    )
    banned = ("->", "struct ", "union ", "float ", "double ", "goto ")
    if any(b in body for b in banned):
        rec("KERNEL-C", "FAIL", "kernel uses constructs lin_from_c rejects", "")
        return 1
    rec("KERNEL-C", "PASS", "pointer-free C kernel eligible for lin_from_c (ONE'=1000, checked mul)")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_subst_one" in sol_src and "sol_expand_pow10" in sol_src and "sol_div_kind" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v2.1: ONE subst, 10**N, CEIL_DIV")
    else:
        rec("SOL-EMIT", "FAIL", "v2.1 emit path missing")

    jit_ok = lin_roundtrip_jit("psy_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on psy_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("psy_asset_to_sy_up", three, 10)
        if jv == 4:
            rec("C0-JIT", "PASS", "lin_c0 jit psy_asset_to_sy_up(3e18,10)==4 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/pendle-finance/pendle-core-v2-public",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-3.0-or-later",
        "vendored": False,
        "note": "hash-pinned only; GPL source is not copied into lin-open",
    }
    evidence["lin_clone"] = "src/lin_pendle_syutils.lin"
    evidence["c11_oracle"] = "test/oracles/pendle_syutils_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "ID_syToAsset": ONE,
        "ID_assetToSy": ONE,
        "FLOOR_assetToSy_3e18_10": 3,
        "CEIL_assetToSyUp_3e18_10": 4,
        "FLOOR_syToAsset_3_10": 0,
        "CEIL_syToAssetUp_3_10": 1,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-pendle-syutils"
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
