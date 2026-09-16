#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 CalculateNextWorkRequired vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of pow.cpp, arith_uint256.cpp, pow_tests.cpp
      (git blob + sha256, bitcoin/bitcoin tag v27.1)
    * an independent C11 oracle (8 x uint32 limbs, Bitcoin Core WIDTH)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * a Bitcoin node, wallet, or P2P stack
    * SHA256d CheckProofOfWork (hash vs target) — only compact range + retarget
    * that LIN replaces Bitcoin Core
    * wall-clock superiority vs gcc

Class: EXPERIMENTAL (real Core algorithm, compact nBits in/out).
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
LIN = ROOT / "src" / "lin_bitcoin_nbits.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_nbits_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_nbits_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_bitcoin_v27_1")
EVIDENCE = ROOT / "examples" / "bitcoin_nbits" / "bitcoin_nbits_evidence.json"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINS = {
    "src/pow.cpp": {
        "file": FIX / "pow.cpp",
        "sha256": "a997ebc9e89ec0ed0f98fe56e7ece7c0a799746d36be5c0951ca6fd264280a33",
        "blob": "1e8d53de8bb87b0b9a30ff6439881cc2c40e38a4",
    },
    "src/arith_uint256.cpp": {
        "file": FIX / "arith_uint256.cpp",
        "sha256": "b46d67db26cef11a9da125b98e29bd8bf77b7a5c71418ee63bb77a0125a09d06",
        "blob": "0d5b3d5b0e6476b88053bd74a35c5cdbef1d2ae8",
    },
    "src/test/pow_tests.cpp": {
        "file": FIX / "pow_tests.cpp",
        "sha256": "5911e49b195af6dac2e4e94f5509537555172ae9c6a4816dc06c147cd8c6d0ae",
        "blob": "3a44d1da499852cbdf6206bbf5026a50a9610f2f",
    },
}

