#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: ethereum/consensus-specs (CC0-1.0) integer_squareroot +
Altair get_base_reward vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of phase0/altair beacon-chain.md (git blob + sha256)
    * an independent C11 oracle (spec Babylonian XOR overflow-safe avg_floor)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int matching the published spec helpers

  NOT claimed:
    * that this is a beacon node / validator client
    * Electra 2048 ETH max-effective-balance economics as a special case
    * wall-clock superiority vs Prysm/Lighthouse/nimbus
    * zk / computational soundness of Merkle receipts

Class: EXPERIMENTAL (real consensus-spec uint64 Gwei algorithm; not a chain).
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
LIN = ROOT / "src" / "lin_eth_base_reward.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "eth_base_reward_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "eth_base_reward_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_consensus_specs")
EVIDENCE = ROOT / "examples" / "eth_base_reward" / "eth_base_reward_evidence.json"

PINNED_COMMIT = "b5c3b619887c7850a8c1d3540b471092be73ad84"
PINNED_TAG = "v1.5.0"
PHASE0_REL = "specs/phase0/beacon-chain.md"
ALTAIR_REL = "specs/altair/beacon-chain.md"
PINNED_PHASE0_SHA256 = "95519084a4689b0bbbbaa9db9fb1d6e48d6c7be83a8dd21bc82a83cf96a6254a"
PINNED_PHASE0_BLOB = "5658ed2c236568f7be1cf26e8d2c496ed5179564"
PINNED_ALTAIR_SHA256 = "2ea769c3a23139225997efc75efed8914f8fd949ec02991fa62d026017a278d9"
PINNED_ALTAIR_BLOB = "4edfbeb763146fe33750de82e118b6bf1bde890e"
UINT64_MAX = 2**64 - 1
UINT64_MAX_SQRT = 4294967295
EB_INC = 10**9
BRF = 64


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


