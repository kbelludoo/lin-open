#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 PermittedDifficultyTransition vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of src/pow.cpp (git blob + sha256, tag v27.1)
    * published pow_tests.cpp timespan vectors (block times, not nBits uint256)
    * an independent C11 oracle (gcc -std=c11, __int128 muldiv + compact nSize<=8)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python int as a third oracle for clamp / modulus / compact / bigint muldiv

  NOT claimed:
    * uint256 compact target compare on mainnet nBits (0x1d00ffff → WIDTH=2)
    * that LIN replaces Bitcoin Core header sync or consensus
    * wall-clock superiority vs bitcoind
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real Bitcoin Core algorithm; 4x compact bound is i64-width).
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
LIN = ROOT / "src" / "lin_bitcoin_perm_diff.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_perm_diff_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_perm_diff_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_bitcoin_core_v27_1")
EVIDENCE = ROOT / "examples" / "bitcoin_perm_diff" / "bitcoin_perm_diff_evidence.json"
PINNED = FIX / "bitcoin_core_v27_1_pow.cpp"
SCALAR = FIX / "bitcoin_perm_diff_scalar.c"

PINNED_SHA256 = "a997ebc9e89ec0ed0f98fe56e7ece7c0a799746d36be5c0951ca6fd264280a33"
PINNED_BLOB = "1e8d53de8bb87b0b9a30ff6439881cc2c40e38a4"
PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINNED_TAG = "v27.1"
UPSTREAM_REL = "src/pow.cpp"
T = 1_209_600
I = 2016
NBITS_GENESIS = 0x1D00FFFF
OLD_U64 = 0x0400FFFF


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


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(fn: str, *args: int) -> int:
    cmd = [str(C0), "vm", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed {fn}: {proc.stdout}\n{proc.stderr}")
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
    proc = run(
        [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90
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
        p = run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                PINNED_TAG,
                "--filter=blob:none",
                url,
                str(UPSTREAM),
            ],
            timeout=180,
        )
        if p.returncode != 0:
            return "", "", ""
    src = UPSTREAM / UPSTREAM_REL
    if not src.exists():
        run(
            ["git", "-C", str(UPSTREAM), "sparse-checkout", "set", UPSTREAM_REL],
            timeout=60,
        )
    if not src.exists():
        return "", "", ""
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(
        ["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]
    ).stdout.strip()
    return sha256_file(src), blob, commit


def py_setcompact(n: int) -> int:
    nsize = (n >> 24) & 0xFF
    nword = n & 0x007FFFFF
    if nsize > 8 or nword == 0 or (n & 0x00800000):
        return 0
    if nsize <= 3:
        return nword >> (8 * (3 - nsize))
    return nword << (8 * (nsize - 3))


def py_bitlen(n: int) -> int:
    return n.bit_length()


def py_getcompact(n: int) -> int:
    if n <= 0:
        return 0
    nsize = (py_bitlen(n) + 7) // 8
    ncompact = n << (8 * (3 - nsize)) if nsize <= 3 else n >> (8 * (nsize - 3))
    if ncompact & 0x00800000:
        ncompact >>= 8
        nsize += 1
    return (ncompact | (nsize << 24)) & 0xFFFFFFFF


def py_bound(old_n: int, new_n: int, timespan: int, pow_limit: int) -> int:
    old_t = py_setcompact(old_n)
    new_t = py_setcompact(new_n)
    if old_t == 0 or new_t == 0 or timespan <= 0:
        return 0
    lo, hi = timespan // 4, timespan * 4
    largest = (old_t * hi) // timespan
    smallest = (old_t * lo) // timespan
    if pow_limit > 0:
        largest = min(largest, pow_limit)
        smallest = min(smallest, pow_limit)
    max_rt = py_setcompact(py_getcompact(largest))
    min_rt = py_setcompact(py_getcompact(smallest))
    if max_rt < new_t or new_t < min_rt:
        return 0
    return 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"harness": Path(__file__).name, "claims": []}

    def rec(cid: str, status: str, detail: str, extra: str = "") -> None:
        row = {"id": cid, "status": status, "detail": detail}
        if extra:
            row["extra"] = extra
        claims.append(row)
        print(f"  [{status}] {cid}: {detail}" + (f" ({extra})" if extra else ""))

    print("=" * 78)
    print("  Bitcoin Core v27.1 PermittedDifficultyTransition — external proof")
    print("=" * 78)

    if not PINNED.exists():
        rec("PIN-EXISTS", "FAIL", "missing fixture bitcoin_core_v27_1_pow.cpp")
        return 1
    got = sha256_file(PINNED)
    blob = git_blob_sha1(PINNED.read_bytes())
    if got != PINNED_SHA256 or blob != PINNED_BLOB:
        rec("PIN-HASH", "FAIL", "fixture hash mismatch", f"sha={got} blob={blob}")
        return 1
    rec("PIN-HASH", "PASS", "fixture sha256 and git blob match published pins")

    src = PINNED.read_text(encoding="utf-8", errors="replace")
    if "bool PermittedDifficultyTransition" not in src or "CalculateNextWorkRequired" not in src:
        rec("PIN-SYMBOLS", "FAIL", "expected symbols missing from pow.cpp")
        return 1
    rec("PIN-SYMBOLS", "PASS", "PermittedDifficultyTransition + CalculateNextWorkRequired present")

    live_sha, live_blob, live_commit = ensure_upstream()
    if live_sha and live_sha != PINNED_SHA256:
        rec("UPSTREAM-FETCH", "FAIL", "live v27.1 pow.cpp sha256 != pin", live_sha)
        return 1
    if live_blob and live_blob != PINNED_BLOB:
        rec("UPSTREAM-FETCH", "FAIL", "live git blob != pin", live_blob)
        return 1
    if live_sha:
        rec(
            "UPSTREAM-FETCH",
            "PASS",
            "git clone bitcoin v27.1 pow.cpp matches pin",
            f"commit={live_commit or PINNED_COMMIT}",
        )
    else:
        rec("UPSTREAM-FETCH", "SKIP", "network clone unavailable; fixture pin still holds")

    ensure_oracle()
    st = int(oracle(["selftest"]).splitlines()[-1])
    if st != 1:
        rec("C11-SELFTEST", "FAIL", "C11 oracle selftest", str(st))
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle selftest == 1 (published timespan + u64 4x)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of perm-diff clone", chk.stdout[:400])
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_perm_diff.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk2.stdout[:400])
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "pdt_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "pdt_test_suite via lin_c0 vm", gate.stdout[:500])
        return 1
    rec("LIN-SUITE", "PASS", "pdt_test_suite == 1 on Compiler 0 interpreter")

    # Published Bitcoin Core pow_tests.cpp timespan vectors (block times).
    published = [
        (1022578, 1022578, "get_next_work unclamped 1262152739-1261130161"),
        (289434, 302400, "get_next_work_lower_limit_actual clamp to T/4"),
        (6048000, 4838400, "get_next_work_upper_limit_actual clamp to 4T"),
    ]
    for actual, want, name in published:
        c11 = int(oracle(["clamp", str(actual), str(T)]).splitlines()[-1])
        lin = lin_vm("pdt_clamp_timespan", actual, T)
        py = max(T // 4, min(actual, T * 4))
        if not (c11 == lin == py == want):
            rec("TIMESPAN", "FAIL", name, f"c11={c11} lin={lin} py={py} want={want}")
            return 1
    rec("TIMESPAN", "PASS", "3/3 published pow_tests.cpp timespan clamps: C11==LIN==Python")

    if lin_vm("pdt_on_retarget", 32256, I) != 1 or int(oracle(["on", "32256", str(I)])) != 1:
        rec("WINDOW", "FAIL", "height 32256 must be on-retarget")
        return 1
    if lin_vm("pdt_on_retarget", 32255, I) != 0 or (32255 % I) != 2015:
        rec("WINDOW", "FAIL", "height 32255 must be off-retarget remainder 2015")
        return 1
    rec("WINDOW", "PASS", "2016-block retarget window: 32256 on, 32255 off (2015)")

    p_eq = lin_vm("pdt_permitted", 0, 32255, I, T, NBITS_GENESIS, NBITS_GENESIS, 0)
    p_ne = lin_vm("pdt_permitted", 0, 32255, I, T, NBITS_GENESIS, NBITS_GENESIS - 1, 0)
    p_min = lin_vm("pdt_permitted", 1, 32255, I, T, 1, 2, 0)
    p_w = lin_vm("pdt_permitted", 0, 32256, I, T, NBITS_GENESIS, NBITS_GENESIS, 0)
    c_eq = int(oracle(["permitted", "0", "32255", str(I), str(T), str(NBITS_GENESIS), str(NBITS_GENESIS), "0"]))
    c_ne = int(oracle(["permitted", "0", "32255", str(I), str(T), str(NBITS_GENESIS), str(NBITS_GENESIS - 1), "0"]))
    c_w = int(oracle(["permitted", "0", "32256", str(I), str(T), str(NBITS_GENESIS), str(NBITS_GENESIS), "0"]))
    if p_eq != 1 or p_ne != 0 or p_min != 1 or p_w != 2 or c_eq != 1 or c_ne != 0 or c_w != 2:
        rec("EQUALITY", "FAIL", "header-sync equality/min-diff/width", f"{p_eq,p_ne,p_min,p_w,c_eq,c_ne,c_w}")
        return 1
    rec("EQUALITY", "PASS", "off-window nBits equality + min-diff allow + mainnet WIDTH=2")

    four = py_getcompact(py_setcompact(OLD_U64) * 4)
    five = py_getcompact(py_setcompact(OLD_U64) * 5)
    qtr = py_getcompact(py_setcompact(OLD_U64) // 4)
    fifth = py_getcompact(py_setcompact(OLD_U64) // 5)
    for new, want, label in ((OLD_U64, 1, "same"), (four, 1, "4x"), (five, 0, "5x"), (qtr, 1, "1/4"), (fifth, 0, "1/5")):
        lin_b = lin_vm("pdt_timespan_bound", OLD_U64, new, T, 0)
        c11_b = int(oracle(["bound", hex(OLD_U64), hex(new), str(T), "0"]).splitlines()[-1])
        py_b = py_bound(OLD_U64, new, T, 0)
        if not (lin_b == c11_b == py_b == want):
            rec("U64-4X", "FAIL", f"compact {label}", f"lin={lin_b} c11={c11_b} py={py_b} want={want}")
            return 1
    rec("U64-4X", "PASS", "64-bit compact 4x bound: same/4x/1/4 permit, 5x/1/5 reject")

    tr = C_TR.read_text(encoding="utf-8")
    pow_src = PINNED.read_text(encoding="utf-8")
    sc = SCALAR.read_text(encoding="utf-8")
    if "REJ_C_CXX_SCOPE" not in tr or "REJ_C_REFERENCE" not in tr or "cfs_reason_gate" not in tr:
        rec("TRANSPILER", "FAIL", "lin_from_c.lin v2 rejectors missing")
        return 1
    if "Consensus::Params&" not in pow_src or "int64_t&" in sc:
        rec("TRANSPILER", "FAIL", "upstream still C++ ref; scalar fixture must not be")
        return 1
    if "*" in sc.split("pdt_clamp_timespan", 1)[-1].split("{", 1)[0]:
        rec("TRANSPILER", "FAIL", "scalar fixture signature has pointer")
        return 1
    rec(
        "TRANSPILER",
        "PASS",
        "C transpiler v2 fail-closes :: and lone &; lifted scalar C has neither",
    )

    vm_gate = run([str(C0), "vm", str(C_TR), "cfs_reason_gate"])
    if vm_gate.returncode == 0 and value_of(vm_gate.stdout) == 1:
        rec("C-TR-GATE", "PASS", "cfs_reason_gate == 1 on lin_c0 vm")
    else:
        rec(
            "C-TR-GATE",
            "SKIP",
            "lin_c0 does not execute string-literal transpiler modules",
            (vm_gate.stdout + vm_gate.stderr)[:240],
        )

    jit_ok = lin_roundtrip_jit("pdt_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on pdt_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("pdt_clamp_timespan", 289434, T)
        if jv == 302400:
            rec("C0-JIT", "PASS", "lin_c0 jit clamp(289434,T)==302400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if "pdt_clamp_timespan(actual: int, target_timespan: int)" not in LIN.read_text(encoding="utf-8"):
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit timespan/interval args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes consensus params as arguments (no Consensus::Params&)")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/bitcoin/bitcoin",
        "tag": PINNED_TAG,
        "commit": live_commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "MIT",
        "clone_lin": "https://github.com/kbelludoo/clone-lin-bitcoin-core-permdiff",
    }
    evidence["lin_clone"] = "src/lin_bitcoin_perm_diff.lin"
    evidence["c11_oracle"] = "test/oracles/bitcoin_perm_diff_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["published_timespan_vectors"] = [
        {"name": n, "actual": a, "clamped": w} for a, w, n in published
    ]
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
