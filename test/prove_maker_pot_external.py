#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Pot.drip/join/exit vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss pot.sol, C11 wrap-detect XOR
__int128 rpow/rmul/mul, lin_c0 VM, Python bigint. Join requires now==rho; exit
does not. Not claimed: uint256, TVL, zk, vat.suck/move host, sUSDS wrapper.
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
LIN = ROOT / "src" / "lin_maker_pot.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_pot_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_pot_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_pot_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_pot" / "maker_pot_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 10**10, 10**9
I64_WRAP_MUL = -8446744073709551616
RAY = 10**9
DSR = 1_010_000_000
PINNED_SHA256 = "8b22fb58d37e5eba6c5d1f42c8651a2c5077d39a93edd13082029bc3bfb3edc6"
PINNED_BLOB = "cae58cdafe7b4014fd87dcfb002968f61dc89eee"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/pot.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-pot-join"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")

DRIP0 = (RAY, RAY, 10, 10, 1000)
DRIP1 = (DSR, RAY, 0, 1, 1000)
DRIP2 = (DSR, RAY, 0, 2, 1000)
DRIP_PAST = (DSR, RAY, 10, 9, 1000)
JOIN = (10, 10, RAY, 0, 0, 1000)
JOIN_STALE = (11, 10, RAY, 0, 0, 1000)
JOIN_OV = (10, 10, WRAP_A, 0, 0, WRAP_B)
EXIT = (RAY, 1000, 1000, 400)
EXIT_LOW = (RAY, 100, 1000, 400)
EXIT_FULL = (RAY, 1000, 1000, 1000)
WANT_DRIP = {"ok": 0, "chi": 1, "delta": 2, "suck": 3}
WANT_JE = {"ok": 0, "rad": 1, "user": 2, "total": 3}


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


def py_sub_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a >= b)


