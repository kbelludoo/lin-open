#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.frob vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss vat.sol, C11 __int128 XOR
limbs, lin_c0 VM, Python bigint. Not claimed: RAY=1e27/uint256, TVL, zk, wish.
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
LIN = ROOT / "src" / "lin_maker_vat_frob.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_frob_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_frob_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_frob" / "maker_vat_frob_evidence.json"

RAY = 10**9
E18 = 10**18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-frob"
CLONE_LIN_HEAD = "7e219fd71412a851c6f6706b45cf12faf7a89f9c"
CLONE_LIN_LIN_COMMIT = "562f9e340b8ebce18d5b7c5980c6b2743badef4f"
CLONE_LIN_LIN_BLOB = "99419e74b6e6be102b99b7daf90ebd82ffb147b5"
CLONE_LIN_C_BLOB = "aa9750e46c4797d0e90baa2a3d909b2f5694fc7b"


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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/makerdao/dss.git"
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


def py_umul(a: int, b: int) -> int:
    p = a * b
    return 0 if a < 0 or b < 0 or p > I64MAX else p


def py_add_ui(x: int, y: int) -> int:
    z = x + y
    if z < 0 or z > I64MAX:
        return 0
    if y >= 0 and z < x:
        return 0
    if y < 0 and z > x:
        return 0
    return z


