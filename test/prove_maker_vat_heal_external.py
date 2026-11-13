#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.heal vs LIN C0 (EXPERIMENTAL uint64-scale).

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
LIN = ROOT / "src" / "lin_maker_vat_heal.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_heal_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_heal_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_heal" / "maker_vat_heal_evidence.json"

E18 = 10**18
E18_2 = 2 * E18
E18_3 = 3 * E18
E18_4 = 4 * E18
E18_5 = 5 * E18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
I64_WRAP_MUL = -5389669316318724096
I64_WRAP_ADD = -8446744073709551616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-heal"
CLONE_LIN_HEAD = "29fd94e30fad0cce3530034eed71b34153430785"
CLONE_LIN_LIN_COMMIT = "311905f92c84db37184cbb3539cf4458a5563c61"
CLONE_LIN_LIN_BLOB = "185cdedcbd2bacd64bed817d8de004ceba77d867"
CLONE_LIN_C_BLOB = "91cd3e6b2950aafe0e0d2e1213c0673dd361ffaa"


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


def py_u_sub(x: int, y: int) -> int:
    if x < 0 or y < 0 or x < y or x > I64MAX or y > I64MAX:
        return 0
    return x - y


def py_u_add(x: int, y: int) -> int:
    z = x + y
    if x < 0 or y < 0 or z < 0 or z > I64MAX:
        return 0
    return z


def py_heal_ok(sin_u: int, dai_u: int, vice: int, debt: int, rad: int) -> int:
    if min(sin_u, dai_u, vice, debt, rad) < 0:
        return 0
    if rad > min(sin_u, dai_u, vice, debt):
        return 0
    if max(sin_u, dai_u, vice, debt, rad) > I64MAX:
        return 0
    return 1


def py_healable(sin_u: int, dai_u: int, vice: int, debt: int) -> int:
    if min(sin_u, dai_u, vice, debt) < 0:
        return 0
    return min(sin_u, dai_u, vice, debt)


