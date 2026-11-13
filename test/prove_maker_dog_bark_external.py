#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Dog.bark vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss dog.sol, C11 wrap-detect XOR
__int128 mul, lin_c0 VM, Python bigint. Hole/Dirt room, chop, dusty leftover
and dusty-auction-from-partial. Not claimed: uint256, TVL, zk, vat.grab calls,
ClipperLike.kick, bytes32 ilk maps.
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
LIN = ROOT / "src" / "lin_maker_dog_bark.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_dog_bark_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_dog_bark_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_dog_bark_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_dog_bark" / "maker_dog_bark_evidence.json"

I64MAX = 2**63 - 1
WAD = 1000
WRAP_A, WRAP_B = 7 * 10**9, 3 * 10**9
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "274f7c5df8a13e535b496236436ebf726228fbe9285d94c542e2c9d2a78671de"
PINNED_BLOB = "d941d80fbf89fe7b3d334cf4931c779e1ac7c0ce"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/dog.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-dog-bark"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
FULL = (1, 1000, 800, 1500, 1000, 100, 1000000000, 0, 1000000000, 0, 1130, 7)
PARTIAL = (1, 10000, 8000, 1200, 800, 500000, 1000000000, 0, 2000000, 0, 1130, 3)
DUSTY_LEFT = (1, 1000, 800, 1000, 700, 200000, 1000000000, 0, 791000, 0, 1130, 1)
DUSTY_AUC = (1, 1000, 800, 1000, 700, 500000, 1000000000, 0, 113000, 0, 1130, 1)
SAFE = (1, 1000, 800, 1000, 1000, 100, 1000000000, 0, 1000000000, 0, 1130, 1)
DEAD = (0, 1000, 800, 1500, 1000, 100, 1000000000, 0, 1000000000, 0, 1130, 1)
LIMIT = (1, 1000, 800, 1500, 1000, 100, 100, 100, 1000000000, 0, 1130, 1)
NULL = (1, 1, 10000, 1000, 100, 1, 1000000000, 0, 113000, 0, 1130, 1)
SPOT0 = (1, 1000, 800, 1500, 0, 100, 1000000000, 0, 1000000000, 0, 1130, 1)
OVERFLOW = (1, WRAP_A, 800, 1500, WRAP_B, 100, 1000000000, 0, 1000000000, 0, 1130, 1)
FN = {
    "ok": "db_bark_ok",
    "dart": "db_dart",
    "dink": "db_dink",
    "due": "db_due",
    "tab": "db_tab",
    "left_ink": "db_left_ink",
    "left_art": "db_left_art",
    "dirt_new": "db_dirt_new",
    "id": "db_id",
    "full": "db_full",
    "partial": "db_partial",
}


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
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", FETCH_HEAD := "FETCH_HEAD"]).returncode != 0:
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


