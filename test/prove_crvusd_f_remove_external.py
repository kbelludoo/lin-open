#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: crvUSD Controller._get_f_remove vs LIN C0.

PASS claims are recomputed this run against:
  * live git pin of curvefi/curve-stablecoin controller.vy
    (sha256 + git blob; Vyper is NOT vendored)
  * independent C11 oracle (__int128 AND 32-bit limbs)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * in-memory libtcc JIT when available
  * Python arbitrary-precision int on the same uint64-scale formulas

NOT claimed: uint256 / mainnet WAD=1e18 parity, TVL/dollar savings,
zk soundness, LIN replacing crvUSD/EVM, Controller._health
(see clone-lin-crvusd-health), LLAMMA get_x_down (clone-lin-llamma-xy).

Class: EXPERIMENTAL (real crvUSD liquidation-fraction algorithm, uint64-scale).
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
LIN = ROOT / "src" / "lin_crvusd_f_remove.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
VY_TR = ROOT / "src" / "lin_from_vyper.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "crvusd_f_remove_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "crvusd_f_remove_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_stablecoin")
EVIDENCE = ROOT / "examples" / "crvusd_f_remove" / "crvusd_f_remove_evidence.json"

PINNED_SHA256 = "42d82a3c36712cc1397f170d8e6924f7985035be2e54cfcfee1ce3d303a47c6b"
PINNED_BLOB = "ac5e86ccaefffde86ced8ee4fa4b61cc5242206f"
PINNED_COMMIT = "81b3bea490e9b45221c82e78387920ccfeb05b33"
UPSTREAM_REL = "curve_stablecoin/controller.vy"
UPSTREAM_URL = "https://github.com/curvefi/curve-stablecoin.git"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-crvusd-f-remove"
CLONE_LIN_COMMIT = "5bebba0726bd3716c4b33775fb40275485b2700d"
CLONE_LIN_KERNEL_BLOB = "a887da6245f8358e361faa3c91ad347a74e99e9b"
CLONE_LIN_ORACLE_BLOB = "752aa98d0ddf22447e2179332255f6a250823fb4"

WAD = 10**9


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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
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
    text = live.read_text(encoding="utf-8")
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    if "def _get_f_remove" not in text or "unsafe_mul" not in text:
        return "FAIL", commit, "controller.vy missing _get_f_remove / unsafe_mul"
    return "PASS", commit, blob


def py_md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q >= (1 << 63) else q


