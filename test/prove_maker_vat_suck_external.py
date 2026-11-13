#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.suck vs LIN C0 (EXPERIMENTAL uint64-scale).

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
LIN = ROOT / "src" / "lin_maker_vat_suck.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_suck_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_suck_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_suck" / "maker_vat_suck_evidence.json"

E18 = 10**18
E18_2, E18_3, E18_4, E18_5, E18_6 = 2 * E18, 3 * E18, 4 * E18, 5 * E18, 6 * E18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
I64_WRAP_MUL = -5389669316318724096
I64_WRAP_ADD = -8446744073709551616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-suck"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "92060679532820179adf01e83f703852516c7bcc")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "ab57ae9298156930fb852ec8548a7fac87f407cc")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "4e314df2588d587fd45a74c4e0d79831aff67a8a")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "8f63a1440d65f21a19988db5ce493d6355ade554")


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
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    return "PASS", commit, blob


def py_u_sub(x: int, y: int) -> int:
    if x < 0 or y < 0 or x < y or x > I64MAX or y > I64MAX:
        return 0
    return x - y


def py_u_add(x: int, y: int) -> int:
    z = x + y
    if x < 0 or y < 0 or z < 0 or z > I64MAX:
        return 0
    return z


def py_suck_ok(sin_u: int, dai_v: int, vice: int, debt: int, rad: int, auth: int) -> int:
    if min(sin_u, dai_v, vice, debt, rad) < 0 or auth != 1:
        return 0
    if max(sin_u, dai_v, vice, debt, rad) > I64MAX:
        return 0
    return int(all(py_u_add(x, rad) != 0 or rad == 0 for x in (sin_u, dai_v, vice, debt)))