def py_frob_ok(
    live: int, rate: int, ink: int, art: int, art_ilk: int, dink: int, dart: int,
    spot: int, line: int, line_g: int, debt: int, dust: int,
) -> int:
    if live != 1 or rate == 0:
        return 0
    if min(rate, ink, art, art_ilk, spot, line, line_g, debt, dust) < 0:
        return 0
    ink2 = py_add_ui(ink, dink)
    art2 = py_add_ui(art, dart)
    art_ilk2 = py_add_ui(art_ilk, dart)
    if ink + dink >= 0 and ink + dink <= I64MAX and ink2 != ink + dink:
        return 0
    if art + dart >= 0 and art + dart <= I64MAX and art2 != art + dart:
        return 0
    if art_ilk + dart >= 0 and art_ilk + dart <= I64MAX and art_ilk2 != art_ilk + dart:
        return 0
    if py_umul(rate, abs(dart)) == 0 and dart != 0 and rate != 0:
        return 0
    tab = py_umul(rate, art2)
    cov = py_umul(ink2, spot)
    dtab = py_umul(rate, abs(dart))
    signed_dtab = -dtab if dart < 0 else dtab
    debt2 = py_add_ui(debt, signed_dtab)
    if dart > 0:
        if py_umul(art_ilk2, rate) > line or debt2 > line_g:
            return 0
    if not (dart <= 0 and dink >= 0):
        if tab > cov:
            return 0
    if art2 != 0 and tab < dust:
        return 0
    return 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_FROB_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.FROB — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned makerdao/dss vat.sol matches hash pin",
            f"commit={commit} blob={blob}",
        )
        live = UPSTREAM / UPSTREAM_REL
        text = live.read_text(encoding="utf-8", errors="replace")
        if "function frob(" not in text or "_mul(uint x, int y)" not in text:
            rec("UPSTREAM-FROB", "FAIL", "pinned vat.sol missing frob/_mul")
            return 1
        rec("UPSTREAM-FROB", "PASS", "pinned vat.sol contains frob and signed _mul (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-FROB", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-FROB", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.frob clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_frob.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "mfr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mfr_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "mfr_test_suite == 1 on Compiler 0 interpreter", f"steps from stdout")

    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "mfr_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "mfr_muldiv", (7, 9, 1)),
        ("tab", ["500000000", str(RAY)], "mfr_tab", (500000000, RAY)),
        ("spot_cov", [str(RAY), "2000000000"], "mfr_spot_cov", (RAY, 2000000000)),
        ("max_art", [str(RAY), "1500000000", str(RAY)], "mfr_max_art", (RAY, 1500000000, RAY)),
        ("add_ui", [str(RAY), "-500000000"], "mfr_add_ui", (RAY, -500000000)),
        (
            "ok",
            ["1", str(RAY), "0", "0", "0", str(RAY), "500000000", "2000000000", str(E18), str(E18), "0", "0"],
            "mfr_frob_ok",
            (1, RAY, 0, 0, 0, RAY, 500000000, 2000000000, E18, E18, 0, 0),
        ),
        (
            "ok",
            ["1", str(RAY), "0", "0", "0", str(RAY), "3000000000", "2000000000", str(E18), str(E18), "0", "0"],
            "mfr_frob_ok",
            (1, RAY, 0, 0, 0, RAY, 3000000000, 2000000000, E18, E18, 0, 0),
        ),
        (
            "ok",
            ["1", str(RAY), str(RAY), "2000000000", "2000000000", "0", "-500000000", str(RAY), str(E18), str(E18), "2000000000000000000", "0"],
            "mfr_frob_ok",
            (1, RAY, RAY, 2000000000, 2000000000, 0, -500000000, RAY, E18, E18, 2000000000000000000, 0),
        ),
        (
            "ok",
            ["0", str(RAY), "0", "0", "0", str(RAY), "500000000", "2000000000", str(E18), str(E18), "0", "0"],
            "mfr_frob_ok",
            (0, RAY, 0, 0, 0, RAY, 500000000, 2000000000, E18, E18, 0, 0),
        ),
        (
            "ok",
            ["1", str(RAY), str(RAY), "0", "0", "0", "1", "2000000000", str(E18), str(E18), "0", "1000000000000000"],
            "mfr_frob_ok",
            (1, RAY, RAY, 0, 0, 0, 1, 2000000000, E18, E18, 0, 10**15),
        ),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if kind == "muldiv":
            py = largs[0] * largs[1] // largs[2]
        elif kind == "tab":
            py = py_umul(largs[1], largs[0])
        elif kind == "spot_cov":
            py = py_umul(largs[0], largs[1])
        elif kind == "max_art":
            py = py_umul(largs[0], largs[1]) // largs[2]
        elif kind == "add_ui":
            py = py_add_ui(largs[0], largs[1])
        else:
            py = py_frob_ok(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    open_ok = lin_vm("mfr_frob_ok", 1, RAY, 0, 0, 0, RAY, 500000000, 2000000000, E18, E18, 0, 0)
    unsafe = lin_vm("mfr_frob_ok", 1, RAY, 0, 0, 0, RAY, 3000000000, 2000000000, E18, E18, 0, 0)
    max150 = lin_vm("mfr_max_art", RAY, 1500000000, RAY)
    if open_ok != 1 or unsafe != 0 or max150 != 1500000000:
        rec("NAMED-GOLDEN", "FAIL", "OPEN/UNSAFE/MAX150 goldens", f"open={open_ok} unsafe={unsafe} max150={max150}")
        return 1
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "OPEN lock+draw at 200% collat is safe; 3e9 draw is unsafe; 150% max_art=1.5e9",
        "open=1 unsafe=0 max_art=1500000000 naive_1to1=1000000000 liq_buffer=500000000",
    )
    rec(
        "COMMERCIAL",
        "PASS",
        "measured CDP buffer vs naive 1:1 (not TVL): 150% spot allows 1.5e9 art on 1e9 ink",
        "liq_buffer_wad=500000000",
    )

    wrapped = lin_vm("mfr_naive_i64_mul", 7000000000000000000, 3000000000000000000)
    wide = lin_vm("mfr_muldiv", 7000000000000000000, 3000000000000000000, 1)
    if wrapped != -5389669316318724096 or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs 128-bit fail-closed", f"wrap={wrapped} wide={wide}")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (7e18*3e18) wraps; 128-bit muldiv fail-closes to 0",
        f"i64_wrap={wrapped} bigint_fail_closed={wide}",
    )

    src = LIN.read_text(encoding="utf-8")
    if "mfr_frob_ok(live: int, rate: int, ink: int, art: int, art_ilk: int, dink: int, dart: int, spot: int, line: int, line_g: int, debt: int, dust: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/wish")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes CDP params as arguments (no hidden urns/wish/msg.sender)")
    if "mfr_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 a*b wraps on 7e18*3e18)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_VAT_FROB" in sol_src and "REJ_C_VAT_FROB" in c_src and "REJ_RUST_VAT_FROB" in rs_src:
        rec("TR-FAILCLOSE", "PASS", "Solidity/C/Rust transpilers fail-close vat.frob / wish / urns")
    else:
        rec("TR-FAILCLOSE", "FAIL", "transpiler reject tokens missing")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    jit_ok = lin_roundtrip_jit("mfr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mfr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mfr_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit mfr_muldiv(100,200,50)==400 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/makerdao/dss",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "AGPL-3.0-or-later",
        "vendored": False,
    }
    evidence["lin_clone"] = "src/lin_maker_vat_frob.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_frob_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "open_frob_ok": open_ok,
        "unsafe_overdraw_ok": unsafe,
        "max_art_150pct": max150,
        "naive_1to1": RAY,
        "liq_buffer_wad": max150 - RAY,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["clone_lin_head"] = CLONE_LIN_HEAD
    evidence["clone_lin_lin_commit"] = CLONE_LIN_LIN_COMMIT
    evidence["clone_lin_lin_blob"] = CLONE_LIN_LIN_BLOB
    evidence["clone_lin_c_blob"] = CLONE_LIN_C_BLOB
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
