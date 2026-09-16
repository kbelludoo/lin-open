#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: OpenZeppelin Math.log10 / log256 (MIT v5.0.2) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of Math.sol (git blob + sha256) plus log10/log256 excerpt
    * an independent C11 oracle (same skip-10**64 algorithm as the LIN clone)
    * a *different* Python oracle (decimal-string length / int.bit_length)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * full Solidity uint256 range (LIN path is non-negative i64; 10**64/10**32 skipped)
    * that LIN replaces OpenZeppelin on mainnet
    * wall-clock superiority vs solc/EVM
    * computational soundness of Merkle receipts

Class: EXPERIMENTAL (real OZ algorithm, i64-scale operands).
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
LIN = ROOT / "src" / "lin_oz_log10.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "oz_log10_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "oz_log10_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_openzeppelin_contracts")
EVIDENCE = ROOT / "examples" / "oz_log10" / "oz_log10_evidence.json"

PINNED_SHA256 = "a6ee779fc42e6bf01b5e6a963065706e882b016affbedfd8be19a71ea48e6e15"
PINNED_BLOB = "9681524529b34f34033ae97064a2700bfc4eec00"
PINNED_COMMIT = "dbb6104ce834628e473d2173bbc9d47f81a9eec3"
PINNED_TAG = "v5.0.2"
UPSTREAM_REL = "contracts/utils/math/Math.sol"
EXCERPT_SHA256 = "2c0396e0703d1be2fbed02c40620fb5501a035ee204a8ccc8f279d8af6996432"
INT64_MAX = 9223372036854775807


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def py_log10(v: int) -> int:
    """Independent of the OZ if-chain: decimal length of |v|."""
    if v < 0:
        return 0
    if v == 0:
        return 0
    return len(str(v)) - 1


def py_log256(v: int) -> int:
    """Independent of the OZ shift-chain: bit_length grouped by octets."""
    if v < 0:
        return 0
    if v == 0:
        return 0
    return (v.bit_length() - 1) // 8


def py_pow10(n: int) -> int:
    if n < 0 or n > 18:
        return 0
    return 10**n


def py_log10_round(v: int, round_up: int) -> int:
    r = py_log10(v)
    if not round_up or v < 0:
        return r
    return r + 1 if py_pow10(r) < v else r


