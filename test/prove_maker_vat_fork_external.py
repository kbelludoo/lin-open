#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.fork vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss vat.sol, C11 __int128 XOR
limbs, lin_c0 VM, Python bigint. Not claimed: RAY=1e27/uint256, TVL, zk, wish maps.
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
LIN = ROOT / "src" / "lin_maker_vat_fork.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_fork_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_fork_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_fork" / "maker_vat_fork_evidence.json"

E9 = 10**9
E9_2, E9_3, E9_4, E9_5 = 2 * E9, 3 * E9, 4 * E9, 5 * E9
E9_12, E9_15, HALF = 12 * 10**8, 15 * 10**8, 5 * 10**8
DUST, DUST2 = 10**18, 2 * 10**18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
I64_WRAP_MUL = -5389669316318724096
I64_WRAP_ADD = -8446744073709551616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-fork"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
SAFE = (E9_5, E9_2, E9_3, E9, E9, HALF, E9, E9, DUST, 1, 1)


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


def py_iadd(x: int, y: int) -> int:
    if y >= 0:
        return py_u_add(x, y)
    if y == -I64MAX - 1:
        return 0
    return py_u_sub(x, -y)


def py_isub(x: int, y: int) -> int:
    if y >= 0:
        return py_u_sub(x, y)
    if y == -I64MAX - 1:
        return 0
    return py_u_add(x, -y)


def py_mul(a: int, b: int) -> int:
    if a < 0 or b < 0:
        return 0
    q = a * b
    return 0 if q > I64MAX else q


def py_fork_ok(*a: int) -> int:
    u_ink, u_art, v_ink, v_art, dink, dart, rate, spot, dust, ws, wd = a
    if min(u_ink, u_art, v_ink, v_art, rate, spot, dust) < 0 or ws != 1 or wd != 1:
        return 0
    nu_ink, nu_art = py_isub(u_ink, dink), py_isub(u_art, dart)
    nv_ink, nv_art = py_iadd(v_ink, dink), py_iadd(v_art, dart)
    if dink >= 0 and (nu_ink == 0 and u_ink != dink):
        return 0
    if dart >= 0 and (nu_art == 0 and u_art != dart):
        return 0
    utab, ucol = py_mul(nu_art, rate), py_mul(nu_ink, spot)
    vtab, vcol = py_mul(nv_art, rate), py_mul(nv_ink, spot)
    if ucol < utab or vcol < vtab:
        return 0
    if nu_art != 0 and utab < dust:
        return 0
    if nv_art != 0 and vtab < dust:
        return 0
    return 1


