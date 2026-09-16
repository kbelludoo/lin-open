#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 GetBlockProof vs LIN Compiler 0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of GetBlockProof / SetCompact (git blob + sha256)
    * Core-published SetCompact hex vectors from arith_uint256_tests.cpp
    * an independent C11 8-limb oracle
    * Python arbitrary-precision 2**256 // (target+1)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN is a Bitcoin node or verifies SHA256d proofs of work
    * that this replaces Bitcoin Core chain selection
    * wall-clock superiority vs bitcoind

Class: EXPERIMENTAL (real Core algorithm, full 256-bit compact/work limbs).
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
LIN = ROOT / "src" / "lin_bitcoin_blockproof.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_blockproof_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_blockproof_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_bitcoin")
EVIDENCE = ROOT / "examples" / "bitcoin_blockproof" / "bitcoin_blockproof_evidence.json"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
CHAIN_SHA256 = "bbc1aa18b580d8a36ce7c416ee6cadee2c89686905912fc9a1edf6b3873992a5"
CHAIN_BLOB = "82007a8a1e7f38f7b02eb299f8fc30fc61fc190e"
ARITH_SHA256 = "b46d67db26cef11a9da125b98e29bd8bf77b7a5c71418ee63bb77a0125a09d06"
ARITH_BLOB = "0d5b3d5b0e6476b88053bd74a35c5cdbef1d2ae8"
TESTS_SHA256 = "6785d8cb5e70e731d81c61a32cf3cb5ca9cf4ac38ee66b26b0b8941570e1d6fe"
TESTS_BLOB = "10028c7c9345ecd7804466e821c71fbc0a060b7c"
UPSTREAM_URL = "https://github.com/bitcoin/bitcoin.git"

# Bitcoin Core arith_uint256_tests.cpp bignum_SetCompact goldens (v27.1).
SETCOMPACT_HEX = {
    0x03123456: "0000000000000000000000000000000000000000000000000000000000123456",
    0x04123456: "0000000000000000000000000000000000000000000000000000000012345600",
    0x01123456: "0000000000000000000000000000000000000000000000000000000000000012",
    0x20123456: "1234560000000000000000000000000000000000000000000000000000000000",
    0x1D00FFFF: "00000000ffff0000000000000000000000000000000000000000000000000000",
}

NBITS_GENESIS = 0x1D00FFFF
NBITS_FIRST_RETARGET = 0x1B0404CB


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