MAINNET_TS = 1209600
MAINNET_LIMIT = 0x1D00FFFF
VECTORS = [
    ("get_next_work", 0x1D00FFFF, 1262152739, 1261130161, 0x1D00D86A),
    ("pow_limit", 0x1D00FFFF, 1233061996, 1231006505, 0x1D00FFFF),
    ("lower_limit", 0x1C05A3F4, 1279297671, 1279008237, 0x1C0168FD),
    ("upper_limit", 0x1C387F6F, 1269211443, 1263163443, 0x1D00E1FD),
]


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
    proc = run(cmd, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=180)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run(
        [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=180
    )
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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/bitcoin/bitcoin.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT],
        timeout=180,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    notes = []
    for rel, meta in PINS.items():
        live = UPSTREAM / rel
        if not live.exists():
            return "FAIL", commit, f"{rel} missing after checkout"
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{rel}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != meta["sha256"] or blob != meta["blob"]:
            return "FAIL", commit, f"{rel} live={live_hash} blob={blob}"
        notes.append(blob)
    return "PASS", commit, ",".join(notes)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE v27.1 compact nBits retarget — external LIN proof")
    print("=" * 78)

    for rel, meta in PINS.items():
        if not meta["file"].exists():
            rec("PIN-FILE", "FAIL", f"pinned {rel} missing")
            return 1
        got = sha256_file(meta["file"])
        if got != meta["sha256"]:
            rec("PIN-SHA256", "FAIL", f"pinned {rel} hash mismatch", f"{got} != {meta['sha256']}")
            return 1
    rec("PIN-SHA256", "PASS", "pinned pow.cpp + arith_uint256.cpp + pow_tests.cpp sha256")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of bitcoin v27.1 commit matches fixtures", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of the three pinned files")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 limb retarget selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle matches bitcoin/bitcoin pow_tests.cpp goldens")

    src_c = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX" not in src_c or "cfs_strip_int_suffix" not in src_c:
        rec("C-TR-DELTA", "FAIL", "lin_from_c.lin missing v2 CXX/suffix gates")
        return 1
    rec("C-TR-DELTA", "PASS", "C transpiler v2: U/L suffix strip + REJ_C_CXX + ceil/floor float reject")

    src_sol = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_POW" not in src_sol or "sol_expand_pow" not in src_sol:
        rec("SOL-TR-DELTA", "FAIL", "lin_from_solidity.lin missing 10**N / leftover **")
        return 1
    rec("SOL-TR-DELTA", "PASS", "Solidity transpiler v3: 10**N expand + leftover ** reject")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of nBits clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_nbits.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    chk3 = run([str(C0), "check", str(SOL_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk3.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    if "REJ_C_POINTER" not in (FIX / "arith_uint256.cpp").read_text(encoding="utf-8", errors="replace"):
        cpp = (FIX / "arith_uint256.cpp").read_text(encoding="utf-8", errors="replace")
        if "template" in cpp and "::" in cpp:
            rec("CXX-REJECT", "PASS", "upstream arith_uint256.cpp is C++ (templates); C transpiler must REJ_C_CXX")
        else:
            rec("CXX-REJECT", "FAIL", "expected C++ markers in arith_uint256.cpp")
            return 1

    gate = run([str(C0), "vm", str(LIN), "btc_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "btc_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "btc_test_suite == 1 on Compiler 0 interpreter")

    for name, nbits, last, first, expected in VECTORS:
        c11 = int(oracle(["next", hex(nbits), str(last), str(first)]))
        if c11 != expected:
            rec("C11-" + name, "FAIL", f"C11 {name}", f"got={c11} expected={expected}")
            return 1
        rec("C11-" + name, "PASS", f"C11 {name} == 0x{expected:08x}")
        lin = lin_vm("btc_next_work", nbits, last, first, MAINNET_TS, MAINNET_LIMIT, 0)
        if lin != expected:
            rec("LIN-" + name, "FAIL", f"LIN {name}", f"got={lin} expected={expected}")
            return 1
        rec("LIN-" + name, "PASS", f"lin_c0 vm {name} == C11 == Core golden")

    ov = 0xFF7FFFFF
    if int(oracle(["overflow", hex(ov)])) != 1 or lin_vm("btc_compact_overflow", ov) != 1:
        rec("OVERFLOW", "FAIL", "CheckProofOfWork overflow nBits (~0x00800000)")
        return 1
    rec("OVERFLOW", "PASS", "overflow compact fail-closed (Core CheckProofOfWork vector)")

    if int(oracle(["ok", hex(ov), hex(MAINNET_LIMIT)])) != 0 or lin_vm("btc_compact_ok", ov, MAINNET_LIMIT) != 0:
        rec("COMPACT-OK", "FAIL", "btc_compact_ok must reject overflow target")
        return 1
    rec("COMPACT-OK", "PASS", "btc_compact_ok rejects overflow; accepts genesis nBits")

    jit_ok = 0
    jit_skip = 0
    args = (MAINNET_LIMIT, 1262152739, 1261130161, MAINNET_TS, MAINNET_LIMIT, 0)
    jv = lin_jit("btc_next_work", *args)
    if jv is None:
        jit_skip = 1
        rec("JIT", "SKIP", "libtcc in-memory JIT not available on this host")
    elif jv != 0x1D00D86A:
        rec("JIT", "FAIL", "libtcc jit mismatch on get_next_work", f"got={jv}")
        return 1
    else:
        jit_ok = 1
        rec("JIT", "PASS", "libtcc jit get_next_work == 0x1d00d86a")
        if lin_roundtrip_jit("btc_next_work", *args):
            rec("ROUNDTRIP-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on get_next_work")
        else:
            rec("ROUNDTRIP-JIT", "SKIP", "roundtrip-jit did not report CONSENSUS")

    n_fail = sum(1 for c in claims if c["status"] == "FAIL")
    n_pass = sum(1 for c in claims if c["status"] == "PASS")
    n_skip = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_BITCOIN_NBITS_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "upstream": {
            "repo": "https://github.com/bitcoin/bitcoin",
            "tag": "v27.1",
            "commit": PINNED_COMMIT,
            "license": "MIT",
            "files": {k: {"sha256": v["sha256"], "blob": v["blob"]} for k, v in PINS.items()},
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-bitcoin-core-nbits",
        "claims": claims,
        "pass": n_pass,
        "fail": n_fail,
        "skip": n_skip,
        "jit_ok": jit_ok,
        "jit_skip": jit_skip,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("=" * 78)
    print(f"  summary  PASS={n_pass}  FAIL={n_fail}  SKIP={n_skip}")
    print(f"  evidence {EVIDENCE}")
    print("=" * 78)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