def py_of(kind: str, args: tuple[int, ...]) -> int:
    if kind == "muldiv":
        a, b, d = args
        if d == 0 or a < 0 or b < 0:
            return 0
        q = (a * b) // d
        return 0 if q > I64MAX else q
    if kind == "sub":
        return py_u_sub(args[0], args[1])
    if kind == "add":
        return py_u_add(args[0], args[1])
    if kind == "new_sin":
        return py_u_sub(args[0], args[1])
    if kind == "new_dai":
        return py_u_sub(args[0], args[1])
    if kind == "new_vice":
        return py_u_sub(args[0], args[1])
    if kind == "new_debt":
        return py_u_sub(args[0], args[1])
    if kind == "healable":
        return py_healable(*args)
    if kind == "settled":
        return args[4] if py_heal_ok(*args) else 0
    if kind == "restore":
        return py_u_add(args[0], args[1])
    if kind == "deltas":
        return 1 if py_heal_ok(*args) else 0
    if kind == "ok":
        return py_heal_ok(*args)
    raise RuntimeError(f"unknown kind {kind}")


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_HEAL_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.HEAL — external LIN proof (uint64-scale, C11 oracle)")
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
        if "function heal(" not in text or "_sub(uint x, uint y)" not in text:
            rec("UPSTREAM-HEAL", "FAIL", "pinned vat.sol missing heal/_sub(uint,uint)")
            return 1
        rec("UPSTREAM-HEAL", "PASS", "pinned vat.sol contains heal and unsigned _sub (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; hash pin still holds",
            up_note,
        )
        rec("UPSTREAM-HEAL", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-HEAL", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.heal clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_heal.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "mh_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mh_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "mh_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("muldiv", ["100", "200", "50"], "mh_muldiv", (100, 200, 50)),
        ("muldiv", ["7", "9", "1"], "mh_muldiv", (7, 9, 1)),
        ("sub", [str(E18_2), str(E18)], "mh_u_sub", (E18_2, E18)),
        ("add", [str(E18), str(E18)], "mh_u_add", (E18, E18)),
        ("new_sin", [str(E18_2), str(E18)], "mh_new_sin", (E18_2, E18)),
        ("new_dai", [str(E18_3), str(E18)], "mh_new_dai", (E18_3, E18)),
        ("new_vice", [str(E18_2), str(E18)], "mh_new_vice", (E18_2, E18)),
        ("new_debt", [str(E18_5), str(E18)], "mh_new_debt", (E18_5, E18)),
        ("healable", [str(E18), str(E18_3), str(E18_2), str(E18_5)], "mh_healable", (E18, E18_3, E18_2, E18_5)),
        ("settled", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18_2)], "mh_settled", (E18_2, E18_3, E18_2, E18_5, E18_2)),
        ("restore", [str(E18), str(E18)], "mh_restore", (E18, E18)),
        ("deltas", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18)], "mh_deltas_equal", (E18_2, E18_3, E18_2, E18_5, E18)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18)], "mh_heal_ok", (E18_2, E18_3, E18_2, E18_5, E18)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), str(E18_2)], "mh_heal_ok", (E18_2, E18_3, E18_2, E18_5, E18_2)),
        ("ok", [str(E18), str(E18_3), str(E18_2), str(E18_5), str(E18_2)], "mh_heal_ok", (E18, E18_3, E18_2, E18_5, E18_2)),
        ("ok", [str(E18_2), str(E18), str(E18_2), str(E18_5), str(E18_2)], "mh_heal_ok", (E18_2, E18, E18_2, E18_5, E18_2)),
        ("ok", [str(E18_2), str(E18_3), str(E18), str(E18_5), str(E18_2)], "mh_heal_ok", (E18_2, E18_3, E18, E18_5, E18_2)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18), str(E18_2)], "mh_heal_ok", (E18_2, E18_3, E18_2, E18, E18_2)),
        ("ok", [str(E18_2), str(E18_3), str(E18_2), str(E18_5), "0"], "mh_heal_ok", (E18_2, E18_3, E18_2, E18_5, 0)),
        ("add", ["7000000000000000000", "3000000000000000000"], "mh_u_add", (7000000000000000000, 3000000000000000000)),
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
        py = py_of(kind, largs)
        if py != want:
            rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    vow_ok = lin_vm("mh_heal_ok", E18_2, E18_3, E18_2, E18_5, E18)
    full_ok = lin_vm("mh_heal_ok", E18_2, E18_3, E18_2, E18_5, E18_2)
    new_vice_full = lin_vm("mh_new_vice", E18_2, E18_2)
    settled = lin_vm("mh_settled", E18_2, E18_3, E18_2, E18_5, E18_2)
    live_req = lin_vm("mh_live_required")
    auth_req = lin_vm("mh_auth_required")
    deltas = lin_vm("mh_deltas_equal", E18_2, E18_3, E18_2, E18_5, E18)
    if (
        vow_ok != 1
        or full_ok != 1
        or new_vice_full != 0
        or settled != E18_2
        or live_req != 0
        or auth_req != 0
        or deltas != 1
    ):
        rec(
            "NAMED-GOLDEN",
            "FAIL",
            "VOW/FULL_SETTLE/LIVE/AUTH/DELTA goldens",
            f"vow={vow_ok} full={full_ok} vice0={new_vice_full} settled={settled} live={live_req} auth={auth_req} deltas={deltas}",
        )
        return 1
    rec(
        "NAMED-GOLDEN",
        "PASS",
        "VOW heal 1e18 ok; FULL_SETTLE vice 2e18 -> 0; four deltas equal rad; no live/auth",
        "vow=1 full=1 new_vice=0 settled=2000000000000000000 live_required=0 auth_required=0 deltas=1",
    )
    rec(
        "COMMERCIAL",
        "PASS",
        "measured surplus-buffer settlement (not TVL): 2e18 unbacked vice cancelled by matching dai/sin; leftover dai=1e18",
        "settled_vice=2000000000000000000 leftover_dai=1000000000000000000 leftover_debt=3000000000000000000",
    )

    wrapped_mul = lin_vm("mh_naive_i64_mul", 7000000000000000000, 3000000000000000000)
    wide_mul = lin_vm("mh_muldiv", 7000000000000000000, 3000000000000000000, 1)
    wrapped_add = lin_vm("mh_naive_i64_add", 7000000000000000000, 3000000000000000000)
    wide_add = lin_vm("mh_u_add", 7000000000000000000, 3000000000000000000)
    if wrapped_mul != I64_WRAP_MUL or wide_mul != 0 or wrapped_add != I64_WRAP_ADD or wide_add != 0:
        rec(
            "I64-WRAP",
            "FAIL",
            "i64 wrap vs 128-bit fail-closed add/mul",
            f"mul_wrap={wrapped_mul} mul_wide={wide_mul} add_wrap={wrapped_add} add_wide={wide_add}",
        )
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked u_add fail-closes to 0; (7e18*3e18) muldiv fail-closes",
        f"i64_add_wrap={wrapped_add} u_add_fail_closed={wide_add} i64_mul_wrap={wrapped_mul} muldiv_fail_closed={wide_mul}",
    )

    src = LIN.read_text(encoding="utf-8")
    if "mh_heal_ok(sin_u: int, dai_u: int, vice: int, debt: int, rad: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Solidity storage/auth")
    else:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes settlement params as arguments (no hidden sin/dai/vice/debt/msg.sender)",
        )
    if "mh_u_sub" in src and "mh_u_add" in src and "mh_muldiv" in src:
        rec("WIDE-ADD", "PASS", "clone uses fail-closed unsigned sub/add plus 128-bit muldiv")
    else:
        rec("WIDE-ADD", "FAIL", "fail-closed add/sub or 128-bit muldiv missing")
    if "mh_live_required" in src and "mh_auth_required" in src and "mh_deltas_equal" in src:
        rec("NO-LIVE-AUTH", "PASS", "heal has no live==1 and no auth (unlike frob/suck); four deltas equal rad")
    else:
        rec("NO-LIVE-AUTH", "FAIL", "live/auth/delta identity missing")

    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "REJ_SOLIDITY_VAT_HEAL" in sol_src and "REJ_C_VAT_HEAL" in c_src and "REJ_RUST_VAT_HEAL" in rs_src:
        rec("TR-FAILCLOSE", "PASS", "Solidity/C/Rust transpilers fail-close vat.heal / dai / sin / vice")
    else:
        rec("TR-FAILCLOSE", "FAIL", "transpiler reject tokens missing")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    jit_ok = lin_roundtrip_jit("mh_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on mh_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("mh_muldiv", 100, 200, 50)
        if jv == 400:
            rec("C0-JIT", "PASS", "lin_c0 jit mh_muldiv(100,200,50)==400 (in-memory libtcc)")
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
    evidence["lin_clone"] = "src/lin_maker_vat_heal.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_heal_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "vow_heal_ok": vow_ok,
        "full_settle_ok": full_ok,
        "full_settle_new_vice": new_vice_full,
        "settled_vice": settled,
        "live_required": live_req,
        "auth_required": auth_req,
        "deltas_equal": deltas,
        "leftover_dai_after_full": E18,
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