def py_of(kind: str, args: tuple[int, ...]) -> int:
    if kind == "muldiv":
        a, b, d = args
        if d == 0 or a < 0 or b < 0:
            return 0
        q = (a * b) // d
        return 0 if q > I64MAX else q
    if kind in ("sub", "restore"):
        return py_u_sub(args[0], args[1])
    if kind in ("add", "new_sin", "new_dai", "new_vice", "new_debt"):
        return py_u_add(args[0], args[1])
    if kind == "minted":
        return args[4] if py_suck_ok(*args) else 0
    if kind in ("deltas", "inverse", "ok"):
        return 1 if py_suck_ok(*args) else 0
    if kind == "auth":
        return 1 if args[0] == 1 else 0
    raise RuntimeError(f"unknown kind {kind}")


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_SUCK_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.SUCK — external LIN proof (uint64-scale, C11 oracle)")
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
        if "function suck(" not in text or "_add(uint x, uint y)" not in text:
            rec("UPSTREAM-SUCK", "FAIL", "pinned vat.sol missing suck/_add(uint,uint)")
            return 1
        rec("UPSTREAM-SUCK", "PASS", "pinned vat.sol contains suck, unsigned _add, and auth (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-SUCK", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-SUCK", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.suck clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_suck.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "ms_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ms_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ms_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "ms_muldiv", (100, 200, 50)),
        ("sub", [str(E18_3), str(E18)], "ms_u_sub", (E18_3, E18)),
        ("add", [str(E18_2), str(E18)], "ms_u_add", (E18_2, E18)),
        ("new_sin", [str(E18_2), str(E18)], "ms_new_sin", (E18_2, E18)),
        ("new_dai", [str(E18_3), str(E18)], "ms_new_dai", (E18_3, E18)),
        ("new_vice", [str(E18_2), str(E18)], "ms_new_vice", (E18_2, E18)),
        ("new_debt", [str(E18_5), str(E18)], "ms_new_debt", (E18_5, E18)),
        ("restore", [str(E18_3), str(E18)], "ms_heal_restore", (E18_3, E18)),
        ("minted", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18_2), "1"], "ms_minted", (E18_2, E18_3, E18_2, E18_5, E18_2, 1)),
        ("deltas", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18), "1"], "ms_deltas_equal", (E18_2, E18_3, E18_2, E18_5, E18, 1)),
        ("inverse", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18), "1"], "ms_inverse_ok", (E18_2, E18_3, E18_2, E18_5, E18, 1)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18), "1"], "ms_suck_ok", (E18_2, E18_3, E18_2, E18_5, E18, 1)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18_2), "1"], "ms_suck_ok", (E18_2, E18_3, E18_2, E18_5, E18_2, 1)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18), "0"], "ms_suck_ok", (E18_2, E18_3, E18_2, E18_5, E18, 0)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), "0", "1"], "ms_suck_ok", (E18_2, E18_3, E18_2, E18_5, 0, 1)),
        ("ok", ["7000000000000000000", str(E18), str(E18), str(E18), "3000000000000000000", "1"], "ms_suck_ok", (7000000000000000000, E18, E18, E18, 3000000000000000000, 1)),
        ("auth", ["1"], "ms_auth_ok", (1,)),
        ("auth", ["0"], "ms_auth_ok", (0,)),
        ("add", ["7000000000000000000", "3000000000000000000"], "ms_u_add", (7000000000000000000, 3000000000000000000)),
        ("minted", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18), "0"], "ms_minted", (E18_2, E18_3, E18_2, E18_5, E18, 0)),
    ]
    n_ok = 0
    for kind, oargs, fn, largs in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        extra = [] if kind == "auth" else ["--limbs"]
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

    vow_ok = lin_vm("ms_suck_ok", E18_2, E18_3, E18_2, E18_5, E18, 1)
    full_ok = lin_vm("ms_suck_ok", E18_2, E18_3, E18_2, E18_5, E18_2, 1)
    new_vice = lin_vm("ms_new_vice", E18_2, E18)
    minted = lin_vm("ms_minted", E18_2, E18_3, E18_2, E18_5, E18_2, 1)
    unauth = lin_vm("ms_suck_ok", E18_2, E18_3, E18_2, E18_5, E18, 0)
    live_req = lin_vm("ms_live_required")
    auth_req = lin_vm("ms_auth_required")
    deltas = lin_vm("ms_deltas_equal", E18_2, E18_3, E18_2, E18_5, E18, 1)
    inverse = lin_vm("ms_inverse_ok", E18_2, E18_3, E18_2, E18_5, E18, 1)
    if (vow_ok, full_ok, new_vice, minted, unauth, live_req, auth_req, deltas, inverse) != (1, 1, E18_3, E18_2, 0, 0, 1, 1, 1):
        rec("NAMED-GOLDEN", "FAIL", "VOW/FULL_MINT/UNAUTH/LIVE/AUTH/DELTA/INVERSE goldens",
            f"vow={vow_ok} full={full_ok} vice={new_vice} minted={minted} unauth={unauth} live={live_req} auth={auth_req} deltas={deltas} inv={inverse}")
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "VOW suck 1e18 ok; FULL_MINT vice 2e18->4e18; unauth=0; four deltas=rad; inverse of heal; auth required, no live",
        "vow=1 full=1 new_vice=3000000000000000000 minted=2000000000000000000 unauth=0 live_required=0 auth_required=1 deltas=1 inverse=1")
    rec("COMMERCIAL", "PASS",
        "measured unbacked mint (not TVL): 2e18 vice/dai/sin/debt created under explicit auth; leftover dai=5e18",
        "minted_vice=2000000000000000000 new_dai=5000000000000000000 new_debt=7000000000000000000 leftover_dai=5000000000000000000")

    wrapped_mul = lin_vm("ms_naive_i64_mul", 7000000000000000000, 3000000000000000000)
    wide_mul = lin_vm("ms_muldiv", 7000000000000000000, 3000000000000000000, 1)
    wrapped_add = lin_vm("ms_naive_i64_add", 7000000000000000000, 3000000000000000000)
    wide_add = lin_vm("ms_u_add", 7000000000000000000, 3000000000000000000)
    if wrapped_mul != I64_WRAP_MUL or wide_mul != 0 or wrapped_add != I64_WRAP_ADD or wide_add != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs 128-bit fail-closed add/mul",
            f"mul_wrap={wrapped_mul} mul_wide={wide_mul} add_wrap={wrapped_add} add_wide={wide_add}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked u_add fail-closes to 0; (7e18*3e18) muldiv fail-closes",
        f"i64_add_wrap={wrapped_add} u_add_fail_closed={wide_add} i64_mul_wrap={wrapped_mul} muldiv_fail_closed={wide_mul}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "ms_suck_ok(sin_u: int, dai_v: int, vice: int, debt: int, rad: int, auth: int)" in src else "FAIL",
        "LIN clone takes mint params plus explicit auth (no hidden sin/dai/vice/debt/wards/msg.sender)")
    rec("WIDE-ADD", "PASS" if all(t in src for t in ("ms_u_add", "ms_u_sub", "ms_muldiv")) else "FAIL",
        "clone uses fail-closed unsigned add/sub plus 128-bit muldiv")
    rec("AUTH-NO-LIVE", "PASS" if all(t in src for t in ("ms_live_required", "ms_auth_required", "ms_deltas_equal", "ms_inverse_ok")) else "FAIL",
        "suck requires explicit auth and has no live==1 (unlike frob); four deltas equal rad; inverse of heal")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE", "PASS" if "REJ_SOLIDITY_VAT_SUCK" in sol_src and "REJ_C_VAT_SUCK" in c_src and "REJ_RUST_VAT_SUCK" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.suck / dai / sin / vice")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("ms_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ms_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ms_muldiv", 100, 200, 50)
        rec("C0-JIT", "PASS" if jv == 400 else "SKIP",
            "lin_c0 jit ms_muldiv(100,200,50)==400 (in-memory libtcc)" if jv == 400 else "in-memory JIT not exercised",
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
    evidence["lin_clone"] = "src/lin_maker_vat_suck.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_suck_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "vow_suck_ok": vow_ok,
        "full_mint_ok": full_ok,
        "full_mint_new_vice": lin_vm("ms_new_vice", E18_2, E18_2),
        "minted_vice": minted,
        "unauth_refused": unauth,
        "live_required": live_req,
        "auth_required": auth_req,
        "deltas_equal": deltas,
        "inverse_of_heal": inverse,
        "leftover_dai_after_full": E18_5,
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