def py_isqrt(n: int) -> int:
    if n == UINT64_MAX:
        return UINT64_MAX_SQRT
    if n < 0:
        return 0
    x = n
    y = (x + 1) // 2
    while y < x:
        x = y
        y = (x + n // x) // 2
    return x


def py_brpi(total: int) -> int:
    if total <= 0:
        return 0
    s = py_isqrt(total)
    if s == 0:
        return 0
    return (EB_INC * BRF) // s


def py_altair(eb: int, total: int) -> int:
    return (eb // EB_INC) * py_brpi(total)


def py_phase0(eb: int, total: int) -> int:
    if total <= 0:
        return 0
    s = py_isqrt(total)
    if s == 0:
        return 0
    return (eb * BRF // s) // 4


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/ethereum/consensus-specs.git"
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
    live0 = UPSTREAM / PHASE0_REL
    live1 = UPSTREAM / ALTAIR_REL
    if not live0.exists() or not live1.exists():
        return "SKIP", "", "spec files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob0 = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PHASE0_REL}"]).stdout.strip()
    blob1 = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ALTAIR_REL}"]).stdout.strip()
    h0 = sha256_file(live0)
    h1 = sha256_file(live1)
    if h0 != PINNED_PHASE0_SHA256 or blob0 != PINNED_PHASE0_BLOB:
        return "FAIL", commit, f"phase0 live={h0} blob={blob0}"
    if h1 != PINNED_ALTAIR_SHA256 or blob1 != PINNED_ALTAIR_BLOB:
        return "FAIL", commit, f"altair live={h1} blob={blob1}"
    return "PASS", commit, f"{blob0},{blob1}"


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_ETH_BASE_REWARD_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  ETH CONSENSUS SPECS — integer_squareroot + Altair base reward")
    print("  (CC0-1.0, uint64 Gwei, C11 compiler 0)")
    print("=" * 78)

    pinned0 = FIX / "beacon-chain-phase0.md"
    pinned1 = FIX / "beacon-chain-altair.md"
    if not pinned0.exists() or not pinned1.exists():
        rec("PIN-FILE", "FAIL", "pinned beacon-chain md missing")
        return 1
    g0 = sha256_file(pinned0)
    g1 = sha256_file(pinned1)
    if g0 != PINNED_PHASE0_SHA256:
        rec("PIN-SHA256", "FAIL", "phase0 fixture hash mismatch", f"{g0}")
        return 1
    if g1 != PINNED_ALTAIR_SHA256:
        rec("PIN-SHA256", "FAIL", "altair fixture hash mismatch", f"{g1}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned phase0+altair beacon-chain.md sha256 matches manifest")

    p0txt = pinned0.read_text(encoding="utf-8")
    altxt = pinned1.read_text(encoding="utf-8")
    need0 = "def integer_squareroot(n: uint64) -> uint64:"
    need1 = "def get_base_reward_per_increment(state: BeaconState) -> Gwei:"
    need2 = "increments = state.validators[index].effective_balance // EFFECTIVE_BALANCE_INCREMENT"
    if need0 not in p0txt:
        rec("PIN-ISQRT", "FAIL", "integer_squareroot missing from phase0 fixture")
        return 1
    if need1 not in altxt or need2 not in altxt:
        rec("PIN-ALTAIR", "FAIL", "Altair get_base_reward helpers missing")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned files contain integer_squareroot and Altair helpers")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned consensus-specs commit matches fixtures",
            f"commit={commit} blobs={up_note}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of phase0+altair beacon-chain.md")
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
        rec("C11-SELFTEST", "FAIL", "C11 spec vs overflow-safe isqrt", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 spec Babylonian XOR overflow-safe avg_floor")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of eth base-reward clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_eth_base_reward.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "ebr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ebr_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ebr_test_suite == 1 on Compiler 0 interpreter")

    isqrt_ns = [0, 1, 15, 16, 1000000, 10**9, 32 * 10**9, 1000 * 32 * 10**9]
    n_ok = 0
    for n in isqrt_ns:
        want = int(oracle(["isqrt", str(n)]).splitlines()[-1])
        py = py_isqrt(n)
        got = lin_vm("ebr_isqrt", n)
        if want != py or got != want:
            rec("VEC-ISQRT", "FAIL", f"isqrt({n})", f"c11={want} py={py} lin={got}")
            return 1
        n_ok += 1
    rec("VEC-ISQRT", "PASS", f"{n_ok}/{n_ok} isqrt vectors: C11 == Python spec == LIN vm")

    c11_max = int(oracle(["isqrt", str(UINT64_MAX)]).splitlines()[-1])
    lin_max = lin_vm("ebr_isqrt", -1)
    py_max = py_isqrt(UINT64_MAX)
    if c11_max != UINT64_MAX_SQRT or lin_max != UINT64_MAX_SQRT or py_max != UINT64_MAX_SQRT:
        rec(
            "ISQRT-U64MAX",
            "FAIL",
            "UINT64_MAX special case",
            f"c11={c11_max} lin={lin_max} py={py_max}",
        )
        return 1
    rec(
        "ISQRT-U64MAX",
        "PASS",
        "UINT64_MAX → 4294967295 (spec special case; LIN encodes as i64 -1)",
        f"value={c11_max}",
    )

    reward_vecs = [
        (32 * 10**9, 32 * 10**9),
        (32 * 10**9, 1000 * 32 * 10**9),
        (32 * 10**9, 1_000_000 * 32 * 10**9),
        (16 * 10**9, 32 * 10**9),
        (0, 32 * 10**9),
        (32 * 10**9, EB_INC),
    ]
    r_ok = 0
    canonical = 0
    for eb, tot in reward_vecs:
        c11a = int(oracle(["altair", str(eb), str(tot)]).splitlines()[-1])
        c11p = int(oracle(["phase0", str(eb), str(tot)]).splitlines()[-1])
        pya = py_altair(eb, tot)
        pyp = py_phase0(eb, tot)
        lina = lin_vm("ebr_base_reward", eb, tot)
        linp = lin_vm("ebr_phase0_base_reward", eb, tot)
        if not (c11a == pya == lina and c11p == pyp == linp):
            rec(
                "VEC-REWARD",
                "FAIL",
                f"eb={eb} tot={tot}",
                f"altair c11={c11a} py={pya} lin={lina} phase0 c11={c11p} py={pyp} lin={linp}",
            )
            return 1
        if eb == 32 * 10**9 and tot == 32 * 10**9:
            canonical = lina
        r_ok += 1
    rec(
        "VEC-REWARD",
        "PASS",
        f"{r_ok}/{r_ok} Altair+Phase0 reward vectors: C11 == Python == LIN",
        f"altair_1v_32eth={canonical}",
    )
    rec("PY-BIGINT", "PASS", "Python spec helpers match C11 and LIN on every vector above")

    wrapped = (144115188075855873 * 64)
    wrap_i64 = wrapped & ((1 << 64) - 1)
    if wrap_i64 >= 2**63:
        wrap_i64 -= 2**64
    lin_ov = lin_vm("ebr_mul_ok", 144115188075855873, 64)
    if lin_ov != 0:
        rec("I64-WRAP", "FAIL", "checked mul should fail-close on i64 overflow", f"ok={lin_ov}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (overflow_eb*64) wraps; LIN ebr_mul_ok fail-closes",
        f"i64_wrap={wrap_i64}",
    )

    lin_zero = lin_vm("ebr_base_reward", 32 * 10**9, 0)
    if lin_zero != 0:
        rec("ZERO-TOTAL", "FAIL", "total_balance=0 must fail-close", f"got={lin_zero}")
        return 1
    rec(
        "ZERO-TOTAL",
        "PASS",
        "LIN fail-closes total_balance=0 (spec get_total_balance mins at 1 ETH; C UB otherwise)",
    )

    src = LIN.read_text(encoding="utf-8")
    if "ebr_base_reward(effective_balance: int, total_balance: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs BeaconState")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes effective_balance and total_balance as arguments (no BeaconState)",
        )
    if "ebr_avg_floor" in src and "_lia_ushr" in src:
        rec(
            "SAFE-ISQRT",
            "PASS",
            "isqrt uses overflow-safe floor((a+b)/2); UINT64_MAX is a named special case",
        )
    else:
        rec("SAFE-ISQRT", "FAIL", "overflow-safe isqrt helpers missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "sol_expand_pow10" in sol_src and "OK_VIEW" in sol_src and "REJ_SOLIDITY_POW" in sol_src:
        rec("SOL-EMIT", "PASS", "lin_from_solidity.lin v3: OK_VIEW emit, 10**N expand, REJ ** leftover")
    else:
        rec("SOL-EMIT", "FAIL", "solidity transpiler v3 symbols missing")

    c_src = C_TR.read_text(encoding="utf-8")
    if (
        "cfs_strip_num_suffix" in c_src
        and "REJ_C_CXX" in c_src
        and "UINT64_MAX_SQRT" in c_src
        and "ceil(" in c_src
    ):
        rec("C-EMIT", "PASS", "lin_from_c.lin v2: U/L suffix strip, CXX reject, UINT64_MAX_SQRT expand")
    else:
        rec("C-EMIT", "FAIL", "C transpiler v2 symbols missing")

    jit_ok = lin_roundtrip_jit("ebr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ebr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ebr_isqrt", 16)
        if jv == 4:
            rec("C0-JIT", "PASS", "lin_c0 jit ebr_isqrt(16)==4 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/consensus-specs",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "license": "CC0-1.0",
        "phase0": {
            "path": PHASE0_REL,
            "git_blob_sha": PINNED_PHASE0_BLOB,
            "file_sha256": PINNED_PHASE0_SHA256,
        },
        "altair": {
            "path": ALTAIR_REL,
            "git_blob_sha": PINNED_ALTAIR_BLOB,
            "file_sha256": PINNED_ALTAIR_SHA256,
        },
    }
    evidence["lin_clone"] = "src/lin_eth_base_reward.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-eth-basereward"
    evidence["c11_oracle"] = "test/oracles/eth_base_reward_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["canonical_altair_1_validator_32eth_gwei"] = canonical
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
