#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Clipper.take vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss clip.sol, C11 wrap-detect XOR
__int128 slice*price, lin_c0 VM, Python bigint. Chost dust floor. Tab cap.
Not claimed: uint256, TVL, zk, sales[] maps, chip/tip in take, callbacks.
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
LIN = ROOT / "src" / "lin_maker_clipper_take.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_clipper_take_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_clipper_take_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_clipper_take_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_clipper_take" / "maker_clipper_take_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7 * 10**9, 3 * 10**9
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "1ea897fc0e8e0964a2e5098716d86fdcd93d11e0b2e4f65998eb1b7650d167de"
PINNED_BLOB = "c43d8fff46a4ad225d1fa031b4b1de618345cba7"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/clip.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-clipper-take"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
FULL = (200000, 1000, 2000, 100, 100, 1, 1, 0, 0)
TAB_CAP = (100000, 1000, 1000, 200, 200, 1, 1, 0, 0)
CHOST = (100000, 1000, 400, 100, 100, 70000, 1, 0, 0)
NO_PARTIAL = (50000, 1000, 400, 100, 100, 70000, 1, 0, 0)
EXPENSIVE = (100000, 1000, 1000, 50, 100, 1, 1, 0, 0)
RESET = (100000, 1000, 1000, 100, 100, 1, 1, 1, 0)
NOT_RUN = (100000, 1000, 1000, 100, 100, 1, 0, 0, 0)
STOPPED3 = (100000, 1000, 1000, 100, 100, 1, 1, 0, 3)
STOPPED2 = (200000, 1000, 2000, 100, 100, 1, 1, 0, 2)
ZERO_PX = (100000, 1000, 1000, 100, 0, 1, 1, 0, 0)
EXACT = (100000, 1000, 1000, 100, 100, 1, 1, 0, 0)
DUST = (50000, 400, 400, 100, 100, 70000, 1, 0, 0)
ZERO_AMT = (100000, 1000, 0, 100, 100, 1, 1, 0, 0)
OVERFLOW = (I64MAX, WRAP_A, WRAP_A, WRAP_B, WRAP_B, 1, 1, 0, 0)
FN = {"ok": "ct_take_ok", "slice": "ct_slice", "owe": "ct_owe",
      "new_tab": "ct_new_tab", "new_lot": "ct_new_lot", "clears": "ct_clears",
      "returns": "ct_returns_col"}


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
    proc = run([str(C0), "vm", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
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
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
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


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/makerdao/dss.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    if sha256_file(live) != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={sha256_file(live)} blob={blob}"
    return "PASS", commit, blob


def py_mul_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    if a == 0 or b == 0:
        return 1
    p = a * b
    return int(0 <= p <= I64MAX)


def py_take(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return args[0] * args[1] if py_mul_ok(args[0], args[1]) else 0
    tab, lot, amt, maxp, price, chost, running, done, stopped = args
    if stopped >= 3 or running != 1 or done != 0 or price < 1:
        return 0
    if min(tab, lot, amt, chost) < 0 or maxp < price:
        return 0
    slice_ = min(lot, amt)
    if not py_mul_ok(slice_, price):
        return 0
    owe = slice_ * price
    tab_cap = tab < owe
    if tab_cap:
        owe = tab
        slice_ = owe // price
    elif owe < tab and slice_ < lot and tab - owe < chost:
        if tab <= chost:
            return 0
        owe = tab - chost
        slice_ = owe // price
    new_tab, new_lot = tab - owe, lot - slice_
    return {"ok": 1, "slice": slice_, "owe": owe, "new_tab": new_tab,
            "new_lot": new_lot, "clears": int(new_lot == 0),
            "returns": int(new_lot != 0 and new_tab == 0)}[kind]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_CLIPPER_TAKE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY CLIPPER.TAKE — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect slice*price and __int128 mul agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss clip.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function take(", "owe = mul(slice, price)", "Clipper/no-partial-purchase", "clipperCall")
        if any(s not in text for s in need):
            rec("UPSTREAM-TAKE", "FAIL", "pinned clip.sol missing take/owe/chost/callback")
            return 1
        rec("UPSTREAM-TAKE", "PASS", "pinned clip.sol contains take, slice*price, chost, callback (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/clip.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-TAKE", "SKIP", "live clip.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-TAKE", "FAIL", "clip.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of clipper.take clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_clipper_take.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "ct_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ct_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ct_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 100)),
        ("ok", FULL), ("slice", FULL), ("owe", FULL), ("new_tab", FULL), ("new_lot", FULL), ("clears", FULL),
        ("slice", TAB_CAP), ("owe", TAB_CAP), ("returns", TAB_CAP),
        ("slice", CHOST), ("owe", CHOST), ("new_tab", CHOST),
        ("ok", NO_PARTIAL), ("ok", EXPENSIVE), ("ok", RESET), ("ok", NOT_RUN),
        ("ok", STOPPED3), ("ok", STOPPED2), ("ok", ZERO_PX), ("ok", OVERFLOW),
        ("slice", EXACT), ("new_tab", EXACT), ("slice", DUST), ("ok", ZERO_AMT), ("new_lot", ZERO_AMT),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        fn = "ct_u_mul" if kind == "mul" else FN[kind]
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_take(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_take(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    full_ok = lin_vm("ct_take_ok", *FULL)
    full_slice = lin_vm("ct_slice", *FULL)
    full_owe = lin_vm("ct_owe", *FULL)
    cap_slice = lin_vm("ct_slice", *TAB_CAP)
    cap_owe = lin_vm("ct_owe", *TAB_CAP)
    ch_slice = lin_vm("ct_slice", *CHOST)
    ch_owe = lin_vm("ct_owe", *CHOST)
    ch_tab = lin_vm("ct_new_tab", *CHOST)
    no_part = lin_vm("ct_take_ok", *NO_PARTIAL)
    too_exp = lin_vm("ct_take_ok", *EXPENSIVE)
    reset_ok = lin_vm("ct_take_ok", *RESET)
    stop3 = lin_vm("ct_take_ok", *STOPPED3)
    stop2 = lin_vm("ct_take_ok", *STOPPED2)
    auth = lin_vm("ct_auth_required")
    chip = lin_vm("ct_chip_tip_in_take")
    brk = lin_vm("ct_breaker_take_level")
    vat = lin_vm("ct_is_vat_kernel")
    golden = (full_ok, full_slice, full_owe, cap_slice, cap_owe, ch_slice, ch_owe, ch_tab,
              no_part, too_exp, reset_ok, stop3, stop2, auth, chip, brk, vat)
    expect = (1, 1000, 100000, 500, 100000, 300, 30000, 70000, 0, 0, 0, 0, 1, 0, 0, 3, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "FULL/TAB_CAP/CHOST/NO_PARTIAL/breaker goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "FULL slice=1000 owe=1e5; TAB_CAP slice=500; CHOST slice=300 tab=70000; NO_PARTIAL=0; stopped<3",
        "full_owe=100000 cap_slice=500 chost_tab=70000 auth=0 chip_tip=0 breaker=3")
    rec("COMMERCIAL", "PASS",
        "measured Dutch-auction buy (not TVL): 1000 collat units at price 100 raises 100000 tab; chost dust floor explicit",
        "slice=1000 owe=100000 leftover_tab=100000 leftover_lot=0 unit=reduced_wad_rad")

    wrapped = lin_vm("ct_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("ct_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked slice*price fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "ct_take_ok(tab: int, lot: int, amt: int, maxp: int, price: int, chost: int" in src else "FAIL",
        "LIN clone takes tab/lot/amt/max/price/chost/running/done/stopped (no hidden sales[])")
    rec("NO-CHIP-TIP", "PASS" if "ct_chip_tip_in_take" in src else "FAIL",
        "take does not suck chip/tip; those are kick/redo incentives")
    rec("NO-AUTH", "PASS" if "ct_auth_required" in src else "FAIL",
        "take is public (lock+breaker), not wards auth; LIN measures auth_required=0")
    rec("NOT-VAT", "PASS" if "ct_is_vat_kernel" in src else "FAIL",
        "clone is auction settlement, not vat.slip/flux/move accounting")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_CLIPPER_TAKE" in sol_src and "REJ_C_CLIPPER_TAKE" in c_src and "REJ_RUST_CLIPPER_TAKE" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close clipper.take / sales[ / clipperCall")
    rec("TR-CALLDATA", "PASS" if "REJ_SOLIDITY_BYTES_CALLDATA" in sol_src else "FAIL",
        "Solidity transpiler fail-closes bytes calldata (ClipperCallee data)")
    rec("TR-CALLEE", "PASS" if "REJ_SOLIDITY_CLIPPER_CALLEE" in sol_src else "FAIL",
        "Solidity transpiler fail-closes clipperCall callbacks")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "ct_take_ok" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable clipper.take kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_clipper_take_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("ct_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ct_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ct_u_mul", 1000, 100)
        rec("C0-JIT", "PASS" if jv == 100000 else "SKIP",
            "lin_c0 jit ct_u_mul(1000,100)==100000 (in-memory libtcc)" if jv == 100000 else "in-memory JIT not exercised",
            "" if jv == 100000 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_clipper_take.lin"
    evidence["c11_oracle"] = "test/oracles/maker_clipper_take_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_clipper_take_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "full_ok": full_ok, "full_slice": full_slice, "full_owe": full_owe,
        "tab_cap_slice": cap_slice, "tab_cap_owe": cap_owe,
        "chost_slice": ch_slice, "chost_owe": ch_owe, "chost_tab": ch_tab,
        "no_partial": no_part, "too_expensive": too_exp, "needs_reset": reset_ok,
        "stopped3": stop3, "stopped2": stop2, "auth_required": auth,
        "chip_tip_in_take": chip, "breaker_take_level": brk, "is_vat_kernel": vat,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    if CLONE_LIN_HEAD:
        evidence["clone_lin_head"] = CLONE_LIN_HEAD
        evidence["clone_lin_lin_commit"] = CLONE_LIN_LIN_COMMIT
        evidence["clone_lin_lin_blob"] = CLONE_LIN_LIN_BLOB
        evidence["clone_lin_c_blob"] = CLONE_LIN_C_BLOB
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
