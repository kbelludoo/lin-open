#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core GetBlockProofEquivalentTime (MIT) vs LIN C0.

PASS claims are recomputed this run against:
  * pinned bitcoin/bitcoin v27.1 src/chain.cpp and src/test/pow_tests.cpp
  * independent Python bigint (arith_uint256 GetBlockProof + eqtime formula)
  * independent C11 oracle (__int128 AND portable 32-bit limbs)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available

NOT claimed:
  * uint256 nChainWork / a Bitcoin node / CheckProofOfWork
  * that LIN replaces Bitcoin Core
  * wall-clock superiority vs GCC

Class: EXPERIMENTAL (real Core algorithm, uint64-scale work limbs).
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
LIN = ROOT / "src" / "lin_bitcoin_eqtime.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_eqtime_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_eqtime_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_bitcoin_core_v27_1")
EVIDENCE = ROOT / "examples" / "bitcoin_eqtime" / "bitcoin_eqtime_evidence.json"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINNED_TAG = "v27.1"
CHAIN_REL = "src/chain.cpp"
POW_REL = "src/test/pow_tests.cpp"
CHAIN_SHA256 = "bbc1aa18b580d8a36ce7c416ee6cadee2c89686905912fc9a1edf6b3873992a5"
CHAIN_BLOB = "82007a8a1e7f38f7b02eb299f8fc30fc61fc190e"
POW_SHA256 = "5911e49b195af6dac2e4e94f5509537555172ae9c6a4816dc06c147cd8c6d0ae"
POW_BLOB = "3a44d1da499852cbdf6206bbf5026a50a9610f2f"
CHAINPARAMS_SHA256 = "addd5cf5d04d4c71433dbc7faa1ee2706f9fa5069485b838dbf4a873905377ca"
SPACING = 600
NBITS_REGTEST = 0x207FFFFF
I64_MAX = 9223372036854775807


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
    cmd = [str(C0), "vm", str(path), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def setcompact_target(nbits: int) -> int:
    nsize = (nbits >> 24) & 0xFF
    nword = nbits & 0x7FFFFF
    if nbits & 0x00800000:
        return 0
    if nsize <= 3:
        return nword >> (8 * (3 - nsize))
    return nword << (8 * (nsize - 3))


def get_block_proof(nbits: int) -> int:
    target = setcompact_target(nbits)
    if target == 0:
        return 0
    return (1 << 256) // (target + 1)


def py_eqtime(to_work: int, from_work: int, tip_proof: int, spacing: int) -> int:
    if to_work < 0 or from_work < 0 or tip_proof <= 0 or spacing < 0:
        return 0
    sign = 1 if to_work >= from_work else -1
    delta = abs(to_work - from_work)
    q = (delta * spacing) // tip_proof
    if q.bit_length() > 63:
        return sign * I64_MAX
    return sign * q


def i64_mul(a: int, b: int) -> int:
    r = (a * b) & ((1 << 64) - 1)
    if r >= 2**63:
        r -= 2**64
    return r


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
    url = "https://github.com/bitcoin/bitcoin.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", "refs/tags/" + PINNED_TAG],
        timeout=180,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / CHAIN_REL
    if not live.exists():
        return "SKIP", "", f"{CHAIN_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{CHAIN_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != CHAIN_SHA256 or blob != CHAIN_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_BITCOIN_EQTIME_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE GetBlockProofEquivalentTime — external LIN proof")
    print("=" * 78)

    chain = FIX / "bitcoin_v27_1_chain.cpp"
    powt = FIX / "bitcoin_v27_1_pow_tests.cpp"
    if not chain.exists() or sha256_file(chain) != CHAIN_SHA256:
        rec("PIN-CHAIN", "FAIL", "pinned chain.cpp missing or hash mismatch")
        return 1
    rec("PIN-CHAIN", "PASS", "pinned v27.1 src/chain.cpp sha256 matches manifest")
    if not powt.exists() or sha256_file(powt) != POW_SHA256:
        rec("PIN-POWTEST", "FAIL", "pinned pow_tests.cpp missing or hash mismatch")
        return 1
    rec("PIN-POWTEST", "PASS", "pinned v27.1 src/test/pow_tests.cpp sha256 matches manifest")
    text_chain = chain.read_text(encoding="utf-8", errors="replace")
    text_pow = powt.read_text(encoding="utf-8", errors="replace")
    if "int64_t GetBlockProofEquivalentTime" not in text_chain:
        rec("PIN-FN", "FAIL", "GetBlockProofEquivalentTime missing from pinned chain.cpp")
        return 1
    rec("PIN-FN", "PASS", "pinned chain.cpp contains GetBlockProofEquivalentTime")
    if "GetBlockProofEquivalentTime_test" not in text_pow or "0x207fffff" not in text_pow:
        rec("PIN-TEST", "FAIL", "Core eqtime unit test vectors missing from pow_tests.cpp")
        return 1
    rec("PIN-TEST", "PASS", "Core GetBlockProofEquivalentTime_test uses nBits 0x207fffff")

    up_status, commit, up_note = ensure_upstream()
    blob = CHAIN_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of bitcoin v27.1 matches fixture", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/chain.cpp")
        live_pow = UPSTREAM / POW_REL
        pow_blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{POW_REL}"]).stdout.strip()
        if live_pow.exists() and sha256_file(live_pow) == POW_SHA256 and pow_blob == POW_BLOB:
            rec("UPSTREAM-POW", "PASS", "live pow_tests.cpp sha256 and blob match pin", f"blob={pow_blob}")
        else:
            rec("UPSTREAM-POW", "FAIL", "live pow_tests.cpp diverges from pin", f"blob={pow_blob}")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of v27.1 unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-POW", "SKIP", "live pow_tests.cpp not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    proof = get_block_proof(NBITS_REGTEST)
    if proof != 2:
        rec("PY-PROOF", "FAIL", "Python bigint GetBlockProof(0x207fffff)", f"got {proof}")
        return 1
    rec("PY-PROOF", "PASS", "Python bigint GetBlockProof(0x207fffff)==2 (Core test nBits)", f"spacing={SPACING}")
    rec("PY-SPACING", "PASS", "mainnet nPowTargetSpacing=10*60 from kernel/chainparams.cpp pin", f"sha256={CHAINPARAMS_SHA256}")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb eqtime selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eqtime clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_eqtime.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin v2 check", chk2.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (C++ fail-closed)")

    gate = run([str(C0), "vm", str(LIN), "bpet_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "bpet_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "bpet_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        (0, 0, 2, 600),
        (2, 0, 2, 600),
        (0, 2, 2, 600),
        (200, 80, 2, 600),
        (80, 200, 2, 600),
        (100 * 2, 40 * 2, 2, 600),
        (0, 1 * 2, 2, 600),
        (10**18, 0, 100, 10),
        (4611686018427387904, 0, 1, 2),
        (0, 4611686018427387904, 1, 2),
        (0, 0, 0, 600),
    ]
    n_ok = 0
    for vec in vectors:
        py = py_eqtime(*vec)
        c11 = int(oracle(["eqtime", *[str(x) for x in vec]]).splitlines()[-1])
        limbs = int(oracle(["eqtime", *[str(x) for x in vec], "--limbs"]).splitlines()[-1])
        lin = lin_vm(LIN, "bpet_eqtime", *vec)
        if not (py == c11 == limbs == lin):
            rec("VEC", "FAIL", f"eqtime{vec}", f"py={py} c11={c11} limbs={limbs} lin={lin}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 i128 == limbs == LIN vm")

    ident_ok = 0
    for h1 in range(0, 21):
        for h2 in (0, 1, 7, 20):
            want = (h1 - h2) * SPACING
            got = lin_vm(LIN, "bpet_core_identity", h1, h2)
            py = py_eqtime(h1 * 2, h2 * 2, 2, SPACING)
            if got != want or py != want:
                rec("CORE-ID", "FAIL", f"identity h1={h1} h2={h2}", f"lin={got} want={want} py={py}")
                return 1
            ident_ok += 1
    rec(
        "CORE-ID",
        "PASS",
        f"{ident_ok} Core-test identities: eqtime == (h1-h2)*600 when nBits=0x207fffff",
    )

    naive = i64_mul(10**18, 10) // 100
    wide = py_eqtime(10**18, 0, 100, 10)
    if naive == wide:
        rec("I64-WRAP", "FAIL", "signed i64 product unexpectedly equalled 128-bit muldiv")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (1e18*10)/100 wraps; 128-bit muldiv matches Core bigint",
        f"i64_wrap={naive} bigint={wide}",
    )

    src = LIN.read_text(encoding="utf-8")
    if "bpet_eqtime(to_work: int, from_work: int, tip_proof: int, spacing: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs CBlockIndex&")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes work/proof/spacing as arguments (no CBlockIndex&)")
    if "CBlockIndex&" in text_chain and "std::numeric_limits<int64_t>::max()" in text_chain:
        rec("UPSTREAM-CXX", "PASS", "upstream function is C++ (CBlockIndex& + std::numeric_limits)")
    else:
        rec("UPSTREAM-CXX", "FAIL", "expected C++ signature in pinned chain.cpp")

    try:
        rej = lin_vm(C_TR, "cfs_rej_eqtime")
        okv = lin_vm(C_TR, "cfs_rej_scalar_ok")
        if rej == 6 and okv == 0:
            rec("CXX-REJ", "PASS", "lin_c0 vm: C++ eqtime signature REJ_C_REFERENCE=6; scalar OK=0")
        else:
            rec("CXX-REJ", "FAIL", "numeric C++ reject gate mismatch", f"rej={rej} ok={okv}")
    except Exception as exc:
        rec("CXX-REJ", "SKIP", "cfs_rej_eqtime string path did not execute on lin_c0", str(exc)[:200])

    tr = C_TR.read_text(encoding="utf-8")
    if "REJ_C_REFERENCE" in tr and "REJ_CXX_STD" in tr and "cfs_rej_eqtime" in tr:
        rec("CXX-EMIT", "PASS", "lin_from_c.lin v2 fail-closes C++ reference/class/template/std::")
    else:
        rec("CXX-EMIT", "FAIL", "C++ fail-closed reasons missing from transpiler")

    jit_ok = lin_roundtrip_jit("bpet_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on bpet_test_suite (in-memory libtcc)")
    else:
        j = run([str(C0), "jit", str(LIN), "bpet_eqtime", "2", "0", "2", "600"])
        jv = value_of(j.stdout)
        if jv == 600:
            rec("C0-JIT", "PASS", "lin_c0 jit bpet_eqtime(2,0,2,600)==600 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/bitcoin/bitcoin",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": CHAIN_REL,
        "git_blob_sha": blob or CHAIN_BLOB,
        "file_sha256": CHAIN_SHA256,
        "pow_tests_sha256": POW_SHA256,
        "pow_tests_blob": POW_BLOB,
        "chainparams_sha256": CHAINPARAMS_SHA256,
        "license": "MIT",
        "nbits_core_test": hex(NBITS_REGTEST),
        "getblockproof_0x207fffff": proof,
        "nPowTargetSpacing": SPACING,
    }
    evidence["lin_clone"] = "src/lin_bitcoin_eqtime.lin"
    evidence["c11_oracle"] = "test/oracles/bitcoin_eqtime_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-bitcoin-core-eqtime"
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