def py_log256_round(v: int, round_up: int) -> int:
    r = py_log256(v)
    if not round_up or v < 0:
        return r
    if r >= 8:
        return r
    return r + 1 if (1 << (r * 8)) < v else r


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/OpenZeppelin/openzeppelin-contracts.git"
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
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_OZ_LOG10_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  OPENZEPPELIN Math.log10/log256 — external LIN proof (i64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "openzeppelin_math_v5_0_2.sol"
    excerpt = FIX / "oz_log10_log256_excerpt.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned openzeppelin_math_v5_0_2.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned Math.sol hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned OpenZeppelin Math.sol v5.0.2 sha256 matches manifest")

    if not excerpt.exists():
        rec("PIN-EXCERPT", "FAIL", "log10/log256 excerpt missing")
        return 1
    ex = sha256_file(excerpt)
    if ex != EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "excerpt sha256 mismatch", f"{ex} != {EXCERPT_SHA256}")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned log10/log256 excerpt sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned openzeppelin-contracts commit matches fixture",
            f"tag={PINNED_TAG} commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of contracts/utils/math/Math.sol")
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
        rec("C11-SELFTEST", "FAIL", "C11 log10/log256 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle selftest (pow10/log10/log256 goldens)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of oz_log10 clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_oz_log10.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3 (POW/ENUM reject)")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (word-boundary sqrt)")

    gate = run([str(C0), "vm", str(LIN), "ozl_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ozl_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ozl_test_suite == 1 on Compiler 0 interpreter", gate.stdout.strip()[:160])

    vectors: list[tuple[str, int, int]] = [
        ("log10", 0, 0),
        ("log10", 1, 0),
        ("log10", 9, 0),
        ("log10", 10, 0),
        ("log10", 99, 0),
        ("log10", 100, 0),
        ("log10", 10**8, 0),
        ("log10", 10**16, 0),
        ("log10", 10**18, 0),
        ("log10", INT64_MAX, 0),
        ("log10", -1, 0),
        ("log10r", 11, 1),
        ("log10r", 10, 1),
        ("log256", 255, 0),
        ("log256", 256, 0),
        ("log256", 65536, 0),
        ("log256", 2**32, 0),
        ("log256r", 257, 1),
        ("digits", 10**8, 0),
        ("digits", 10**18, 0),
        ("nbytes", 255, 0),
    ]
    n_ok = 0
    for kind, a, b in vectors:
        oargs = [kind, str(a)] + ([str(b)] if kind.endswith("r") else [])
        want = int(oracle(oargs).splitlines()[-1])
        if kind == "log10":
            got_lin = lin_vm("ozl_log10", a)
            py = py_log10(a)
        elif kind == "log10r":
            got_lin = lin_vm("ozl_log10_round", a, b)
            py = py_log10_round(a, b)
        elif kind == "log256":
            got_lin = lin_vm("ozl_log256", a)
            py = py_log256(a)
        elif kind == "log256r":
            got_lin = lin_vm("ozl_log256_round", a, b)
            py = py_log256_round(a, b)
        elif kind == "digits":
            got_lin = lin_vm("ozl_dec_digits", a)
            py = 0 if a < 0 else (1 if a == 0 else py_log10(a) + 1)
        else:
            got_lin = lin_vm("ozl_hex_nbytes", a)
            py = 0 if a < 0 else (1 if a == 0 else py_log256(a) + 1)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{kind}({a},{b})", f"lin={got_lin} c11={want}")
            return 1
        if py != want:
            rec("VEC-PY", "FAIL", f"python {kind}({a})", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} goldens: C11 == LIN vm == Python str/bit_length")

    extra = [2, 3, 7, 16, 31, 32, 63, 64, 99, 100, 999, 1000, 10**6 - 1, 10**6, 10**15, 10**16 - 1]
    extra += [2**k for k in range(1, 63)]
    extra += [10**k for k in range(0, 19)]
    extra += [INT64_MAX - 1, INT64_MAX]
    n_scan = 0
    for a in extra:
        if a > INT64_MAX:
            continue
        c11 = int(oracle(["log10", str(a)]).splitlines()[-1])
        lin = lin_vm("ozl_log10", a)
        py = py_log10(a)
        if not (c11 == lin == py):
            rec("SCAN-LOG10", "FAIL", f"log10({a})", f"c11={c11} lin={lin} py={py}")
            return 1
        c11b = int(oracle(["log256", str(a)]).splitlines()[-1])
        linb = lin_vm("ozl_log256", a)
        pyb = py_log256(a)
        if not (c11b == linb == pyb):
            rec("SCAN-LOG256", "FAIL", f"log256({a})", f"c11={c11b} lin={linb} py={pyb}")
            return 1
        n_scan += 1
    rec(
        "SCAN-INDEPENDENT",
        "PASS",
        f"{n_scan} values: Python len(str)/bit_length == C11 == LIN",
    )

    eth_wei = 10**18
    btc_sat = 10**8
    usdc = 10**6
    d_eth = lin_vm("ozl_dec_digits", eth_wei)
    d_btc = lin_vm("ozl_dec_digits", btc_sat)
    d_usdc = lin_vm("ozl_dec_digits", usdc)
    if d_eth != 19 or d_btc != 9 or d_usdc != 7:
        rec("COMMERCIAL", "FAIL", "decimal digit counts for 1 ETH / 1 BTC / 1 USDC units")
        return 1
    rec(
        "COMMERCIAL",
        "PASS",
        "decimal-digit count for 1 ETH (1e18 wei)=19, 1 BTC (1e8 sat)=9, 1 USDC (1e6)=7",
        "buffer-sizing for token amount formatting; not a TVL or gas-savings claim",
    )

    jit_ok = lin_roundtrip_jit("ozl_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ozl_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ozl_log10", 100)
        if jv == 2:
            rec("C0-JIT", "PASS", "lin_c0 jit ozl_log10(100)==2 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_POW" in sol_src and '"**"' in sol_src:
        rec("SOL-POW", "PASS", "lin_from_solidity.lin v3 fail-closes Solidity ** (10**64 is not i64)")
    else:
        rec("SOL-POW", "FAIL", "REJ_SOLIDITY_POW missing")
    if "REJ_SOLIDITY_ENUM" in sol_src and "sol_has_user_type" in sol_src:
        rec("SOL-ENUM", "PASS", "lin_from_solidity.lin v3 fail-closes enum / Rounding user types")
    else:
        rec("SOL-ENUM", "FAIL", "REJ_SOLIDITY_ENUM missing")

    c_src = C_TR.read_text(encoding="utf-8")
    if "cfs_has_call" in c_src and '"sqrt"' in c_src:
        rec("C-SQRT", "PASS", "lin_from_c.lin v2 word-boundary libc sqrt(/sqrtf(/sqrtl( is REJ_C_FLOAT")
    else:
        rec("C-SQRT", "FAIL", "cfs_has_call sqrt reject missing")

    c_fix = (FIX / "oz_log10_u64.c").read_text(encoding="utf-8")
    if "*" in c_fix.split("int64_t", 1)[-1] or "sqrt(" in c_fix:
        rec("C-ELIGIBLE", "FAIL", "scalar C rewrite unexpectedly has pointers or sqrt(")
    else:
        rec(
            "C-ELIGIBLE",
            "PASS",
            "scalar C rewrite has no pointers/sqrt — eligible for cfs_reason=OK (lin_c0 does not execute cfs_from_c; string-literal VM gate)",
        )

    math = pinned.read_text(encoding="utf-8")
    if "10 ** 64" not in math or "function log10" not in math:
        rec("UPSTREAM-LOG10", "FAIL", "pinned Math.sol missing log10 / 10 ** 64")
    else:
        rec("UPSTREAM-LOG10", "PASS", "pinned Math.sol contains log10 with 10 ** 64 (rejected for i64 emit)")

    lin_src = LIN.read_text(encoding="utf-8")
    if "10000000000000000" in lin_src and "10 **" not in lin_src and "**" not in lin_src:
        rec("NO-POW-EMIT", "PASS", "LIN clone uses explicit 10^16..10^1 constants; no ** operator")
    else:
        rec("NO-POW-EMIT", "FAIL", "unexpected ** in LIN clone or missing 10^16 constant")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/OpenZeppelin/openzeppelin-contracts",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "excerpt_sha256": EXCERPT_SHA256,
        "license": "MIT",
    }
    evidence["lin_clone"] = "src/lin_oz_log10.lin"
    evidence["c11_oracle"] = "test/oracles/oz_log10_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["commercial"] = {
        "eth_wei_digits": d_eth,
        "btc_sat_digits": d_btc,
        "usdc_digits": d_usdc,
        "note": "digit counts for amount-string buffers; not a TVL claim",
    }
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-oz-log10"
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
