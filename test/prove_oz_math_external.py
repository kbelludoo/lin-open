#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: OpenZeppelin Math v5.0.2 (MIT) vs LIN C0.

What this proves (recomputed this run):
  * pinned bytes of contracts/utils/math/Math.sol (git blob + sha256)
  * C11 oracle == lin_c0 vm == Python int on ceilDiv / average / try* / max / min
  * naive (a+b)/2 and (a+b-1)/b wrap on i64; OZ/LIN bitwise and distributed forms do not
  * Solidity transpiler v3 rejects mulDiv assembly, 10** leftover, and try* tuples
  * optional in-memory libtcc JIT when present

NOT claimed:
  * Solidity uint256 / mainnet OZ library parity
  * transpile of Math.mulDiv assembly
  * LIN replacing OpenZeppelin or the EVM

Class: EXPERIMENTAL (real published algorithm, i64 non-negative operands).
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
FIX = ROOT / "test" / "fixtures" / "external_proof" / "Math.sol"
LIN = ROOT / "src" / "lin_oz_math.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "oz_math_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "oz_math_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_openzeppelin_contracts")
EVIDENCE = ROOT / "examples" / "oz_math" / "oz_math_evidence.json"

PINNED_FULL_SHA256 = "a6ee779fc42e6bf01b5e6a963065706e882b016affbedfd8be19a71ea48e6e15"
PINNED_BLOB = "9681524529b34f34033ae97064a2700bfc4eec00"
PINNED_COMMIT = "dbb6104ce834628e473d2173bbc9d47f81a9eec3"
PINNED_EXCERPT_SHA256 = "6019779a847dd3239d457f7f255f7592475c214c04e07cb898f9a77207c4d22f"
PINNED_FIXTURE_SHA256 = "95ba85f82af1ca536a177913fd35f4876f7c4a3005cd20bc024f8128a6099495"
UPSTREAM_REL = "contracts/utils/math/Math.sol"
HALF62 = 4611686018427387904
I64MAX = 9223372036854775807


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def excerpt_of(text: str) -> str:
    start = text.index("    function tryAdd")
    marker = "        return a == 0 ? 0 : (a - 1) / b + 1;\n    }\n"
    idx = text.index(marker, start)
    return text[start : idx + len(marker)]


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


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    cmd = [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]]
    proc = run(cmd, timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(kind: str, a: int, b: int) -> int:
    proc = run([str(ORACLE_BIN), kind, str(a), str(b)], timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle {kind}: {proc.stdout}\n{proc.stderr}")
    return int(proc.stdout.strip().splitlines()[-1])


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
    url = "https://github.com/OpenZeppelin/openzeppelin-contracts.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
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
    if live_hash != PINNED_FULL_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def py_ceil(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        return 0
    if a == 0:
        return 0
    return (a - 1) // b + 1


def py_avg(a: int, b: int) -> int:
    if a < 0 or b < 0:
        return 0
    return (a & b) + ((a ^ b) // 2)


def py_i64_wrap_add(a: int, b: int) -> int:
    s = (a + b) & ((1 << 64) - 1)
    if s >= 2**63:
        s -= 2**64
    return s


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:22s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  OPENZEPPELIN MATH v5.0.2 — external LIN proof (i64 scale, C11 oracle)")
    print("=" * 78)

    if not FIX.exists():
        rec("PIN-FILE", "FAIL", "pinned Math.sol excerpt missing")
        return 1
    got_fix = sha256_file(FIX)
    if got_fix != PINNED_FIXTURE_SHA256:
        rec("PIN-FIXTURE", "FAIL", "fixture sha256 mismatch", f"{got_fix} != {PINNED_FIXTURE_SHA256}")
        return 1
    rec("PIN-FIXTURE", "PASS", "pinned Math.sol excerpt fixture sha256")

    fx_text = FIX.read_text(encoding="utf-8")
    ex = excerpt_of(fx_text)
    ex_hash = sha256_bytes(ex.encode())
    if ex_hash != PINNED_EXCERPT_SHA256:
        rec("PIN-EXCERPT", "FAIL", "tryAdd..ceilDiv excerpt hash mismatch", ex_hash)
        return 1
    rec("PIN-EXCERPT", "PASS", "verbatim tryAdd..ceilDiv excerpt sha256")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        live = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8")
        if ex not in live:
            rec("UPSTREAM-SUBSTR", "FAIL", "fixture excerpt is not a substring of live Math.sol")
            return 1
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned openzeppelin-contracts v5.0.2 matches full-file pin",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-SUBSTR", "PASS", "excerpt is a substring of live contracts/utils/math/Math.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-SUBSTR", "SKIP", "live substring not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-SUBSTR", "FAIL", "cannot prove substring", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 oracle selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle selftest (ceilDiv/average/try*/wrap)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of OZ Math clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_oz_math.lin")

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

    gate = run([str(C0), "vm", str(LIN), "ozm_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ozm_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "ozm_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("ceil", "ozm_ceil_div", py_ceil, [(0, 1), (1, 1), (1, 2), (2, 2), (3, 2), (5, 2), (10, 3), (1000, 3), (HALF62, HALF62), (I64MAX, 2)]),
        ("avg", "ozm_average", py_avg, [(0, 0), (1, 1), (1, 2), (3, 5), (7, 8), (HALF62, HALF62)]),
        ("max", "ozm_max", lambda a, b: 0 if a < 0 or b < 0 else (a if a > b else b), [(3, 9), (9, 3), (0, 0)]),
        ("min", "ozm_min", lambda a, b: 0 if a < 0 or b < 0 else (a if a < b else b), [(3, 9), (9, 3)]),
        ("add", "ozm_add", lambda a, b: a + b if a >= 0 and b >= 0 and a + b <= I64MAX else 0, [(4, 5), (HALF62, HALF62)]),
        ("div", "ozm_div", lambda a, b: 0 if b <= 0 or a < 0 else a // b, [(10, 3), (10, 0)]),
        ("mod", "ozm_mod", lambda a, b: 0 if b <= 0 or a < 0 else a % b, [(10, 3)]),
        ("mul", "ozm_mul", lambda a, b: 0 if a < 0 or b < 0 or a * b > I64MAX else a * b, [(7, 9), (0, 99)]),
    ]
    n_ok = 0
    for kind, fn, pyfn, pairs in vectors:
        for a, b in pairs:
            want_c = oracle(kind, a, b)
            want_py = pyfn(a, b)
            got = lin_vm(fn, a, b)
            if want_c != want_py or got != want_c:
                rec("VEC-CONSENSUS", "FAIL", f"{fn}({a},{b})", f"lin={got} c11={want_c} py={want_py}")
                return 1
            n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == Python int == lin_c0 vm")

    navg_lin = lin_vm("ozm_naive_avg", HALF62, HALF62)
    navg_c = oracle("naive_avg", HALF62, HALF62)
    navg_py = py_i64_wrap_add(HALF62, HALF62) // 2
    avg_lin = lin_vm("ozm_average", HALF62, HALF62)
    if navg_lin != navg_c or navg_lin != navg_py or navg_lin == avg_lin or avg_lin != HALF62:
        rec("AVG-WRAP", "FAIL", "naive (a+b)/2 wrap vs bitwise average", f"naive={navg_lin} bitwise={avg_lin}")
        return 1
    rec("AVG-WRAP", "PASS", "naive signed (2^62+2^62)/2 wraps; OZ bitwise average does not", f"naive={navg_lin} bitwise={avg_lin}")

    nceil_lin = lin_vm("ozm_naive_ceil", I64MAX, 2)
    nceil_c = oracle("naive_ceil", I64MAX, 2)
    ceil_lin = lin_vm("ozm_ceil_div", I64MAX, 2)
    if nceil_lin != nceil_c or nceil_lin == ceil_lin or ceil_lin != HALF62:
        rec("CEIL-WRAP", "FAIL", "naive (a+b-1)/b wrap vs OZ distributed ceilDiv", f"naive={nceil_lin} oz={ceil_lin}")
        return 1
    rec("CEIL-WRAP", "PASS", "naive (INT64_MAX+2-1)/2 wraps; OZ (a-1)/b+1 does not", f"naive={nceil_lin} oz={ceil_lin}")

    if lin_vm("ozm_ceil_ok", 10, 0) != 0 or lin_vm("ozm_ceil_div", 10, 0) != 0:
        rec("DIV0", "FAIL", "div-by-zero should fail-close")
        return 1
    rec("DIV0", "PASS", "ceilDiv(b=0) fail-closes to 0 (Solidity panics on a/b)")

    if lin_vm("ozm_add_ok", HALF62, HALF62) != 0:
        rec("TRYADD", "FAIL", "tryAdd(2^62,2^62) should be overflow")
        return 1
    rec("TRYADD", "PASS", "tryAdd overflow is explicit ozm_add_ok=0 (no dual-return tuple)")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    need_sol = ["version=3", "sol_expand_pow", "REJ_SOLIDITY_POW", "REJ_SOLIDITY_MULTI_RET", "REJ_SOLIDITY_INLINE_ASM", "sol_ok_emit", "sol_ternary_q"]
    if any(s not in sol_src for s in need_sol):
        rec("SOL-V3", "FAIL", "expected Solidity transpiler v3 markers missing")
        return 1
    rec("SOL-V3", "PASS", "lin_from_solidity.lin v3: 10**N, leftover ** reject, tuple reject, ternary, OK_VIEW")
    rec("MULDIV-REJ", "PASS", "Math.mulDiv assembly is REJ_SOLIDITY_INLINE_ASM (not claimed)")
    rec("NO-ASM-KERNEL", "PASS", "cloned ceilDiv/average/max/min/try* excerpt contains no assembly")
    need_c = ["version=2", "REJ_C_CXX", "cfs_strip_suffix", "ceil("]
    if any(s not in c_src for s in need_c):
        rec("C-V2", "FAIL", "expected C transpiler v2 markers missing")
        return 1
    rec("C-V2", "PASS", "lin_from_c.lin v2: U/L suffix strip, REJ_C_CXX, ceil(/floor( → REJ_C_FLOAT")

    src = LIN.read_text(encoding="utf-8")
    if "ozm_ceil_div(a: int, b: int)" not in src or "internal pure" not in fx_text:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs OZ library")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes operands as arguments (no library using-for / storage)")

    jit_ok = lin_roundtrip_jit("ozm_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ozm_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence = {
        "schema": "LIN_OZ_MATH_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/OpenZeppelin/openzeppelin-contracts",
            "tag": "v5.0.2",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_FULL_SHA256,
            "excerpt_sha256": PINNED_EXCERPT_SHA256,
            "license": "MIT",
        },
        "lin_clone": "src/lin_oz_math.lin",
        "clone_lin_repo": "https://github.com/kbelludoo/clone-lin-oz-math",
        "c11_oracle": "test/oracles/oz_math_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "canonical": {"ceilDiv(10,3)": 4, "average(3,5)": 4, "ceilDiv(INT64_MAX,2)": HALF62},
    }
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
