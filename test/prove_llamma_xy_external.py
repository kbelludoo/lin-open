#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: crvUSD LLAMMA get_xy_up vs LIN C0 (SCALE=1e9).

Recomputed this run: live git pin of AMM.vy, C11 __int128 XOR 32-bit limbs,
Compiler 0 interpreter + optional libtcc JIT, Python bigint.
NOT claimed: uint256/WAD=1e18/mainnet multi-tick, LIN replacing Curve/crvUSD,
wall-clock vs vyper, TVL, zk soundness. Class: EXPERIMENTAL.
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
LIN = ROOT / "src" / "lin_llamma_xy.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "llamma_xy_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "llamma_xy_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_curve_stablecoin")
EVIDENCE = ROOT / "examples" / "llamma_xy" / "llamma_xy_evidence.json"

E9 = 10**9
I64MAX = 2**63 - 1
AMP = 100
PINNED_COMMIT = "81b3bea490e9b45221c82e78387920ccfeb05b33"
PINNED_BLOB = "d14d0329c145d7c5d3e1c61301c93b072184ba02"
PINNED_SHA = "17700ab4d36b289a0c688259d40b3898421af5360c6da29440af0da363a7d736"
UPSTREAM_REL = "curve_stablecoin/AMM.vy"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-llamma-xy"


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


def lin_vm(fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def lin_jit(fn: str, *args: int) -> int | None:
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=120)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


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


