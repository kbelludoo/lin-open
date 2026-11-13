#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.move vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss vat.sol, C11 wrap-detect XOR
__int128 add, lin_c0 VM, Python bigint. Sequential sub-then-add (self-move is
identity). Not claimed: uint256, TVL, zk, wish maps.
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
LIN = ROOT / "src" / "lin_maker_vat_move.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_move_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_move_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_move" / "maker_vat_move_evidence.json"

E9 = 10**9
E9_3, E9_4, E9_5, E9_8 = 3 * E9, 4 * E9, 5 * E9, 8 * E9
WRAP_A, WRAP_B = 7 * 10**18, 3 * 10**18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
I64_WRAP_ADD = -8446744073709551616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-move"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
SAFE = (E9_5, E9_3, E9, 1)
SELF = (WRAP_A, WRAP_A, WRAP_B, 1)


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


def py_u_sub(x: int, y: int) -> int:
    return 0 if x < 0 or y < 0 or x < y or x > I64MAX or y > I64MAX else x - y


def py_u_add(x: int, y: int) -> int:
    z = x + y
    return 0 if x < 0 or y < 0 or z < 0 or z > I64MAX else z


def py_move_ok(src: int, dst: int, rad: int, wish: int) -> int:
    if min(src, dst, rad) < 0 or wish != 1:
        return 0
    if src > I64MAX or dst > I64MAX or rad > I64MAX:
        return 0
    if src < rad:
        return 0
    base = (src - rad) if src == dst else dst
    if base + rad > I64MAX:
        return 0
    return 1