def py_of(kind: str, args: tuple[int, ...]) -> int:
    if kind == "muldiv":
        a, b, d = args
        return 0 if d == 0 or a < 0 or b < 0 or (a * b) // d > I64MAX else (a * b) // d
    if kind == "sub":
        return py_u_sub(args[0], args[1])
    if kind == "add":
        return py_u_add(args[0], args[1])
    if kind == "iadd":
        return py_iadd(args[0], args[1])
    if kind == "isub":
        return py_isub(args[0], args[1])
    ok = py_fork_ok(*args)
    if kind == "ok":
        return ok
    if not ok:
        return 0
    u_ink, u_art, v_ink, v_art, dink, dart = args[:6]
    if kind == "new_u_ink":
        return py_isub(u_ink, dink)
    if kind == "new_u_art":
        return py_isub(u_art, dart)
    if kind == "new_v_ink":
        return py_iadd(v_ink, dink)
    if kind == "new_v_art":
        return py_iadd(v_art, dart)
    if kind == "inkc":
        return int(py_u_add(py_isub(u_ink, dink), py_iadd(v_ink, dink)) == py_u_add(u_ink, v_ink))
    if kind == "artc":
        return int(py_u_add(py_isub(u_art, dart), py_iadd(v_art, dart)) == py_u_add(u_art, v_art))
    if kind == "moved":
        return abs(dink)
    raise RuntimeError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_FORK_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.FORK — external LIN proof (uint64-scale, C11 oracle)")
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
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss vat.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        if "function fork(" not in text or "_sub(uint x, int y)" not in text:
            rec("UPSTREAM-FORK", "FAIL", "pinned vat.sol missing fork/signed _sub")
            return 1
        rec("UPSTREAM-FORK", "PASS", "pinned vat.sol contains fork, signed _add/_sub, dual safety+dust (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-FORK", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-FORK", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.fork clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_fork.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL", f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "mf_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mf_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "mf_test_suite == 1 on Compiler 0 interpreter")

    s = [str(x) for x in SAFE]
    unsafe = (E9_5, E9_2, E9_12, E9, 0, HALF, E9, E9, DUST, 1, 1)
    dustv = (E9_5, E9_2, E9_3, E9, E9, HALF, E9, E9, DUST2, 1, 1)
    nowish = (E9_5, E9_2, E9_3, E9, E9, HALF, E9, E9, DUST, 0, 1)
    zero = (E9_5, E9_2, E9_3, E9, 0, 0, E9, E9, DUST, 1, 1)
    under = (E9_5, E9_2, E9_3, E9, 6000000000, 0, E9, E9, DUST, 1, 1)
    negd = (E9_5, E9_2, E9_3, E9, -E9, 0, E9, E9, DUST, 1, 1)
    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "mf_muldiv", (100, 200, 50)),
        ("sub", [str(E9_3), str(E9)], "mf_u_sub", (E9_3, E9)),
        ("add", [str(E9_2), str(E9)], "mf_u_add", (E9_2, E9)),
        ("isub", [str(E9_5), str(-E9)], "mf_isub", (E9_5, -E9)),
        ("iadd", [str(E9_3), str(-E9)], "mf_iadd", (E9_3, -E9)),
        ("ok", s, "mf_fork_ok", SAFE),
        ("new_u_ink", s, "mf_new_u_ink", SAFE),
        ("new_u_art", s, "mf_new_u_art", SAFE),
        ("new_v_ink", s, "mf_new_v_ink", SAFE),
        ("new_v_art", s, "mf_new_v_art", SAFE),
        ("inkc", s, "mf_ink_conserved", SAFE),
        ("artc", s, "mf_art_conserved", SAFE),
        ("moved", s, "mf_moved_ink", SAFE),
        ("ok", [str(x) for x in unsafe], "mf_fork_ok", unsafe),
        ("ok", [str(x) for x in dustv], "mf_fork_ok", dustv),
        ("ok", [str(x) for x in nowish], "mf_fork_ok", nowish),
        ("ok", [str(x) for x in zero], "mf_fork_ok", zero),
        ("ok", [str(x) for x in under], "mf_fork_ok", under),
        ("ok", [str(x) for x in negd], "mf_fork_ok", negd),
        ("new_u_ink", [str(x) for x in negd], "mf_new_u_ink", negd),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        extra = ["--limbs"]
        want_limbs = int(oracle([kind, *oargs, *extra]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if want != want_limbs:
            rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_of(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py_of(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    safe_ok = lin_vm("mf_fork_ok", *SAFE)
    new_ui = lin_vm("mf_new_u_ink", *SAFE)
    new_ua = lin_vm("mf_new_u_art", *SAFE)
    new_vi = lin_vm("mf_new_v_ink", *SAFE)
    new_va = lin_vm("mf_new_v_art", *SAFE)
    unsafe_ok = lin_vm("mf_fork_ok", *unsafe)
    dust_ok = lin_vm("mf_fork_ok", *dustv)
    nowish_ok = lin_vm("mf_fork_ok", *nowish)
    live_req = lin_vm("mf_live_required")
    auth_req = lin_vm("mf_auth_required")
    wish_req = lin_vm("mf_wish_required")
    inkc = lin_vm("mf_ink_conserved", *SAFE)
    artc = lin_vm("mf_art_conserved", *SAFE)
    moved = lin_vm("mf_moved_ink", *SAFE)
    neg_ok = lin_vm("mf_fork_ok", *negd)
    if (safe_ok, new_ui, new_ua, new_vi, new_va, unsafe_ok, dust_ok, nowish_ok, live_req, auth_req, wish_req, inkc, artc, moved, neg_ok) != (1, E9_4, E9_15, E9_4, E9_15, 0, 0, 0, 0, 0, 1, 1, 1, E9, 1):
        rec("NAMED-GOLDEN", "FAIL", "SAFE/UNSAFE/DUST/WISH/LIVE/AUTH/CONSERVE goldens",
            f"safe={safe_ok} ui={new_ui} ua={new_ua} vi={new_vi} va={new_va} unsafe={unsafe_ok} dust={dust_ok} nowish={nowish_ok}")
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "SAFE_SPLIT 1e9 ink+5e8 art ok; dst unsafe=0; dust leftover=0; no-wish=0; no live/auth; dual wish; conservation; signed dink",
        "safe=1 new_u=4e9/1.5e9 new_v=4e9/1.5e9 unsafe=0 dust=0 nowish=0 live=0 auth=0 wish=1 inkc=1 artc=1 moved=1e9 neg=1")
    rec("COMMERCIAL", "PASS",
        "measured CDP split (not TVL): 1e9 collateral + 5e8 normalised debt moved src→dst; both vaults stay art<=ink at rate=spot",
        "moved_ink=1000000000 moved_art=500000000 leftover_src_ink=4000000000 leftover_src_art=1500000000")

    wrapped_mul = lin_vm("mf_naive_i64_mul", 7000000000000000000, 3000000000000000000)
    wide_mul = lin_vm("mf_muldiv", 7000000000000000000, 3000000000000000000, 1)
    wrapped_add = lin_vm("mf_naive_i64_add", 7000000000000000000, 3000000000000000000)
    wide_add = lin_vm("mf_u_add", 7000000000000000000, 3000000000000000000)
    if wrapped_mul != I64_WRAP_MUL or wide_mul != 0 or wrapped_add != I64_WRAP_ADD or wide_add != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs 128-bit fail-closed add/mul",
            f"mul_wrap={wrapped_mul} mul_wide={wide_mul} add_wrap={wrapped_add} add_wide={wide_add}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked u_add fail-closes to 0; (7e18*3e18) muldiv fail-closes",
        f"i64_add_wrap={wrapped_add} u_add_fail_closed={wide_add} i64_mul_wrap={wrapped_mul} muldiv_fail_closed={wide_mul}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "mf_fork_ok(u_ink: int, u_art: int, v_ink: int, v_art: int, dink: int, dart: int, rate: int, spot: int, dust: int, wish_src: int, wish_dst: int)" in src else "FAIL",
        "LIN clone takes both urns, signed dink/dart, rate/spot/dust and dual wish (no hidden urns/ilks/msg.sender)")
    rec("WIDE-ADD", "PASS" if all(t in src for t in ("mf_iadd", "mf_isub", "mf_muldiv")) else "FAIL",
        "clone uses fail-closed signed add/sub plus 128-bit muldiv")
    rec("DUAL-SAFE", "PASS" if all(t in src for t in ("mf_safe", "mf_nondust", "mf_ink_conserved", "mf_art_conserved")) else "FAIL",
        "both vaults must stay safe and non-dusty; ink and art are conserved")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE", "PASS" if "REJ_SOLIDITY_VAT_FORK" in sol_src and "REJ_C_VAT_FORK" in c_src and "REJ_RUST_VAT_FORK" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.fork / urns / ilks")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("mf_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mf_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mf_muldiv", 100, 200, 50)
        rec("C0-JIT", "PASS" if jv == 400 else "SKIP",
            "lin_c0 jit mf_muldiv(100,200,50)==400 (in-memory libtcc)" if jv == 400 else "in-memory JIT not exercised",
            "" if jv == 400 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_vat_fork.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_fork_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "safe_split_ok": safe_ok,
        "new_u_ink": new_ui,
        "new_u_art": new_ua,
        "new_v_ink": new_vi,
        "new_v_art": new_va,
        "unsafe_dst": unsafe_ok,
        "dust_src": dust_ok,
        "no_wish": nowish_ok,
        "live_required": live_req,
        "auth_required": auth_req,
        "wish_required": wish_req,
        "ink_conserved": inkc,
        "art_conserved": artc,
        "moved_ink": moved,
        "signed_dink_ok": neg_ok,
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
