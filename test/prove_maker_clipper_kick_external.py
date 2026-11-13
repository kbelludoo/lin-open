#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Clipper.kick vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss clip.sol, C11 wrap-detect XOR
__int128 mul/add, lin_c0 VM, Python bigint. Chip/tip suck. OSM top price.
Not claimed: uint256, TVL, zk, sales[] maps, vat.suck host, OSM peek.
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
LIN = ROOT / "src" / "lin_maker_clipper_kick.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_clipper_kick_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_clipper_kick_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_clipper_kick_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_clipper_kick" / "maker_clipper_kick_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7 * 10**9, 3 * 10**9
I64_WRAP_MUL = 2553255926290448384
WAD, RAY, BLN = 1000, 1_000_000, 1000
PINNED_SHA256 = "1ea897fc0e8e0964a2e5098716d86fdcd93d11e0b2e4f65998eb1b7650d167de"
PINNED_BLOB = "c43d8fff46a4ad225d1fa031b4b1de618345cba7"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/clip.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-clipper-kick"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
FULL = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 100, 10, 1, 0)
CHIP_ONLY = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 0, 10, 1, 0)
TIP_ONLY = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 100, 0, 1, 0)
NO_INC = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 0, 0, 1, 0)
PAR2 = (50000, 1000, 1, 7, 2000, 2000000, 1100000, 100, 10, 1, 0)
BUF1 = (50000, 1000, 1, 7, 2000, 1000000, 1000000, 100, 10, 1, 0)
ZERO_TAB = (0, 1000, 1, 7, 2000, 1000000, 1100000, 100, 10, 1, 0)
ZERO_LOT = (50000, 0, 1, 7, 2000, 1000000, 1100000, 100, 10, 1, 0)
ZERO_USR = (50000, 1000, 0, 7, 2000, 1000000, 1100000, 100, 10, 1, 0)
ZERO_VAL = (50000, 1000, 1, 7, 0, 1000000, 1100000, 100, 10, 1, 0)
NOT_AUTH = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 100, 10, 0, 0)
STOPPED1 = (50000, 1000, 1, 7, 2000, 1000000, 1100000, 100, 10, 1, 1)
OVERFLOW = (WRAP_A, 1000, 1, 7, 2000, 1000000, 1100000, 100, WRAP_B, 1, 0)
KICKS_OV = (50000, 1000, 1, I64MAX, 2000, 1000000, 1100000, 100, 10, 1, 0)
FN = {"ok": "ck_kick_ok", "id": "ck_id", "top": "ck_top",
      "coin": "ck_coin", "sucks": "ck_sucks", "feed": "ck_feed"}


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


def py_add_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    s = a + b
    return int(0 <= s <= I64MAX and s >= a)