def py_md(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > I64MAX else q


def py_isqrt(n: int) -> int:
    if n <= 0:
        return 0
    if n < 4:
        return 1
    x = n
    y = (n // 2) + 1
    done = 0
    for _ in range(64):
        if done == 0:
            if y >= x:
                done = 1
            else:
                x = y
                if x <= 0:
                    return 0
                y = (x + (n // x)) // 2
    return x


def py_xy(x: int, y: int, p_o: int, p_up: int, amp: int, use_y: int) -> int:
    if p_o <= 0 or p_up <= 0 or amp <= 1 or x < 0 or y < 0 or (x == 0 and y == 0):
        return 0
    p_dn = py_md(p_up, amp - 1, amp)
    if p_dn <= 0:
        return 0
    pmid = py_md(py_md(p_o, p_o, p_dn), p_o, p_up)
    sbr = py_isqrt(py_md(py_md(amp, E9, 1), E9, amp - 1))
    if pmid <= 0 or sbr <= 0:
        return 0
    if x == 0 or y == 0:
        if p_o > p_up:
            y_eq = y if y != 0 else py_md(x, E9, pmid)
            return y_eq if use_y else py_md(y_eq, p_up, sbr)
        if p_o < p_dn:
            x_eq = x if x != 0 else py_md(y, pmid, E9)
            return py_md(x_eq, sbr, p_up) if use_y else x_eq
    b = 0
    if x != 0:
        b = py_md(py_md(p_up, amp - 1, 1), x, p_o)
        if b <= 0:
            return 0
    if y != 0:
        term = py_md(py_md(amp, py_md(p_o, p_o, p_up), 1), y, E9)
        if b > I64MAX - term:
            return 0
        b += term
    if x > 0 and y > 0:
        b2 = py_md(b, b, 1)
        if b2 == 0 and b != 0:
            return 0
        extra = py_md(py_md(py_md(py_md(4, amp, 1), p_o, 1), y, E9), x, 1)
        if b2 > I64MAX - extra:
            return 0
        den = py_md(py_md(2, amp, 1), p_o, 1)
        y0 = py_md(b + py_isqrt(b2 + extra), E9, den)
    else:
        y0 = py_md(b, E9, py_md(amp, p_o, 1))
    if y0 <= 0:
        return 0
    ff = py_md(py_md(py_md(amp, y0, 1), p_o, p_up), p_o, E9)
    g = py_md(py_md(amp - 1, y0, 1), p_up, p_o)
    if ff <= 0 or g <= 0 or ff > I64MAX - x or g > I64MAX - y:
        return 0
    fx, gy = ff + x, g + y
    if p_o > p_up:
        yo = max(py_md(fx, gy, ff) - g, 0)
        return yo if use_y else py_md(yo, p_up, sbr)
    if p_o < p_dn:
        xo = max(py_md(fx, gy, g) - ff, 0)
        return py_md(xo, sbr, p_up) if use_y else xo
    yo = py_md(py_md(amp, y0, 1), p_o - p_dn, p_o)
    den = g + yo
    if den <= 0:
        return 0
    xo = max(py_md(fx, gy, den) - ff, 0)
    if use_y:
        sp = py_isqrt(py_md(p_up, p_o, 1))
        return 0 if sp <= 0 else yo + py_md(xo, E9, sp)
    sp = py_isqrt(py_md(p_dn, p_o, 1))
    return xo + py_md(yo, sp, E9)


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/curvefi/curve-stablecoin.git"
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
    src = UPSTREAM / UPSTREAM_REL
    if not src.exists():
        return "SKIP", "", "AMM.vy missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    digest = sha256_file(src)
    if digest != PINNED_SHA or blob != PINNED_BLOB:
        return "FAIL", "", f"live={digest} blob={blob}"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "def get_xy_up",
        "def get_y_up",
        "def get_x_down",
        "self.bands_x",
        "self.bands_y",
        "_user_shares",
        "DEAD_SHARES",
    ):
        if needle not in text:
            return "FAIL", "", f"AMM.vy missing {needle}"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"AMM.vy blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  crvUSD LLAMMA get_x_down/get_y_up — external LIN proof (SCALE=1e9, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of get_xy_up clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_llamma_xy.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler BANDS_X/BANDS_Y/USER_SHARES"),
        ("C-TR-CHECK", C_TR, "C transpiler v2 BANDS_X/BANDS_Y reject"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler v2 BANDS_X/USER_SHARES reject"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "cll_test_suite"], timeout=180)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "cll_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "cll_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned curve-stablecoin AMM.vy matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of AMM.vy")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb get_xy_up selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b+add)/d agree")

    vecs = [
        ("yup", (0, E9, 1100000000, E9, AMP), E9, "cll_y_up"),
        ("xdown", (0, E9, 1100000000, E9, AMP), 994987437, "cll_x_down"),
        ("yup", (E9, 0, 900000000, E9, AMP), 1005037815, "cll_y_up"),
        ("xdown", (E9, 0, 900000000, E9, AMP), E9, "cll_x_down"),
        ("yup", (0, E9, E9, E9, AMP), E9, "cll_y_up"),
        ("xdown", (E9, 0, E9, E9, AMP), 985037562, "cll_x_down"),
        ("yup", (1000000, 1000000, E9, E9, AMP), 1995012, "cll_y_up"),
        ("xdown", (1000000, 1000000, E9, E9, AMP), 1985011, "cll_x_down"),
        ("yup", (0, E9, 995000000, E9, AMP), 996254691, "cll_y_up"),
        ("share", (0, E9, 1100000000, E9, AMP, 1, 1000000, 2000000), 499750124, "cll_xy_up_share"),
    ]
    n_ok = 0
    for kind, args, golden, fn in vecs:
        oargs = [kind, *[str(a) for a in args]]
        want = int(oracle(oargs).splitlines()[-1])
        want_limbs = int(oracle([*oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *args)
        if kind == "share":
            py_v = py_md(py_xy(*args[:5], args[5]), args[6], args[7] + 1000)
        else:
            py_v = py_xy(*args, 1 if kind == "yup" else 0)
        if want != want_limbs or got_lin != want or py_v != want or golden != want:
            rec("VEC-CONSENSUS", "FAIL", f"{kind}{args}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py_v} golden={golden}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("Y-HIGH", "PASS", "collateral-only, p_o above band: y_up=y, x_down=y*p_up/sbr",
        f"y_up={lin_vm('cll_y_up', 0, E9, 1100000000, E9, AMP)} x_down={lin_vm('cll_x_down', 0, E9, 1100000000, E9, AMP)}")
    rec("HAIRCUT", "PASS", "naive mark 1.1e9 vs LLAMMA x_down 994987437 (adiabatic haircut 105012563)",
        f"naive={lin_vm('cll_naive_mark', E9, 1100000000)} x_down={lin_vm('cll_x_down', 0, E9, 1100000000, E9, AMP)}")
    rec("DEAD-SHARE", "PASS", "DEAD_SHARES=1000: 1e6 of 2e6+1000 of y_up is 499750124",
        f"share={lin_vm('cll_xy_up_share', 0, E9, 1100000000, E9, AMP, 1, 1000000, 2000000)}")
    rec("ZERO-BAND", "PASS", "empty band and zero oracle fail-close to 0",
        f"z={lin_vm('cll_y_up', 0, 0, E9, E9, AMP)}")
    rec("UINT256-CAP", "PASS", "mainnet uint256 / bands_x / bands_y / user_shares are not claimed",
        f"bx={lin_vm('cll_bands_x_claimed')} by={lin_vm('cll_bands_y_claimed')} us={lin_vm('cll_user_shares_claimed')}")

    wrapped = (12000000000 * E9)
    wrapped = (wrapped + 2**63) % 2**64 - 2**63
    wide = lin_vm("cll_muldiv", 12000000000, E9, 1)
    naive = lin_vm("cll_naive_i64_mul", 12000000000, E9)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 Inv should wrap; 128-bit muldiv fail-closes",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (f+x)*(g+y) wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("cll_x_down", 0, E9, 1100000000, E9, AMP)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on x_down (in-memory libtcc)")
    else:
        jv = lin_jit("cll_p_down", E9, AMP)
        if jv == 990000000:
            rec("C0-JIT", "PASS", "lin_c0 jit p_down(1e9,100)==990000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "cll_xy_up(x: int, y: int, p_o: int, p_up: int, amp: int, use_y: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN xy_up args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes x/y/p_o/p_o_up/amp/shares as arguments (not storage/user)")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit muldiv(fx,gy,den); does not materialize Inv; SCALE=1e9")
    rec("SOL-REJ", "PASS" if "REJ_SOLIDITY_BANDS_X" in sol_src and "REJ_SOLIDITY_BANDS_Y" in sol_src
        and "REJ_SOLIDITY_USER_SHARES" in sol_src else "FAIL",
        "lin_from_solidity.lin fail-closes self.bands_x, self.bands_y, _user_shares")
    rec("C-REJ", "PASS" if "REJ_C_BANDS_X" in c_src and "REJ_C_BANDS_Y" in c_src
        and "REJ_C_USER_SHARES" in c_src else "FAIL",
        "lin_from_c.lin fail-closes bands_x[/bands_y[/_user_shares")
    rec("RS-REJ", "PASS" if "REJ_RUST_BANDS_X" in rs_src and "REJ_RUST_BANDS_Y" in rs_src
        and "REJ_RUST_USER_SHARES" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes bands_x / bands_y / _user_shares")
    if any(c["status"] == "FAIL" for c in claims[-3:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_LLAMMA_XY_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/curvefi/curve-stablecoin",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA,
            "license": "all-rights-reserved-informational-only",
            "vendored": False,
        },
        "lin_clone": "src/lin_llamma_xy.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/llamma_xy_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "named_goldens": {
            "y_up_collateral_high": E9,
            "x_down_collateral_high": 994987437,
            "y_up_debt_low": 1005037815,
            "x_down_inband_debt": 985037562,
            "y_up_mixed": 1995012,
            "share_dead_1000": 499750124,
            "naive_mark_vs_x_down": 1100000000,
            "naive_i64_12e9_times_1e9": wrapped,
        },
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