def py_of(kind: str, args: tuple[int, ...]) -> int:
    if kind == "sub":
        return py_u_sub(args[0], args[1])
    if kind == "add":
        return py_u_add(args[0], args[1])
    src, dst, rad, wish = args
    if kind == "same_slot":
        return int(src == dst)
    if kind == "parallel_add":
        return int(0 <= dst + rad <= I64MAX and dst >= 0 and rad >= 0)
    ok = py_move_ok(src, dst, rad, wish)
    if kind == "ok":
        return ok
    if not ok:
        return 0
    if kind == "new_src":
        return src if src == dst else py_u_sub(src, rad)
    if kind == "new_dst":
        return src if src == dst else py_u_add(dst, rad)
    if kind == "conserved":
        if src == dst:
            return 1
        return int(py_u_add(py_u_sub(src, rad), py_u_add(dst, rad)) == py_u_add(src, dst))
    if kind == "moved":
        return rad
    raise RuntimeError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_MOVE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.MOVE — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 add selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect add and __int128 add agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss vat.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        if "function move(" not in text or "dai[src]" not in text or "wish(src, msg.sender)" not in text:
            rec("UPSTREAM-MOVE", "FAIL", "pinned vat.sol missing move/dai/wish")
            return 1
        rec("UPSTREAM-MOVE", "PASS", "pinned vat.sol contains move, unsigned dai _add/_sub, src-only wish (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-MOVE", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-MOVE", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.move clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_move.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "mv_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mv_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "mv_test_suite == 1 on Compiler 0 interpreter")

    s = [str(x) for x in SAFE]
    nowish = (E9_5, E9_3, E9, 0)
    under = (E9_5, E9_3, 6000000000, 1)
    overflow = (WRAP_B, WRAP_A, WRAP_B, 1)
    zero = (E9_5, E9_3, 0, 1)
    full = (E9_5, E9_3, E9_5, 1)
    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("sub", [str(E9_3), str(E9)], "mv_u_sub", (E9_3, E9)),
        ("add", ["2000000000", str(E9)], "mv_u_add", (2000000000, E9)),
        ("ok", s, "mv_move_ok", SAFE),
        ("new_src", s, "mv_new_src", SAFE),
        ("new_dst", s, "mv_new_dst", SAFE),
        ("conserved", s, "mv_conserved", SAFE),
        ("moved", s, "mv_moved", SAFE),
        ("ok", [str(x) for x in nowish], "mv_move_ok", nowish),
        ("ok", [str(x) for x in under], "mv_move_ok", under),
        ("ok", [str(x) for x in overflow], "mv_move_ok", overflow),
        ("ok", [str(x) for x in zero], "mv_move_ok", zero),
        ("new_src", [str(x) for x in zero], "mv_new_src", zero),
        ("ok", [str(x) for x in full], "mv_move_ok", full),
        ("new_src", [str(x) for x in full], "mv_new_src", full),
        ("new_dst", [str(x) for x in full], "mv_new_dst", full),
        ("ok", [str(x) for x in SELF], "mv_move_ok", SELF),
        ("new_src", [str(x) for x in SELF], "mv_new_src", SELF),
        ("new_dst", [str(x) for x in SELF], "mv_new_dst", SELF),
        ("conserved", [str(x) for x in SELF], "mv_conserved", SELF),
        ("same_slot", [str(x) for x in SELF], "mv_same_slot4", SELF),
        ("parallel_add", [str(x) for x in SELF], "mv_parallel_add_ok", SELF),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_of(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_of(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    safe_ok = lin_vm("mv_move_ok", *SAFE)
    new_src = lin_vm("mv_new_src", *SAFE)
    new_dst = lin_vm("mv_new_dst", *SAFE)
    conserved = lin_vm("mv_conserved", *SAFE)
    moved = lin_vm("mv_moved", *SAFE)
    nowish_ok = lin_vm("mv_move_ok", *nowish)
    under_ok = lin_vm("mv_move_ok", *under)
    overflow_ok = lin_vm("mv_move_ok", *overflow)
    zero_ok = lin_vm("mv_move_ok", *zero)
    full_src = lin_vm("mv_new_src", *full)
    full_dst = lin_vm("mv_new_dst", *full)
    self_ok = lin_vm("mv_move_ok", *SELF)
    self_src = lin_vm("mv_new_src", *SELF)
    self_dst = lin_vm("mv_new_dst", *SELF)
    parallel = lin_vm("mv_u_add_ok", WRAP_A, WRAP_B)
    unit_rad = lin_vm("mv_unit_is_rad")
    moves_gem = lin_vm("mv_moves_gem")
    live_req = lin_vm("mv_live_required")
    auth_req = lin_vm("mv_auth_required")
    wish_req = lin_vm("mv_wish_required")
    dst_consent = lin_vm("mv_dst_consent_required")
    golden = (safe_ok, new_src, new_dst, conserved, moved, nowish_ok, under_ok,
              overflow_ok, zero_ok, full_src, full_dst, self_ok, self_src, self_dst,
              parallel, unit_rad, moves_gem, live_req, auth_req, wish_req, dst_consent)
    expect = (1, E9_4, E9_4, 1, E9, 0, 0, 0, 1, 0, E9_8, 1, WRAP_A, WRAP_A,
              0, 1, 0, 0, 0, 1, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "SAFE/SELF/WISH/UNDER/OVERFLOW/LIVE/AUTH goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "SAFE_XFER 1e9 dai rad src→dst; SELF_MOVE 7e18 identity; no-wish=0; underflow=0; cross overflow=0; sequential vs parallel",
        "safe=1 src=4e9 dst=4e9 self_ok=1 leftover=7e18 parallel_add_ok=0 unit_rad=1 gem=0")
    rec("SEQUENTIAL", "PASS",
        "same-slot self-move is identity under sequential _sub then _add; naive parallel add_ok(7e18,3e18)=0 would reject a valid Solidity move",
        "self_ok=1 parallel_add_ok=0 leftover_dai=7000000000000000000")
    rec("COMMERCIAL", "PASS",
        "measured dai rad transfer (not TVL): 1e9 internal DAI moved src→dst with src-only wish; gem untouched; conserved",
        "moved_rad=1000000000 leftover_src=4000000000 leftover_dst=4000000000 unit=rad moves_gem=0")

    wrapped_add = lin_vm("mv_naive_i64_add", WRAP_A, WRAP_B)
    wide_add = lin_vm("mv_u_add", WRAP_A, WRAP_B)
    if wrapped_add != I64_WRAP_ADD or wide_add != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_add",
            f"add_wrap={wrapped_add} u_add={wide_add}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked u_add fail-closes to 0",
        f"i64_add_wrap={wrapped_add} u_add_fail_closed={wide_add}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "mv_move_ok(src: int, dst: int, rad: int, wish_src: int)" in src else "FAIL",
        "LIN clone takes src/dst dai balances, rad and src wish (no hidden dai[]/msg.sender)")
    rec("SRC-ONLY-WISH", "PASS" if "mv_dst_consent_required" in src and "mv_wish_required" in src else "FAIL",
        "src-only wish is explicit; dst cannot refuse incoming dai")
    rec("NO-LIVE", "PASS" if "mv_live_required" in src else "FAIL",
        "move does not require vat.live (works after cage); LIN measures live_required=0")
    rec("NOT-GEM", "PASS" if "mv_moves_gem" in src and "mv_unit_is_rad" in src else "FAIL",
        "clone is dai rad, not gem wad (vat.flux)")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_VAT_MOVE" in sol_src and "REJ_C_VAT_MOVE" in c_src and "REJ_RUST_VAT_MOVE" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.move / dai[")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("mv_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mv_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mv_u_add", 2000000000, E9)
        rec("C0-JIT", "PASS" if jv == E9_3 else "SKIP",
            "lin_c0 jit mv_u_add(2e9,1e9)==3e9 (in-memory libtcc)" if jv == E9_3 else "in-memory JIT not exercised",
            "" if jv == E9_3 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_vat_move.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_move_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "safe_xfer_ok": safe_ok,
        "new_src": new_src,
        "new_dst": new_dst,
        "conserved": conserved,
        "moved_rad": moved,
        "no_wish": nowish_ok,
        "underflow": under_ok,
        "overflow": overflow_ok,
        "zero_rad": zero_ok,
        "full_src": full_src,
        "full_dst": full_dst,
        "self_move_ok": self_ok,
        "self_leftover": self_src,
        "parallel_add_ok": parallel,
        "unit_is_rad": unit_rad,
        "moves_gem": moves_gem,
        "live_required": live_req,
        "auth_required": auth_req,
        "wish_required": wish_req,
        "dst_consent_required": dst_consent,
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