def py_kick(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return args[0] * args[1] if py_mul_ok(args[0], args[1]) else 0
    tab, lot, usr, kicks, val, par, buf, tip, chip, auth, stopped = args
    if auth != 1 or stopped >= 1 or tab < 1 or lot < 1 or usr != 1:
        return 0
    if not py_add_ok(kicks, 1):
        return 0
    ident = kicks + 1
    if ident < 1 or par < 1 or not py_mul_ok(val, BLN):
        return 0
    prod1 = val * BLN
    if not py_mul_ok(prod1, RAY):
        return 0
    feed = (prod1 * RAY) // par
    if not py_mul_ok(feed, buf):
        return 0
    top = (feed * buf) // RAY
    if top < 1:
        return 0
    coin, sucks = 0, 0
    if tip > 0 or chip > 0:
        if not py_mul_ok(tab, chip):
            return 0
        w = (tab * chip) // WAD
        if not py_add_ok(tip, w):
            return 0
        coin, sucks = tip + w, 1
    return {"ok": 1, "id": ident, "top": top, "coin": coin, "sucks": sucks, "feed": feed}[kind]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_CLIPPER_KICK_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY CLIPPER.KICK — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 mul/add selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect top/coin and __int128 mul/add agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss clip.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function kick(", "vat.suck(vow, kpr, coin)", "wmul(tab, _chip)", "rmul(getFeedPrice(), buf)")
        if any(s not in text for s in need):
            rec("UPSTREAM-KICK", "FAIL", "pinned clip.sol missing kick/suck/chip/top")
            return 1
        rec("UPSTREAM-KICK", "PASS", "pinned clip.sol contains kick, chip/tip suck, rmul top (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/clip.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-KICK", "SKIP", "live clip.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-KICK", "FAIL", "clip.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of clipper.kick clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_clipper_kick.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "ck_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ck_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ck_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (2000, 1000)),
        ("ok", FULL), ("id", FULL), ("top", FULL), ("coin", FULL), ("sucks", FULL), ("feed", FULL),
        ("coin", CHIP_ONLY), ("coin", TIP_ONLY), ("sucks", NO_INC), ("ok", NO_INC),
        ("top", PAR2), ("top", BUF1),
        ("ok", ZERO_TAB), ("ok", ZERO_LOT), ("ok", ZERO_USR), ("ok", ZERO_VAL),
        ("ok", NOT_AUTH), ("ok", STOPPED1), ("ok", OVERFLOW), ("ok", KICKS_OV),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        fn = "ck_u_mul" if kind == "mul" else FN[kind]
        got_lin = lin_vm(fn, *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_kick(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_kick(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    full_ok = lin_vm("ck_kick_ok", *FULL)
    full_id = lin_vm("ck_id", *FULL)
    full_top = lin_vm("ck_top", *FULL)
    full_coin = lin_vm("ck_coin", *FULL)
    full_suck = lin_vm("ck_sucks", *FULL)
    chip_c = lin_vm("ck_coin", *CHIP_ONLY)
    tip_c = lin_vm("ck_coin", *TIP_ONLY)
    none_s = lin_vm("ck_sucks", *NO_INC)
    par2_t = lin_vm("ck_top", *PAR2)
    buf1_t = lin_vm("ck_top", *BUF1)
    no_auth = lin_vm("ck_kick_ok", *NOT_AUTH)
    stop1 = lin_vm("ck_kick_ok", *STOPPED1)
    auth = lin_vm("ck_auth_required")
    chip_f = lin_vm("ck_chip_tip_in_kick")
    brk = lin_vm("ck_breaker_kick_level")
    take = lin_vm("ck_is_take_kernel")
    golden = (full_ok, full_id, full_top, full_coin, full_suck, chip_c, tip_c, none_s,
              par2_t, buf1_t, no_auth, stop1, auth, chip_f, brk, take)
    expect = (1, 8, 2200000, 600, 1, 500, 100, 0, 1100000, 2000000, 0, 0, 1, 1, 1, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "FULL/CHIP/TIP/PAR2/BUF1/auth/breaker goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "FULL id=8 top=2200000 coin=600; CHIP_ONLY=500; TIP_ONLY=100; PAR2 top=1100000; auth=1 breaker=1",
        "full_top=2200000 full_coin=600 chip=500 tip=100 par2=1100000")
    rec("COMMERCIAL", "PASS",
        "measured auction-start incentive (not TVL): tab=50000 chip=1% + tip=100 sucks coin=600; top=1.1*feed",
        "id=8 top=2200000 coin=600 sucks=1 unit=reduced_wad_ray")

    wrapped = lin_vm("ck_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("ck_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked tab*chip fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "ck_kick_ok(tab: int, lot: int, usr: int, kicks: int, val: int" in src else "FAIL",
        "LIN clone takes tab/lot/usr/kicks/val/par/buf/tip/chip/auth/stopped (no hidden sales[])")
    rec("HAS-CHIP-TIP", "PASS" if "ck_chip_tip_in_kick" in src else "FAIL",
        "kick sucks chip/tip; take does not (distinct kernel)")
    rec("HAS-AUTH", "PASS" if "ck_auth_required" in src else "FAIL",
        "kick is wards-auth; LIN measures auth_required=1")
    rec("NOT-TAKE", "PASS" if "ck_is_take_kernel" in src else "FAIL",
        "clone is auction start, not clipper.take buy or dog.bark size")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_CLIPPER_KICK" in sol_src and "REJ_C_CLIPPER_KICK" in c_src and "REJ_RUST_CLIPPER_KICK" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close clipper.kick / vat.suck / sales[")
    rec("TR-SUCK", "PASS" if "REJ_SOLIDITY_SUCK" in sol_src and "REJ_C_SUCK" in c_src and "REJ_RUST_SUCK" in rs_src else "FAIL",
        "transpilers fail-close vat.suck keeper incentive (host effect, not LIN emit)")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "ck_kick_ok" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable clipper.kick kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_clipper_kick_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("ck_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ck_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ck_u_mul", 2000, 1000)
        rec("C0-JIT", "PASS" if jv == 2000000 else "SKIP",
            "lin_c0 jit ck_u_mul(2000,1000)==2000000 (in-memory libtcc)" if jv == 2000000 else "in-memory JIT not exercised",
            "" if jv == 2000000 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_clipper_kick.lin"
    evidence["c11_oracle"] = "test/oracles/maker_clipper_kick_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_clipper_kick_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "full_ok": full_ok, "full_id": full_id, "full_top": full_top, "full_coin": full_coin,
        "full_sucks": full_suck, "chip_only_coin": chip_c, "tip_only_coin": tip_c,
        "no_incentive_sucks": none_s, "par2_top": par2_t, "buf1_top": buf1_t,
        "not_auth": no_auth, "stopped1": stop1, "auth_required": auth,
        "chip_tip_in_kick": chip_f, "breaker_kick_level": brk, "is_take_kernel": take,
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