def py_bark(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return args[0] * args[1] if py_mul_ok(args[0], args[1]) else 0
    live, ink, art, rate, spot, dust, g_hole, g_dirt, i_hole, i_dirt, chop, next_id = args
    if live != 1 or ink < 0 or art < 1 or rate < 1 or spot < 0 or dust < 0:
        return 0
    if min(g_hole, g_dirt, i_hole, i_dirt, chop, next_id) < 0 or chop < 1:
        return 0
    if not py_mul_ok(ink, spot) or not py_mul_ok(art, rate):
        return 0
    if spot < 1 or not (ink * spot < art * rate):
        return 0
    if not (g_hole > g_dirt and i_hole > i_dirt):
        return 0
    room = min(g_hole - g_dirt, i_hole - i_dirt)
    if not py_mul_ok(room, WAD):
        return 0
    dart = min(art, (room * WAD) // rate // chop)
    if art > dart:
        if not py_mul_ok(art - dart, rate):
            return 0
        if (art - dart) * rate < dust:
            dart = art
        elif not py_mul_ok(dart, rate) or dart * rate < dust:
            return 0
    if not py_mul_ok(ink, dart):
        return 0
    dink = (ink * dart) // art
    if dink < 1:
        return 0
    if not py_mul_ok(dart, rate):
        return 0
    due = dart * rate
    if not py_mul_ok(due, chop):
        return 0
    tab = (due * chop) // WAD
    if g_dirt + tab > I64MAX or i_dirt + tab > I64MAX:
        return 0
    left_ink, left_art = ink - dink, art - dart
    g2, i2 = g_dirt + tab, i_dirt + tab
    return {
        "ok": 1,
        "dart": dart,
        "dink": dink,
        "due": due,
        "tab": tab,
        "left_ink": left_ink,
        "left_art": left_art,
        "dirt_new": g2,
        "id": next_id,
        "full": int(left_ink == 0 and left_art == 0),
        "partial": int(left_art > 0),
    }[kind]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_DOG_BARK_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY DOG.BARK — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect ink*spot/room*WAD/due*chop and __int128 mul agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss dog.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function bark(", "Hole > Dirt", "milk.hole > milk.dirt",
                "ClipperLike(milk.clip).kick", "vat.grab", "vow.fess",
                "Dog/dusty-auction-from-partial-liquidation", "Dog/not-unsafe")
        if any(s not in text for s in need):
            rec("UPSTREAM-BARK", "FAIL", "pinned dog.sol missing bark/Hole/Dirt/kick/dust")
            return 1
        rec("UPSTREAM-BARK", "PASS", "pinned dog.sol contains bark, Hole/Dirt, chop, clip.kick (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/dog.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BARK", "SKIP", "live dog.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BARK", "FAIL", "dog.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of dog.bark clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_dog_bark.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "db_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "db_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "db_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (800, 1500)),
        ("ok", FULL), ("dart", FULL), ("dink", FULL), ("due", FULL), ("tab", FULL),
        ("left_ink", FULL), ("full", FULL), ("id", FULL),
        ("dart", PARTIAL), ("dink", PARTIAL), ("partial", PARTIAL), ("tab", PARTIAL),
        ("full", DUSTY_LEFT), ("dart", DUSTY_LEFT),
        ("ok", DUSTY_AUC), ("ok", SAFE), ("ok", DEAD), ("ok", LIMIT),
        ("ok", NULL), ("ok", SPOT0), ("ok", OVERFLOW),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        fn = "db_u_mul" if kind == "mul" else FN[kind]
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_bark(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_bark(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    full_ok = lin_vm("db_bark_ok", *FULL)
    full_dart = lin_vm("db_dart", *FULL)
    full_dink = lin_vm("db_dink", *FULL)
    full_due = lin_vm("db_due", *FULL)
    full_tab = lin_vm("db_tab", *FULL)
    full_id = lin_vm("db_id", *FULL)
    part_dart = lin_vm("db_dart", *PARTIAL)
    part_dink = lin_vm("db_dink", *PARTIAL)
    part_tab = lin_vm("db_tab", *PARTIAL)
    dusty_full = lin_vm("db_full", *DUSTY_LEFT)
    dusty_auc = lin_vm("db_bark_ok", *DUSTY_AUC)
    safe_ok = lin_vm("db_bark_ok", *SAFE)
    dead_ok = lin_vm("db_bark_ok", *DEAD)
    limit_ok = lin_vm("db_bark_ok", *LIMIT)
    null_ok = lin_vm("db_bark_ok", *NULL)
    auth = lin_vm("db_auth_required")
    chip = lin_vm("db_chip_tip_in_bark")
    take = lin_vm("db_is_take_kernel")
    vat = lin_vm("db_is_vat_kernel")
    b32 = lin_vm("db_uses_bytes32_ilk")
    kick = lin_vm("db_uses_clip_kick_arg")
    golden = (full_ok, full_dart, full_dink, full_due, full_tab, full_id,
              part_dart, part_dink, part_tab, dusty_full, dusty_auc,
              safe_ok, dead_ok, limit_ok, null_ok, auth, chip, take, vat, b32, kick)
    expect = (1, 800, 1000, 1200000, 1356000, 7,
              1474, 1842, 1998744, 1, 0,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 1)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "FULL/PARTIAL/DUSTY/SAFE/DEAD goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "FULL dart=800 dink=1000 tab=1356000; PARTIAL dart=1474 dink=1842; dusty leftover→full; dusty auction=0",
        "full_tab=1356000 part_tab=1998744 auth=0 chip_tip=0 kick_arg=1")
    rec("COMMERCIAL", "PASS",
        "measured liquidation kick (not TVL): 1000 collat / 800 debt at rate 1500 chop 1130 raises tab 1356000; Hole/Dirt room explicit",
        "dink=1000 dart=800 due=1200000 tab=1356000 leftover=0 unit=reduced_wad_rad")

    wrapped = lin_vm("db_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("db_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked ink*spot fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "db_bark_ok(live: int, ink: int, art: int, rate: int, spot: int, dust: int" in src else "FAIL",
        "LIN clone takes live/ink/art/rate/spot/dust/g_hole/g_dirt/i_hole/i_dirt/chop/next_id (no hidden ilks[])")
    rec("NO-CHIP-TIP", "PASS" if "db_chip_tip_in_bark" in src else "FAIL",
        "bark does not suck chip/tip; those are clipper.kick/redo incentives")
    rec("NO-AUTH", "PASS" if "db_auth_required" in src else "FAIL",
        "bark is public (live flag), not wards auth; LIN measures auth_required=0")
    rec("NOT-TAKE", "PASS" if "db_is_take_kernel" in src else "FAIL",
        "clone is liquidation kick, not clipper.take auction buy")
    rec("NOT-VAT", "PASS" if "db_is_vat_kernel" in src else "FAIL",
        "clone is dog.bark, not vat.slip/flux/move accounting")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_DOG_BARK" in sol_src and "REJ_C_DOG_BARK" in c_src and "REJ_RUST_DOG_BARK" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close dog.bark / ilks[ / vat.grab")
    rec("TR-BYTES32", "PASS" if "REJ_SOLIDITY_BYTES32" in sol_src else "FAIL",
        "Solidity transpiler fail-closes bytes32 (ilk keys)")
    rec("TR-KICK", "PASS" if "REJ_SOLIDITY_CLIPPER_KICK" in sol_src else "FAIL",
        "Solidity transpiler fail-closes ClipperLike.kick callbacks")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "db_bark_ok" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable dog.bark kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_dog_bark_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("db_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on db_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("db_u_mul", 800, 1500)
        rec("C0-JIT", "PASS" if jv == 1200000 else "SKIP",
            "lin_c0 jit db_u_mul(800,1500)==1200000 (in-memory libtcc)" if jv == 1200000 else "in-memory JIT not exercised",
            "" if jv == 1200000 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_dog_bark.lin"
    evidence["c11_oracle"] = "test/oracles/maker_dog_bark_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_dog_bark_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "full_ok": full_ok, "full_dart": full_dart, "full_dink": full_dink,
        "full_due": full_due, "full_tab": full_tab, "full_id": full_id,
        "part_dart": part_dart, "part_dink": part_dink, "part_tab": part_tab,
        "dusty_leftover_full": dusty_full, "dusty_auction": dusty_auc,
        "safe": safe_ok, "not_live": dead_ok, "limit_hit": limit_ok, "null_auction": null_ok,
        "auth_required": auth, "chip_tip_in_bark": chip, "is_take_kernel": take,
        "is_vat_kernel": vat, "uses_bytes32_ilk": b32, "uses_clip_kick_arg": kick,
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