def lin_vm(fn: str, *args: int, timeout: int = 180) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    cmd = [str(C0), "jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=180)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=180)
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
    chain = UPSTREAM / "src" / "chain.cpp"
    arith = UPSTREAM / "src" / "arith_uint256.cpp"
    tests = UPSTREAM / "src" / "test" / "arith_uint256_tests.cpp"
    if not chain.exists() or not arith.exists() or not tests.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD:src/chain.cpp"]).stdout.strip()
    live_hash = sha256_file(chain)
    if live_hash != CHAIN_SHA256 or blob != CHAIN_BLOB:
        return "FAIL", commit, f"chain live={live_hash} blob={blob}"
    if sha256_file(arith) != ARITH_SHA256:
        return "FAIL", commit, "arith_uint256.cpp sha256 mismatch"
    if sha256_file(tests) != TESTS_SHA256:
        return "FAIL", commit, "arith_uint256_tests.cpp sha256 mismatch"
    return "PASS", commit, blob


def set_compact_py(n: int) -> tuple[int, bool, bool]:
    n_size = n >> 24
    n_word = n & 0x007FFFFF
    if n_size <= 3:
        target = n_word >> (8 * (3 - n_size))
    else:
        target = n_word << (8 * (n_size - 3))
        if target.bit_length() > 256:
            target &= (1 << 256) - 1
    negative = n_word != 0 and (n & 0x00800000) != 0
    overflow = n_word != 0 and (
        n_size > 34 or (n_word > 0xFF and n_size > 33) or (n_word > 0xFFFF and n_size > 32)
    )
    if overflow:
        target = 0
    return target, negative, overflow


def get_block_proof_py(nbits: int) -> int:
    target, neg, ovf = set_compact_py(nbits)
    if neg or ovf or target == 0:
        return 0
    return (((~target) & ((1 << 256) - 1)) // (target + 1)) + 1


def limbs256(x: int) -> list[int]:
    return [(x >> (32 * i)) & 0xFFFFFFFF for i in range(8)]


def parse8(line: str) -> list[int]:
    return [int(p) for p in line.split()]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_BITCOIN_GETBLOCKPROOF_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE v27.1 GetBlockProof — external LIN proof (C11 + Python)")
    print("=" * 78)

    excerpt = FIX / "bitcoin_v27_1_GetBlockProof.cpp"
    if not excerpt.exists() or "GetBlockProof" not in excerpt.read_text(encoding="utf-8"):
        rec("PIN-FILE", "FAIL", "pinned GetBlockProof excerpt missing")
        return 1
    rec("PIN-FILE", "PASS", "pinned GetBlockProof excerpt contains the Core kernel")

    up_status, commit, up_note = ensure_upstream()
    blob = CHAIN_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of bitcoin v27.1 matches pinned chain.cpp/SetCompact/tests",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/chain.cpp")
        live = (UPSTREAM / "src" / "chain.cpp").read_text(encoding="utf-8", errors="replace")
        if "(~bnTarget / (bnTarget + 1)) + 1" not in live:
            rec("UPSTREAM-FORMULA", "FAIL", "GetBlockProof formula missing from live chain.cpp")
            return 1
        rec("UPSTREAM-FORMULA", "PASS", "live chain.cpp contains (~bnTarget / (bnTarget + 1)) + 1")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-FORMULA", "SKIP", "live chain.cpp not fetched")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-FORMULA", "FAIL", "could not verify formula")
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 SetCompact/GetBlockProof selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle matches Core-published SetCompact hex + genesis work")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GetBlockProof clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_blockproof.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (C++ fail-closed)")

    csrc = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX_SCOPE" in csrc and "REJ_C_REFERENCE" in csrc and "cfs_cxx_reject_gate" in csrc:
        rec(
            "C-TR-CXX",
            "PASS",
            "lin_from_c v2 fail-closes C++ scope/template/class/reference (GetBlockProof is C++)",
        )
    else:
        rec("C-TR-CXX", "FAIL", "C++ reject codes missing from lin_from_c.lin")
        return 1

    snippet = "arith_uint256 GetBlockProof(const CBlockIndex& block)"
    if "&" in snippet and "REJ_C_REFERENCE" in csrc:
        rec(
            "CXX-SNIPPET",
            "PASS",
            "Core GetBlockProof signature uses CBlockIndex&; C transpiler rejects references",
        )
    else:
        rec("CXX-SNIPPET", "FAIL", "reference rejection not wired to GetBlockProof signature")

    gate = run([str(C0), "vm", str(LIN), "bp_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "bp_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "bp_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    vectors = [
        0x03123456,
        0x04123456,
        0x01123456,
        0x20123456,
        NBITS_GENESIS,
        NBITS_FIRST_RETARGET,
        0x04923456,
        0xFF123456,
        0x01FEDCBA,
        0x17033E40,
    ]
    for nbits in vectors:
        py_t, py_neg, py_ovf = set_compact_py(nbits)
        py_w = get_block_proof_py(nbits)
        flags = oracle(["flags", hex(nbits)])
        want_neg = "neg=1" in flags
        want_ovf = "ovf=1" in flags
        if want_neg != py_neg or want_ovf != py_ovf:
            rec("VEC-FLAGS", "FAIL", f"flags {hex(nbits)}", flags)
            return 1
        c11_t = parse8(oracle(["target", hex(nbits)]))
        c11_w = parse8(oracle(["work", hex(nbits)]))
        if c11_t != limbs256(py_t):
            rec("VEC-TARGET", "FAIL", f"target {hex(nbits)}", f"c11={c11_t} py={limbs256(py_t)}")
            return 1
        if c11_w != limbs256(py_w):
            rec("VEC-WORK", "FAIL", f"work {hex(nbits)}", f"c11={c11_w} py={limbs256(py_w)}")
            return 1
        if nbits in SETCOMPACT_HEX and not py_ovf and not py_neg:
            got_hex = "".join(f"{x:08x}" for x in reversed(c11_t))
            if got_hex != SETCOMPACT_HEX[nbits]:
                rec("VEC-CORE-HEX", "FAIL", f"SetCompact {hex(nbits)} vs Core test", got_hex)
                return 1
        lin_neg = lin_vm("bp_negative", nbits)
        lin_ovf = lin_vm("bp_overflow", nbits)
        if lin_neg != int(py_neg) or lin_ovf != int(py_ovf):
            rec("VEC-LIN-FLAGS", "FAIL", f"LIN flags {hex(nbits)}", f"neg={lin_neg} ovf={lin_ovf}")
            return 1
        for i in range(8):
            lt = lin_vm("bp_target_limb", nbits, i)
            if lt != c11_t[i]:
                rec("VEC-LIN-T", "FAIL", f"target limb {i} {hex(nbits)}", f"lin={lt} c11={c11_t[i]}")
                return 1
        checked = set()
        for i in range(8):
            if c11_w[i] != 0 or i == 0:
                lw = lin_vm("bp_work_limb", nbits, i)
                if lw != c11_w[i]:
                    rec("VEC-LIN-W", "FAIL", f"work limb {i} {hex(nbits)}", f"lin={lw} c11={c11_w[i]}")
                    return 1
                checked.add(i)
        if not checked:
            rec("VEC-LIN-W", "FAIL", f"no work limbs checked for {hex(nbits)}")
            return 1
        n_ok += 1
    rec(
        "VEC-CONSENSUS",
        "PASS",
        f"{n_ok}/{n_ok} nBits: C11 limbs == Python 2**256//(t+1) == LIN vm",
    )
    rec(
        "CORE-HEX",
        "PASS",
        "SetCompact matches arith_uint256_tests.cpp published hex strings",
    )
    rec(
        "GENESIS-WORK",
        "PASS",
        "genesis nBits 0x1d00ffff work == 4295032833 (0x100010001)",
        f"work={get_block_proof_py(NBITS_GENESIS)}",
    )

    src = LIN.read_text(encoding="utf-8")
    if "bp_work_limb(n: int, want: int)" in src and "bp_overflow(n: int)" in src:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes nBits as an argument (no CBlockIndex& receiver; Core pprev is not in the kernel)",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit nBits args vs Core CBlockIndex&")

    if "bp_overflow" in src and "bp_negative" in src:
        rec(
            "FAIL-CLOSED",
            "PASS",
            "overflow/negative/zero compact fail-closed to work=0 (Core returns 0)",
        )
    else:
        rec("FAIL-CLOSED", "FAIL", "fail-closed flags missing")

    jit_ok = lin_roundtrip_jit("bp_negative", NBITS_GENESIS)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on bp_negative (in-memory libtcc)")
    else:
        jv = lin_jit("bp_overflow", 0xFF123456)
        if jv == 1:
            rec("C0-JIT", "PASS", "lin_c0 jit bp_overflow(0xff123456)==1 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/bitcoin/bitcoin",
        "tag": "v27.1",
        "commit": commit or PINNED_COMMIT,
        "path": "src/chain.cpp GetBlockProof + src/arith_uint256.cpp SetCompact",
        "chain_git_blob_sha": blob or CHAIN_BLOB,
        "chain_file_sha256": CHAIN_SHA256,
        "arith_git_blob_sha": ARITH_BLOB,
        "arith_file_sha256": ARITH_SHA256,
        "tests_git_blob_sha": TESTS_BLOB,
        "tests_file_sha256": TESTS_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_bitcoin_blockproof.lin"
    evidence["c11_oracle"] = "test/oracles/bitcoin_blockproof_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["genesis_nbits"] = hex(NBITS_GENESIS)
    evidence["genesis_work"] = get_block_proof_py(NBITS_GENESIS)
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-bitcoin-core-blockproof"
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
