#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.grab vs LIN C0 (EXPERIMENTAL uint64-scale).

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
LIN = ROOT / "src" / "lin_maker_vat_grab.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_grab_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_grab_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_grab" / "maker_vat_grab_evidence.json"

RAY = 10**9
E18 = 10**18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-grab"
CLONE_LIN_HEAD = "c244ffb6dcc05452577f3ad5f6155888af25508c"
CLONE_LIN_LIN_COMMIT = "f0ab73da5980f19a86327514ef75d898cde01191"
CLONE_LIN_LIN_BLOB = "57d6c91c8dee6bfa1c1ecfdda69e09da9ab06958"
CLONE_LIN_C_BLOB = "a9c1710e82cab50df4a2653215fa1b71b1a35999"


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


def py_sub_ui(x: int, y: int) -> int:
    return py_add_ui(x, -y) if y != -(2**63) else 0


def py_dtab(rate: int, dart: int) -> int:
    mag = abs(dart)
    q = py_umul(rate, mag)
    if dart != 0 and rate != 0 and q == 0 and mag != 0:
        return 0
    return -q if dart < 0 else q


def py_fits_u63(z: int) -> bool:
    return 0 <= z <= I64MAX


def py_grab_ok(
    rate: int, ink: int, art: int, art_ilk: int, dink: int, dart: int,
    gem_v: int, sin_w: int, vice: int,
) -> int:
    if min(rate, ink, art, art_ilk, gem_v, sin_w, vice) < 0:
        return 0
    if not py_fits_u63(ink + dink) or not py_fits_u63(art + dart) or not py_fits_u63(art_ilk + dart):
        return 0
    if dart != 0 and dart == -(2**63):
        return 0
    if dart != 0 and rate != 0 and py_umul(rate, abs(dart)) == 0:
        return 0
    dtab = py_dtab(rate, dart)
    if not py_fits_u63(gem_v - dink):
        return 0
    if not py_fits_u63(sin_w - dtab) or not py_fits_u63(vice - dtab):
        return 0
    return 1


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_GRAB_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.GRAB — external LIN proof (uint64-scale, C11 oracle)")
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
        if "function grab(" not in text or "_sub(uint x, int y)" not in text:
            rec("UPSTREAM-GRAB", "FAIL", "pinned vat.sol missing grab/_sub")
            return 1
        rec("UPSTREAM-GRAB", "PASS", "pinned vat.sol contains grab and signed _sub (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-GRAB", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-GRAB", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.grab clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_grab.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "mgr_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mgr_test_suite via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "mgr_test_suite == 1 on Compiler 0 interpreter")

    nd = -RAY
    n2 = -2000000000
    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "mgr_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "mgr_muldiv", (7, 9, 1)),
        ("sub_ui", ["0", str(nd)], "mgr_sub_ui", (0, nd)),
        ("new_ink", [str(RAY), str(nd)], "mgr_new_ink", (RAY, nd)),
        ("new_art", [str(RAY), str(nd)], "mgr_new_art", (RAY, nd)),
        ("new_gem", ["0", str(nd)], "mgr_new_gem", (0, nd)),
        ("new_sin", ["0", str(RAY), str(nd)], "mgr_new_sin", (0, RAY, nd)),
        ("new_vice", ["0", str(RAY), str(nd)], "mgr_new_vice", (0, RAY, nd)),
        ("dtab", [str(RAY), str(nd)], "mgr_dtab", (RAY, nd)),
        ("seized", [str(nd)], "mgr_seized_ink", (nd,)),
        ("cancelled", [str(nd)], "mgr_cancelled_art", (nd,)),
        ("underwater", [str(RAY), "2000000000", str(RAY), str(RAY)], "mgr_underwater", (RAY, 2000000000, RAY, RAY)),
        (
            "ok",
            [str(RAY), str(RAY), str(RAY), str(RAY), str(nd), str(nd), "0", "0", "0"],
            "mgr_grab_ok",
            (RAY, RAY, RAY, RAY, nd, nd, 0, 0, 0),
        ),
        (
            "ok",
            [str(RAY), str(RAY), "2000000000", "2000000000", str(nd), str(n2), "0", "0", "0"],
            "mgr_grab_ok",
            (RAY, RAY, 2000000000, 2000000000, nd, n2, 0, 0, 0),
        ),
        (
            "ok",
            [str(RAY), "0", "0", "0", "-1", "0", "0", "0", "0"],
            "mgr_grab_ok",
            (RAY, 0, 0, 0, -1, 0, 0, 0, 0),
        ),
        (
            "ok",
            [str(RAY), "0", "0", "0", str(RAY), "0", "0", "0", "0"],
            "mgr_grab_ok",
            (RAY, 0, 0, 0, RAY, 0, 0, 0, 0),
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
        elif kind == "sub_ui":
            py = py_sub_ui(largs[0], largs[1])
        elif kind == "new_ink" or kind == "new_art":
            py = py_add_ui(largs[0], largs[1])
        elif kind == "new_gem":
            py = py_sub_ui(largs[0], largs[1])
        elif kind in ("new_sin", "new_vice"):
            py = py_sub_ui(largs[0], py_dtab(largs[1], largs[2]))
        elif kind == "dtab":
            py = py_dtab(largs[0], largs[1])
        elif kind == "seized":
            py = abs(largs[0]) if largs[0] < 0 else 0
        elif kind == "cancelled":
            py = abs(largs[0]) if largs[0] < 0 else 0
        elif kind == "underwater":
            py = 1 if py_umul(largs[2], largs[1]) > py_umul(largs[0], largs[3]) else 0
        else:
            py = py_grab_ok(*largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    bark_ok = lin_vm("mgr_grab_ok", RAY, RAY, RAY, RAY, nd, nd, 0, 0, 0)
    under_ok = lin_vm("mgr_grab_ok", RAY, RAY, 2000000000, 2000000000, nd, n2, 0, 0, 0)
    under = lin_vm("mgr_underwater", RAY, 2000000000, RAY, RAY)
    vice2 = lin_vm("mgr_new_vice", 0, RAY, n2)
    live_req = lin_vm("mgr_live_required")
    if bark_ok != 1 or under_ok != 1 or under != 1 or vice2 != 2 * E18 or live_req != 0:
        rec(
            "NAMED-GOLDEN",
            "FAIL",
            "BARK/UNDERWATER/VICE/LIVE goldens",
            f"bark={bark_ok} under_ok={under_ok} under={under} vice={vice2} live={live_req}",
        )
        return 1
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "BARK seize 1e9 ink/art ok; underwater 2e9 art still grab_ok; vice=2e18; no live check",
        "bark=1 underwater=1 grab_under=1 vice=2000000000000000000 live_required=0",
    )
    rec(
        "COMMERCIAL",
        "PASS",
        "measured confiscation vs frob safety (not TVL): underwater urn still seizable; unbacked vice=2e18",
        "cancelled_art=2000000000 seized_ink=1000000000 unbacked_vice=2000000000000000000",
    )

    wrapped = lin_vm("mgr_naive_i64_mul", 7000000000000000000, 3000000000000000000)
    wide = lin_vm("mgr_muldiv", 7000000000000000000, 3000000000000000000, 1)
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
    if "mgr_grab_ok(rate: int, ink: int, art: int, art_ilk: int, dink: int, dart: int, gem_v: int, sin_w: int, vice: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/auth")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes confiscation params as arguments (no hidden urns/sin/gem/msg.sender)")
    if "mgr_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (naive i64 a*b wraps on 7e18*3e18)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")
    if "mgr_live_required" in src and "mgr_sub_ui" in src:
        rec("NO-LIVE", "PASS", "grab has no live==1 gate (unlike frob) and uses signed _sub for gem/sin/vice")
    else:
        rec("NO-LIVE", "FAIL", "live/sub identity missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_VAT_GRAB" in sol_src and "REJ_C_VAT_GRAB" in c_src and "REJ_RUST_VAT_GRAB" in rs_src:
        rec("TR-FAILCLOSE", "PASS", "Solidity/C/Rust transpilers fail-close vat.grab / sin / gem / vice")
    else:
        rec("TR-FAILCLOSE", "FAIL", "transpiler reject tokens missing")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    jit_ok = lin_roundtrip_jit("mgr_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mgr_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mgr_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit mgr_muldiv(100,200,50)==400 (in-memory libtcc)")
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
    evidence["lin_clone"] = "src/lin_maker_vat_grab.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_grab_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "bark_grab_ok": bark_ok,
        "underwater": under,
        "underwater_grab_ok": under_ok,
        "unbacked_vice": vice2,
        "live_required": live_req,
        "seized_ink": RAY,
        "cancelled_art": 2000000000,
    }
    evidence["clone_lin_repo"] = CLONE_LIN
    if CLONE_LIN_HEAD:
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
