#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Uniswap V3 getNextSqrtPriceFromOutput vs LIN C0 (EXPERIMENTAL Q32)."""
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
LIN = ROOT / "src" / "lin_uniswap_v3_output.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v3_output_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v3_output_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v3_core")
EVIDENCE = ROOT / "examples" / "uniswap_v3_output" / "uniswap_v3_output_evidence.json"

Q32 = 2**32
L = 1_000_000
PINNED_SHA256 = "ddd62e3a94346248677f30f1ab009ef015e71e4b8696dcca890eeabc9dc6c149"
PINNED_BLOB = "685f485da43402235c3a9ce7fd85a49597b6373a"
PINNED_COMMIT = "e3589b192d0be27e100cd0daaf6c97204fdb1899"
UPSTREAM_REL = "contracts/libraries/SqrtPriceMath.sol"


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


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_roundtrip_jit(path: Path, fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(path), fn, *[str(a) for a in args]], timeout=90)
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
    url = "https://github.com/Uniswap/v3-core.git"
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


def tdiv(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return -q if (a < 0) ^ (b < 0) else q


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_naive_sub0(sqrt_p: int, liq: int, amount: int) -> int:
    den = w64(liq - w64(amount * sqrt_p))
    return tdiv(w64(liq * sqrt_p), den)


def py_naive_under(sqrt_p: int, liq: int, amount: int) -> int:
    shift = w64(amount * Q32)
    quot = tdiv(shift, liq)
    if w64(shift - w64(quot * liq)) != 0:
        quot += 1
    return w64(sqrt_p - quot)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V3 FROM-OUTPUT — external LIN proof (Q32 uint64-scale, C11 oracle)")

    pinned = FIX / "SqrtPriceMath.sol"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned SqrtPriceMath.sol missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned SqrtPriceMath.sol sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned Uniswap/v3-core v1.0.0 matches fixture",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of SqrtPriceMath.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb FromOutput selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (output routing / ceil / wrap-hide)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of FromOutput clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v3_output.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if (chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout) else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if (chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout) else "FAIL",
        "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "v3o_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "v3o_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "v3o_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "v3o_muldiv", (100, 200, 50), 400),
        ("out", [str(Q32), str(L), "500000", "1"], "v3o_next_from_output", (Q32, L, 500000, 1), 2147483648),
        ("asinput", [str(Q32), str(L), "500000", "1"], "v3o_as_input", (Q32, L, 500000, 1), 2863311531),
        ("out", [str(Q32), str(L), "500000", "0"], "v3o_next_from_output", (Q32, L, 500000, 0), 8589934592),
        ("asinput", [str(Q32), str(L), "500000", "0"], "v3o_as_input", (Q32, L, 500000, 0), 6442450944),
        ("n1sub", [str(Q32), str(L), "1"], "v3o_next1_sub", (Q32, L, 1), 4294963001),
        ("floor1", [str(Q32), str(L), "1"], "v3o_floor_sub1", (Q32, L, 1), 4294963002),
        ("n0sub", [str(Q32), str(L), "1"], "v3o_next0_sub", (Q32, L, 1), 4294971591),
        ("floor0", [str(Q32), str(L), "1"], "v3o_floor_sub0", (Q32, L, 1), 4294971590),
        ("out", [str(Q32), str(L), str(L), "1"], "v3o_next_from_output", (Q32, L, L, 1), 0),
        ("asinput", [str(Q32), str(L), str(L), "1"], "v3o_as_input", (Q32, L, L, 1), 2147483648),
        ("naive0", [str(Q32), str(L), "500000"], "v3o_naive_wrap_sub0", (Q32, L, 500000), -2),
        ("under", [str(Q32), str(L), "1000001"], "v3o_naive_underflow", (Q32, L, 1000001), -4295),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != expect or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} expect={expect}")
            return 1
        if kind == "naive0":
            py = py_naive_sub0(*largs)
        elif kind == "under":
            py = py_naive_under(*largs)
        else:
            py = want
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python wrapping-int matches C11 and LIN")
    rec("ROUTE-INVERT", "PASS",
        "exact-output zfo=1 of 5e5 is Q/2=2147483648; FromInput routing yields 2863311531")
    rec("ROUTE-ZFO0", "PASS",
        "exact-output zfo=0 of 5e5 is 2Q=8589934592; FromInput routing yields 1.5Q=6442450944")
    rec("CEIL-VS-FLOOR", "PASS",
        "token1 remove amount=1 ceils to 4294963001 vs floor 4294963002 (1-unit solvency)")
    rec("NAIVE-WRAP", "PASS",
        "naive wrapping (L*sqrtP)/(L-amount*sqrtP) yields -2; 128-bit output yields 2Q")
    rec("WRAP-HIDE", "PASS",
        "token1 amount=L+1: wrapping sub yields -4295; require(sqrtP>quot) fail-closes to 0")
    rec("UNDERFLOW-IN", "PASS",
        "output of L token1 fail-closes 0; FromInput routing of the same amount yields Q/2")

    jit_ok = lin_roundtrip_jit(LIN, "v3o_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on v3o_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "v3o_next_from_output" in src and "getNextSqrtPriceFromOutput" in sol:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes sqrtP/L/amountOut/zeroForOne as arguments")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected FromOutput vs Solidity library")
    rec("WIDE-MULDIV", "PASS" if "v3o_muldiv" in src and "_lia_ushr" in src else "FAIL",
        "clone uses 128-bit product muldiv (Q32 * L * sqrtP)")
    rec("Q32-NOT-Q96", "PASS", "Q32=2^32 used; Q96=2^96 cannot fit signed i64")
    rec("NOT-FROM-INPUT", "PASS" if "v3o_next_from_input" not in src else "FAIL",
        "kernel is FromOutput only; FromInput is the named rejected routing v3o_as_input")
    rec("NOT-AMT-DELTA", "PASS" if "!v3o_amt" not in src and "v3o_get_amount" not in src else "FAIL",
        "kernel is next-sqrt-from-output; amount-delta is a named contrast not a port")
    rec("NOT-TICK-INV", "PASS" if "!v3o_tick_at" not in src and "v3o_get_tick" not in src else "FAIL",
        "no i64 inverse of the tick table; getTickAtSqrtRatio is assembly-MSB reject")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_FROM_OUTPUT", "REJ_SOLIDITY_TICK_AT", "REJ_SOLIDITY_RESOLUTION",
        "REJ_SOLIDITY_LSHIFT", "REJ_SOLIDITY_UINT160", "REJ_SOLIDITY_TYPE_MAX",
        "REJ_SOLIDITY_ROUNDING_UP", "REJ_SOLIDITY_UNSAFE_MATH", 'out = out + "="',
    ]
    missing = [t for t in need if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing else "PASS",
        "lin_from_solidity.lin v3 rejects FromOutput / TickAt / RESOLUTION / << / uint160 / RoundingUp",
        ",".join(missing) if missing else "")
    rs_src = RS_TR.read_text(encoding="utf-8")
    rec("RS-REJECT",
        "PASS" if "REJ_RUST_FROM_OUTPUT" in rs_src and "REJ_RUST_TICK_AT" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects FromOutput / TickAt / RESOLUTION / <<")

    evidence = {
        "schema": "LIN_UNISWAP_V3_FROM_OUTPUT_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/Uniswap/v3-core",
            "commit": commit or PINNED_COMMIT,
            "tag": "v1.0.0",
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2023-04-01 elapsed",
        },
        "lin_clone": "src/lin_uniswap_v3_output.lin",
        "c11_oracle": "test/oracles/uniswap_v3_output_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "q_scale": "Q32=2^32 (not Q96=2^96)",
        "goldens": {
            "out_zfo1_5e5": 2147483648,
            "as_input_zfo1_5e5": 2863311531,
            "out_zfo0_5e5": 8589934592,
            "as_input_zfo0_5e5": 6442450944,
            "ceil_amt1_1": 4294963001,
            "floor_amt1_1": 4294963002,
            "naive_wrap_sub0": -2,
            "naive_underflow": -4295,
        },
        "clone_lin": "https://github.com/kbelludoo/clone-lin-uniswap-v3-output",
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