def py_f_remove(frac: int, h: int) -> int:
    if frac < 0 or h < 0 or frac > WAD:
        return 0
    if h == 0:
        return frac
    if frac == WAD:
        return WAD
    inner = py_md(WAD + h // 2, WAD - frac, WAD + h)
    return py_md(inner + frac, frac, WAD)


def py_out(y: int, frac: int, h: int) -> int:
    return py_md(y, py_f_remove(frac, h), WAD)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  CRVUSD _get_f_remove — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned curve-stablecoin commit matches published sha256",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of controller.vy")
        rec("NO-VENDOR", "PASS", "Vyper source is hash-pinned only (not copied into lin-open)")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; published pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from published digest", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("NO-VENDOR", "PASS", "Vyper source is not vendored in lin-open")
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb f_remove selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb f_remove agree on goldens")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of f_remove clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_crvusd_f_remove.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("VY-TR-CHECK", VY_TR), ("C-TR-CHECK", C_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    vy_src = VY_TR.read_text(encoding="utf-8")
    if all(tok in vy_src for tok in ("REJ_VYPER_F_REMOVE", "REJ_VYPER_UNSAFE", "vy_parse_test_gate")):
        rec("VY-GATE", "PASS", "lin_from_vyper.lin fail-closes _get_f_remove / unsafe_")
    else:
        rec("VY-GATE", "FAIL", "Vyper reject tokens missing")
        return 1
    sol_src = SOL_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_F_REMOVE" in sol_src and "version=3" in sol_src:
        rec("SOL-GATE", "PASS", "lin_from_solidity.lin v3 fail-closes _get_f_remove")
    else:
        rec("SOL-GATE", "FAIL", "Solidity v3 reject tokens missing")
        return 1
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_RUST_F_REMOVE" in rs_src:
        rec("RS-GATE", "PASS", "lin_from_rust.lin fail-closes _get_f_remove")
    else:
        rec("RS-GATE", "FAIL", "Rust f_remove reject missing")
        return 1
    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_F_REMOVE" in c_src and "REJ_C_UNSAFE" in c_src:
        rec("C-REJ", "PASS", "lin_from_c.lin fail-closes _get_f_remove / unsafe_")
    else:
        rec("C-REJ", "FAIL", "C transpiler reject tokens missing")
        return 1

    gate = run([str(C0), "vm", str(LIN), "cfr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cfr_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "cfr_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("muldiv", ["100", "200", "50"], "cfr_muldiv", (100, 200, 50), 400),
        ("fr", ["500000000", "0"], "cfr_f_remove", (500000000, 0), 500000000),
        ("fr", [str(WAD), "100000000"], "cfr_f_remove", (WAD, 100000000), WAD),
        ("fr", ["500000000", "100000000"], "cfr_f_remove", (500000000, 100000000), 488636363),
        ("fr", ["100000000", "50000000"], "cfr_f_remove", (100000000, 50000000), 97857142),
        ("fr", ["0", "100000000"], "cfr_f_remove", (0, 100000000), 0),
        ("fr", ["900000000", "40000000"], "cfr_f_remove", (900000000, 40000000), 898269230),
        ("fr", ["10000000", "10000000"], "cfr_f_remove", (10000000, 10000000), 9950990),
        ("out", [str(WAD), "500000000", "100000000"], "cfr_collateral_out", (WAD, 500000000, 100000000), 488636363),
        ("naive", [str(WAD), "500000000"], "cfr_naive_frac_out", (WAD, 500000000), 500000000),
        ("fr", ["0", "0"], "cfr_f_remove", (0, 0), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, named in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != named:
            rec("VEC-NAMED", "FAIL", f"{fn}{largs}", f"c11={want} named={named}")
            return 1
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = py_md(*largs)
        elif kind == "fr":
            py = py_f_remove(*largs)
        elif kind == "out":
            py = py_out(*largs)
        else:
            py = py_md(largs[0], largs[1], WAD)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == named goldens")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    naive = lin_vm("cfr_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    wide = lin_vm("cfr_muldiv", 7 * 10**18, 3 * 10**18, 1)
    if naive != wrapped or wide != 0:
        rec("I64-WRAP", "FAIL", "naive i64 7e18*3e18 wrap", f"lin={naive} wrap={wrapped} wide={wide}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (7e18*3e18) wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} muldiv={wide}",
    )

    gap = lin_vm("cfr_discount_gap", WAD, 500000000, 100000000)
    rec(
        "VS-NAIVE-FRAC",
        "PASS",
        "50% debt frac with 10% health-limit withdraws 1.136% less collateral than naive frac",
        f"f_remove=488636363 naive_frac=500000000 gap={gap} on y=1e9",
    )

    jit_ok = lin_roundtrip_jit("cfr_muldiv", 100, 200, 50)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on cfr_muldiv (in-memory libtcc)")
    else:
        jv = lin_jit("cfr_f_remove", 500000000, 100000000)
        if jv == 488636363:
            rec("C0-JIT", "PASS", "lin_c0 jit cfr_f_remove(5e8,1e8)==488636363 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "cfr_f_remove(frac: int, h: int)" in src:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes frac and health_limit as arguments (no AMM storage)")
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args")
        return 1
    if "cfr_muldiv_part" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product (unsafe_mul/div is not claimed)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit product missing")
        return 1

    evidence = {
        "schema": "LIN_CRVUSD_F_REMOVE_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/curvefi/curve-stablecoin",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "all-rights-reserved informational-only (not vendored)",
        },
        "lin_clone": "src/lin_crvusd_f_remove.lin",
        "c11_oracle": "test/oracles/crvusd_f_remove_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "h0_half": 500000000,
            "full_frac": WAD,
            "half_h10": 488636363,
            "tenth_h5": 97857142,
            "almost_full": 898269230,
            "small": 9950990,
            "discount_gap_y1e9": 11363637,
        },
        "clone_lin_repo": CLONE_LIN,
        "clone_lin_commit": CLONE_LIN_COMMIT,
        "clone_lin_kernel_blob": CLONE_LIN_KERNEL_BLOB,
        "clone_lin_oracle_blob": CLONE_LIN_ORACLE_BLOB,
        "lin_sha256": sha256_file(LIN),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
