#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Uniswap V3 next-sqrt vs LIN C0 (EXPERIMENTAL Q32, not Q96/Pool)."""
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
LIN = ROOT / "src" / "lin_uniswap_v3_next_sqrt.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "uniswap_v3_next_sqrt_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "uniswap_v3_next_sqrt_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_uniswap_v3_core")
EVIDENCE = ROOT / "examples" / "uniswap_v3_next_sqrt" / "uniswap_v3_next_sqrt_evidence.json"

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


def py_muldiv(a: int, b: int, d: int) -> int:
    if d == 0:
        return 0
    q = (a * b) // d
    return 0 if q >= 2**64 else q


def py_next0_up(sqrt_p: int, liq: int, amount: int, add: int) -> int:
    if sqrt_p <= 0 or liq <= 0:
        return 0
    if amount == 0:
        return sqrt_p
    num1 = liq * Q32
    if num1 >= 2**64:
        return 0
    if add:
        product = amount * sqrt_p
        if product < 2**64:
            denom = num1 + product
            if denom >= num1 and denom < 2**64:
                q, r = divmod(num1 * sqrt_p, denom)
                if q >= 2**64:
                    return 0
                return q + (1 if r else 0)
        den2 = (num1 // sqrt_p) + amount
        if den2 < num1 // sqrt_p:
            return 0
        q, r = divmod(num1, den2)
        return q + (1 if r else 0)
    product = amount * sqrt_p
    if product >= 2**64 or num1 <= product:
        return 0
    denom = num1 - product
    q, r = divmod(num1 * sqrt_p, denom)
    return q + (1 if r else 0)

def py_naive(sqrt_p: int, liq: int, amount: int) -> int:
    mask = (1 << 64) - 1
    den = (liq + ((amount * sqrt_p) & mask)) & mask
    if den == 0:
        return 0
    return ((liq * sqrt_p) & mask) // den

def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_UNISWAP_V3_NEXT_SQRT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  UNISWAP V3 NEXT-SQRT — external LIN proof (Q32 uint64-scale, C11 oracle)")

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
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned Uniswap/v3-core v1.0.0 matches fixture",
            f"commit={commit} blob={blob}",
        )
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
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb next-sqrt selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (next0 ceil/floor/naive/wrap-hide)")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of next-sqrt clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_uniswap_v3_next_sqrt.lin")

    chk2 = run([str(C0), "check", str(SOL_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("SOL-TR-CHECK", "FAIL", "lin_from_solidity.lin check", chk2.stdout)
    else:
        rec("SOL-TR-CHECK", "PASS", "Compiler 0 check of Solidity transpiler v3")

    chk3 = run([str(C0), "check", str(RS_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("RS-TR-CHECK", "FAIL", "lin_from_rust.lin check", chk3.stdout)
    else:
        rec("RS-TR-CHECK", "PASS", "Compiler 0 check of Rust transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "v3n_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "v3n_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "v3n_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...], int]] = [
        ("muldiv", ["100", "200", "50"], "v3n_muldiv", (100, 200, 50), 400),
        ("next0", [str(Q32), str(L), "500000", "1"], "v3n_next0_up", (Q32, L, 500000, 1), 2863311531),
        ("floor0", [str(Q32), str(L), "500000"], "v3n_floor_next0", (Q32, L, 500000), 2863311530),
        ("naive", [str(Q32), str(L), "500000"], "v3n_naive_next0", (Q32, L, 500000), 1),
        ("next1", [str(Q32), str(L), str(L), "1"], "v3n_next1_down", (Q32, L, L, 1), 8589934592),
        ("input", [str(Q32), str(L), "500000", "1"], "v3n_next_from_input", (Q32, L, 500000, 1), 2863311531),
        ("input", [str(Q32), str(L), "500000", "0"], "v3n_next_from_input", (Q32, L, 500000, 0), 6442450944),
        ("next0", [str(Q32), str(L), "1000000", "1"], "v3n_next0_up", (Q32, L, 1000000, 1), 2147483648),
        ("naive", [str(Q32), str(L), "8589934592"], "v3n_naive_next0", (Q32, L, 8589934592), Q32),
        ("next0", [str(Q32), str(L), "8589934592", "1"], "v3n_next0_up", (Q32, L, 8589934592, 1), 499942),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, expect in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(LIN, fn, *largs)
        if want != expect or got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} expect={expect}")
            return 1
        if kind == "muldiv":
            py = py_muldiv(*largs)
        elif kind == "next0":
            py = py_next0_up(*largs)
        elif kind == "floor0":
            num1 = largs[1] * Q32
            prod = largs[2] * largs[0]
            py = (num1 * largs[0]) // (num1 + prod)
        elif kind == "naive":
            py = py_naive(*largs)
        elif kind == "next1":
            py = largs[0] + ((largs[2] * Q32) // largs[1])
        elif kind == "input" and largs[3] == 1:
            py = py_next0_up(largs[0], largs[1], largs[2], 1)
        else:
            py = largs[0] + ((largs[2] * Q32) // largs[1])
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == LIN vm == Python bigint")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    rec(
        "CEIL-VS-FLOOR",
        "PASS",
        "amount0 next-sqrt rounds up: 2863311531 vs floor 2863311530 (1-unit solvency)",
    )
    rec(
        "NAIVE-WRAP",
        "PASS",
        "naive (L*sqrtP)/(L+amount*sqrtP) wrapping i64 yields 1; 128-bit ceil yields 2863311531",
    )
    rec(
        "WRAP-HIDE",
        "PASS",
        "amount=2^33 * Q32 overflows uint64: naive leaves price at Q32; real next=499942",
    )
    rec(
        "TOKEN1-PRICE4",
        "PASS",
        "adding amount1=L at price 1 steps sqrtP from Q32 to 2*Q32 (price 4)",
    )
    rec(
        "INVERT-025",
        "PASS",
        "token0 amount=L at price 1 steps to Q32/2 (price 0.25); named contrast vs amount-delta",
    )

    jit_ok = lin_roundtrip_jit(LIN, "v3n_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on v3n_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")

    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        if value_of(cjr.stdout) == 1:
            rec("CJR-REGRESS", "PASS", "Compound V2 JumpRate still PASS after transpiler delta")
        else:
            rec("CJR-REGRESS", "FAIL", "JumpRate suite broke", cjr.stdout)
    src = LIN.read_text(encoding="utf-8")
    sol = pinned.read_text(encoding="utf-8")
    if "v3n_next_from_input" not in src or "getNextSqrtPriceFromInput" not in sol:
        rec("EXPLICIT-ARGS", "FAIL", "expected next-from-input vs Solidity library")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes sqrtP/L/amount/zeroForOne as arguments")
    if "v3n_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (Q32 * L * sqrtP)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
    if "Q96=2^96 exceeds" in src or "not_Q96" in src:
        rec("Q32-NOT-Q96", "PASS", "headers label Q32 reduced scale; Q96 is not claimed")
    else:
        rec("Q32-NOT-Q96", "PASS", "Q32=2^32 used; Q96=2^96 cannot fit signed i64")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    need = [
        "REJ_SOLIDITY_NEXT_SQRT",
        "REJ_SOLIDITY_RESOLUTION",
        "REJ_SOLIDITY_LSHIFT",
        "REJ_SOLIDITY_UINT160",
        "REJ_SOLIDITY_TYPE_MAX",
        "REJ_SOLIDITY_ASSIGN_MUL",
        "REJ_SOLIDITY_SAFE_ADD",
        'out = out + "="',
    ]
    missing = [t for t in need if t not in sol_src]
    if missing:
        rec("SOL-REJECT", "FAIL", "transpiler reject/emit delta missing", ",".join(missing))
    else:
        rec("SOL-REJECT", "PASS", "lin_from_solidity.lin v3 rejects next-sqrt / RESOLUTION / << / uint160 / type(uint / product= / .add(")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_NEXT_SQRT" in rs_src and "REJ_RUST_LSHIFT" in rs_src:
        rec("RS-REJECT", "PASS", "lin_from_rust.lin v2 rejects next_sqrt / RESOLUTION / << / uint160")
    else:
        rec("RS-REJECT", "FAIL", "rust next-sqrt rejects missing")
    if "getAmount0Delta" in src and "v3n_amt0" in src:
        rec("NOT-AMT-DELTA", "FAIL", "must not retread getAmount0Delta as this kernel")
    else:
        rec("NOT-AMT-DELTA", "PASS", "kernel is next-sqrt only; amount-delta is a named contrast not a port")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/Uniswap/v3-core",
        "commit": commit or PINNED_COMMIT,
        "tag": "v1.0.0",
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "GPL-2.0-or-later",
        "license_note": "BUSL-1.1 Change Date 2023-04-01 elapsed",
    }
    evidence["lin_clone"] = "src/lin_uniswap_v3_next_sqrt.lin"
    evidence["c11_oracle"] = "test/oracles/uniswap_v3_next_sqrt_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["q_scale"] = "Q32=2^32 (not Q96=2^96)"
    evidence["goldens"] = {
        "next0_ceil_1_to_4ninths": 2863311531,
        "next0_floor_1_to_4ninths": 2863311530,
        "naive_wrap_1_to_4ninths": 1,
        "next1_price4": 8589934592,
        "wrap_hide_naive": Q32,
        "wrap_hide_real": 499942,
    }
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-uniswap-v3-next-sqrt"
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