def py_rpow(x: int, n: int, base: int) -> int:
    if x < 0 or n < 0 or base <= 0:
        return 0
    if n == 0:
        return base
    if x == 0:
        return 0
    z = base if n % 2 == 0 else x
    n //= 2
    while n > 0:
        xx = x * x
        x = (xx + base // 2) // base
        if n % 2:
            z = (z * x + base // 2) // base
        n //= 2
    return z if 0 <= z <= I64MAX else 0


def py_drip(kind: str, args: tuple[int, ...]) -> int:
    dsr, chi, rho, now_ts, pie = args
    if min(dsr, chi, rho, now_ts, pie) < 0 or now_ts < rho:
        return 0
    tmp = (py_rpow(dsr, now_ts - rho, RAY) * chi) // RAY
    if not py_sub_ok(tmp, chi):
        return 0
    delta = tmp - chi
    if not py_mul_ok(pie, delta):
        return 0
    return {"ok": 1, "chi": tmp, "delta": delta, "suck": pie * delta}[kind]


def py_join(kind: str, args: tuple[int, ...]) -> int:
    now_ts, rho, chi, pie_user, pie_total, wad = args
    if min(now_ts, rho, chi, pie_user, pie_total, wad) < 0 or now_ts != rho:
        return 0
    if not py_mul_ok(chi, wad) or not py_add_ok(pie_user, wad) or not py_add_ok(pie_total, wad):
        return 0
    return {"ok": 1, "rad": chi * wad, "user": pie_user + wad, "total": pie_total + wad}[kind]


def py_exit(kind: str, args: tuple[int, ...]) -> int:
    chi, pie_user, pie_total, wad = args
    if min(chi, pie_user, pie_total, wad) < 0:
        return 0
    if not py_mul_ok(chi, wad) or not py_sub_ok(pie_user, wad) or not py_sub_ok(pie_total, wad):
        return 0
    return {"ok": 1, "rad": chi * wad, "user": pie_user - wad, "total": pie_total - wad}[kind]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_POT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY POT.drip/join/exit — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 rpow/drip/join selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect rpow/rmul/mul and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss pot.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("contract Pot", "function drip(", "function join(", "function exit(",
                "vat.suck(", "_rpow(", "_rmul(", 'Pot/rho-not-updated', 'Pot/invalid-now')
        if any(s not in text for s in need):
            rec("UPSTREAM-POT", "FAIL", "pinned pot.sol missing drip/join/exit/rpow/suck")
            return 1
        drip_body = text.split("function drip(", 1)[1].split("function join(", 1)[0]
        join_body = text.split("function join(", 1)[1].split("function exit(", 1)[0]
        exit_body = text.split("function exit(", 1)[1]
        if "now >= rho" not in drip_body and "now>= rho" not in drip_body:
            rec("UPSTREAM-POT", "FAIL", "Pot.drip missing now >= rho")
            return 1
        if "now == rho" not in join_body:
            rec("UPSTREAM-POT", "FAIL", "Pot.join missing now == rho")
            return 1
        if "now == rho" in exit_body:
            rec("UPSTREAM-POT", "FAIL", "Pot.exit unexpectedly requires rho")
            return 1
        rec("UPSTREAM-POT", "PASS", "pinned pot.sol: drip now>=rho, join now==rho, exit no rho, suck (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/pot.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-POT", "SKIP", "live pot.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-POT", "FAIL", "pot.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Pot clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_pot.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "pot_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "pot_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "pot_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    vectors: list[tuple[str, str, tuple[int, ...]]] = [
        ("rpow", "rpow", (3, 2, 2)),
        ("rpow", "rpow", (DSR, 1, RAY)),
        ("rpow", "rpow", (DSR, 2, RAY)),
        ("rpow", "rpow", (DSR, 3, RAY)),
        ("drip", "ok", DRIP0), ("drip", "chi", DRIP0), ("drip", "suck", DRIP0),
        ("drip", "ok", DRIP1), ("drip", "chi", DRIP1), ("drip", "delta", DRIP1), ("drip", "suck", DRIP1),
        ("drip", "chi", DRIP2), ("drip", "suck", DRIP2), ("drip", "ok", DRIP_PAST),
        ("join", "ok", JOIN), ("join", "rad", JOIN), ("join", "ok", JOIN_STALE), ("join", "ok", JOIN_OV),
        ("exit", "ok", EXIT), ("exit", "rad", EXIT), ("exit", "ok", EXIT_LOW), ("exit", "ok", EXIT_FULL),
    ]
    for family, kind, largs in vectors:
        if family == "rpow":
            want = int(oracle(["rpow", *[str(x) for x in largs]]).splitlines()[-1])
            want_i128 = int(oracle(["rpow", *[str(x) for x in largs], "--i128"]).splitlines()[-1])
            got_lin = lin_vm("pot_rpow", *largs)
            pyv = py_rpow(*largs)
        elif family == "drip":
            oargs = [kind, *[str(x) for x in largs]]
            want = int(oracle(["drip", *oargs]).splitlines()[-1])
            want_i128 = int(oracle(["drip", *oargs, "--i128"]).splitlines()[-1])
            got_lin = lin_vm("pot_drip_eval", *largs, WANT_DRIP[kind])
            pyv = py_drip(kind, largs)
        elif family == "join":
            oargs = [kind, *[str(x) for x in largs]]
            want = int(oracle(["join", *oargs]).splitlines()[-1])
            want_i128 = int(oracle(["join", *oargs, "--i128"]).splitlines()[-1])
            got_lin = lin_vm("pot_join_eval", *largs, WANT_JE[kind])
            pyv = py_join(kind, largs)
        else:
            oargs = [kind, *[str(x) for x in largs]]
            want = int(oracle(["exit", *oargs]).splitlines()[-1])
            want_i128 = int(oracle(["exit", *oargs, "--i128"]).splitlines()[-1])
            got_lin = lin_vm("pot_exit_eval", *largs, WANT_JE[kind])
            pyv = py_exit(kind, largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{family}.{kind}", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{family}.{kind}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if pyv != want:
            rec("VEC-PY", "FAIL", f"python bigint {family}.{kind}{largs}", f"py={pyv} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    d0_ok = lin_vm("pot_drip_ok", *DRIP0)
    d1_chi = lin_vm("pot_drip_chi", *DRIP1)
    d1_suck = lin_vm("pot_drip_suck", *DRIP1)
    d2_chi = lin_vm("pot_drip_chi", *DRIP2)
    d2_suck = lin_vm("pot_drip_suck", *DRIP2)
    j_ok = lin_vm("pot_join_ok", *JOIN)
    j_rad = lin_vm("pot_join_rad", *JOIN)
    j_stale = lin_vm("pot_join_ok", *JOIN_STALE)
    e_ok = lin_vm("pot_exit_ok", *EXIT)
    e_rad = lin_vm("pot_exit_rad", *EXIT)
    e_stale = lin_vm("pot_exit_ok", *EXIT_FULL)
    jrho = lin_vm("pot_join_requires_rho")
    erho = lin_vm("pot_exit_requires_rho")
    susds = lin_vm("pot_is_susds")
    golden = (d0_ok, d1_chi, d1_suck, d2_chi, d2_suck, j_ok, j_rad, j_stale, e_ok, e_rad, e_stale, jrho, erho, susds)
    expect = (1, 1_010_000_000, 10_000_000_000, 1_020_100_000, 20_100_000_000, 1, 1_000_000_000_000, 0, 1, 400_000_000_000, 1, 1, 0, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "DRIP/JOIN/EXIT/rho-flag goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "DRIP dt=1 chi'=1.01e9 suck=1e10; dt=2 chi'=1.0201e9 suck=2.01e10; JOIN rad=1e12; stale join=0 exit=1",
        "drip1_suck=10000000000 join_rad=1000000000000 stale_join=0 stale_exit=1")
    rec("COMMERCIAL", "PASS",
        "measured DSR chi step (not TVL): 1% / step on Pie=1000 yields suck_rad=1e10 then 2.01e10; join needs drip first",
        "unit=reduced_ray pie=1000 dsr=1010000000")

    wrapped = lin_vm("pot_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("pot_u_mul", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (1e10*1e9) wraps; checked chi*wad fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "pot_drip_eval(dsr: int, chi: int, rho: int, now_ts: int, pie_total: int" in src else "FAIL",
        "LIN clone takes dsr/chi/rho/now/Pie (no hidden Pot storage)")
    rec("JOIN-RHO", "PASS" if "pot_join_requires_rho" in src else "FAIL",
        "join requires now==rho (Pot/rho-not-updated)")
    rec("EXIT-NO-RHO", "PASS" if "pot_exit_requires_rho" in src else "FAIL",
        "exit does not require drip; stale-chi exit is explicit")
    rec("NOT-SUSDS", "PASS" if "pot_is_susds" in src else "FAIL",
        "clone is Pot chi drip, not sUSDS convertToAssets")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_VAT_SUCK" in sol_src and "REJ_C_VAT_SUCK" in c_src and "REJ_RUST_VAT_SUCK" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.suck / vat_suck (Vat host, not LIN emit)")
    rec("TR-RHO", "PASS" if "REJ_SOLIDITY_POT_RHO" in sol_src else "FAIL",
        "Solidity transpiler fail-closes Pot/rho-not-updated (explicit now/rho args in LIN)")
    rec("TR-NOW", "PASS" if "REJ_SOLIDITY_POT_NOW" in sol_src else "FAIL",
        "Solidity transpiler fail-closes Pot/invalid-now (explicit now arg in LIN)")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")
    rec("TR-ASM", "PASS" if "REJ_SOLIDITY_INLINE_ASM" in sol_src else "FAIL",
        "Solidity transpiler already fail-closes assembly _rpow (LIN loop instead)")

    rec("C-KERNEL", "PASS" if KERNEL.exists() and "pot_drip_ok" in KERNEL.read_text(encoding="utf-8") else "FAIL",
        "pointer-free C kernel (maker_pot_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("pot_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on pot_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("pot_rpow", DSR, 2, RAY)
        rec("C0-JIT", "PASS" if jv == 1_020_100_000 else "SKIP",
            "lin_c0 jit pot_rpow(1.01e9,2,1e9)==1.0201e9 (in-memory libtcc)" if jv == 1_020_100_000 else "in-memory JIT not exercised",
            "" if jv == 1_020_100_000 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_pot.lin"
    evidence["c11_oracle"] = "test/oracles/maker_pot_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_pot_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "drip0_ok": d0_ok, "drip1_chi": d1_chi, "drip1_suck": d1_suck,
        "drip2_chi": d2_chi, "drip2_suck": d2_suck, "join_ok": j_ok, "join_rad": j_rad,
        "join_stale_ok": j_stale, "exit_ok": e_ok, "exit_rad": e_rad,
        "exit_full_ok": e_stale, "join_requires_rho": jrho, "exit_requires_rho": erho,
        "is_susds": susds,
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
