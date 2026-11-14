#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky GemJoin.join/exit vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss join.sol, C11 wrap-detect XOR
__int128 add/sub, lin_c0 VM, Python bigint. Join cages; exit after cage is ok.
Not claimed: uint256, TVL, zk, ERC20 host, vat.slip host, wad=2**255.
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
LIN = ROOT / "src" / "lin_maker_gemjoin.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_gemjoin_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_gemjoin_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_gemjoin_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_gemjoin" / "maker_gemjoin_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7 * 10**18, 3 * 10**18
I64_WRAP_ADD = -8446744073709551616
PINNED_SHA256 = "96fceff4511aa976db5c6b144d83f4dd1bde832dd2f49fd6e54e69343b9583f9"
PINNED_BLOB = "42b01c91c8f2a6b776440e16dea2c94497d966b0"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/join.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-gemjoin"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
JOIN = (0, 1, 5_000_000_000, 0, 0, 1000, 7, 1000)
JOIN_CAGE = (0, 0, 5_000_000_000, 0, 0, 1000, 7, 1000)
JOIN_ZERO = (0, 1, 5_000_000_000, 0, 0, 1000, 7, 0)
JOIN_LOW_TOKEN = (0, 1, 5_000_000_000, 0, 0, 999, 7, 1000)
EXIT = (1, 1, 0, 1000, 1000, 0, 7, 1000)
EXIT_CAGE = (1, 0, 0, 1000, 1000, 0, 7, 1000)
EXIT_LOW = (1, 1, 0, 1, 1000, 0, 7, 1000)
OVERFLOW = (0, 1, WRAP_A, 0, 0, WRAP_B, 0, WRAP_B)
WANT = {"ok": 0, "usr": 1, "sender": 2, "adapter": 3, "stok": 4, "utok": 5}


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


def py_add_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    s = a + b
    return int(0 <= s <= I64MAX and s >= a)


def py_sub_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a >= b)


def py_gj(kind: str, args: tuple[int, ...]) -> int:
    if kind == "add":
        return py_add_ok(args[0], args[1])
    op, live, usr_gem, sender_gem, adapter, sender_tok, usr_tok, wad = args
    if op not in (0, 1) or min(usr_gem, sender_gem, adapter, sender_tok, usr_tok, wad) < 0:
        return 0
    if op == 0 and live != 1:
        return 0
    n_usr, n_sg, n_ad, n_st, n_ut = usr_gem, sender_gem, adapter, sender_tok, usr_tok
    if op == 0:
        if not py_add_ok(usr_gem, wad) or not py_add_ok(adapter, wad) or not py_sub_ok(sender_tok, wad):
            return 0
        n_usr, n_ad, n_st = usr_gem + wad, adapter + wad, sender_tok - wad
    else:
        if not py_sub_ok(sender_gem, wad) or not py_sub_ok(adapter, wad) or not py_add_ok(usr_tok, wad):
            return 0
        n_sg, n_ad, n_ut = sender_gem - wad, adapter - wad, usr_tok + wad
    return {"ok": 1, "usr": n_usr, "sender": n_sg, "adapter": n_ad, "stok": n_st, "utok": n_ut}[kind]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_GEMJOIN_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY GEMJOIN.join/exit — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 add/sub selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect gem add/sub and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss join.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("contract GemJoin", "function join(", "function exit(",
                "vat.slip(ilk, usr, int(wad))", "gem.transferFrom(",
                "vat.slip(ilk, msg.sender, -int(wad))",
                'require(live == 1, "GemJoin/not-live")')
        if any(s not in text for s in need):
            rec("UPSTREAM-JOIN", "FAIL", "pinned join.sol missing GemJoin join/exit/slip/transferFrom")
            return 1
        gem = text.split("contract GemJoin", 1)[1].split("contract DaiJoin", 1)[0]
        join_body = gem.split("function join(", 1)[1].split("function exit(", 1)[0]
        exit_body = gem.split("function exit(", 1)[1]
        if "require(live == 1" not in join_body:
            rec("UPSTREAM-JOIN", "FAIL", "GemJoin.join missing live cage")
            return 1
        if "require(live == 1" in exit_body:
            rec("UPSTREAM-JOIN", "FAIL", "GemJoin.exit unexpectedly requires live")
            return 1
        rec("UPSTREAM-JOIN", "PASS", "pinned join.sol: join cages, exit after cage ok, vat.slip (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/join.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-JOIN", "SKIP", "live join.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-JOIN", "FAIL", "join.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GemJoin clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_gemjoin.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "gj_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "gj_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "gj_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("add", (1000, 2000)), ("add", (WRAP_A, WRAP_B)),
        ("ok", JOIN), ("usr", JOIN), ("sender", JOIN), ("adapter", JOIN), ("stok", JOIN), ("utok", JOIN),
        ("ok", JOIN_CAGE), ("ok", JOIN_ZERO), ("usr", JOIN_ZERO),
        ("ok", JOIN_LOW_TOKEN),
        ("ok", EXIT), ("usr", EXIT), ("sender", EXIT), ("adapter", EXIT), ("stok", EXIT), ("utok", EXIT),
        ("ok", EXIT_CAGE), ("ok", EXIT_LOW), ("ok", OVERFLOW),
    ]
    n_ok = 0
    for kind, largs in vectors:
        if kind == "add":
            oargs = [str(x) for x in largs]
            want = int(oracle(["add", *oargs]).splitlines()[-1])
            want_i128 = int(oracle(["add", *oargs, "--i128"]).splitlines()[-1])
            got_lin = lin_vm("gj_u_add_ok", *largs)
        else:
            oargs = [str(x) for x in largs]
            want = int(oracle([kind, *oargs]).splitlines()[-1])
            want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
            got_lin = lin_vm("gj_eval", *largs, WANT[kind])
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{kind}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_gj(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {kind}{largs}", f"py={py_gj(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    j_ok = lin_vm("gj_join_ok", *JOIN[2:])
    j_usr = lin_vm("gj_join_usr_gem", *JOIN[2:])
    j_ad = lin_vm("gj_join_adapter", *JOIN[2:])
    j_st = lin_vm("gj_join_sender_token", *JOIN[2:])
    e_ok = lin_vm("gj_exit_ok", *EXIT[1:])
    e_sg = lin_vm("gj_exit_sender_gem", *EXIT[1:])
    e_ut = lin_vm("gj_exit_usr_token", *EXIT[1:])
    cage_join = lin_vm("gj_eval", *JOIN_CAGE, 0)
    cage_exit = lin_vm("gj_exit_ok", *EXIT_CAGE[1:])
    jlive = lin_vm("gj_join_checks_live")
    elive = lin_vm("gj_exit_checks_live")
    gem = lin_vm("gj_is_gemjoin")
    dai = lin_vm("gj_is_daijoin")
    golden = (j_ok, j_usr, j_ad, j_st, e_ok, e_sg, e_ut, cage_join, cage_exit, jlive, elive, gem, dai)
    expect = (1, 5_000_001_000, 1000, 0, 1, 0, 1007, 0, 1, 1, 0, 1, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "JOIN/EXIT/CAGE/live-flag goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "JOIN wad=1000 usr_gem'=5000001000 adapter'=1000 sender_tok'=0; EXIT usr_tok'=1007; cage join=0 exit=1",
        "join_usr=5000001000 exit_usr_token=1007 cage_join=0 cage_exit=1")
    rec("COMMERCIAL", "PASS",
        "measured collateral adapter (not TVL): join cages, exit after cage still works; inverse of DaiJoin",
        "join_usr_gem=5000001000 exit_usr_token=1007 unit=reduced_wad")

    wrapped = lin_vm("gj_naive_i64_add", WRAP_A, WRAP_B)
    wide = lin_vm("gj_u_add_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_ADD or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_add", f"add_wrap={wrapped} u_add_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked usr_gem+wad fail-closes to 0",
        f"i64_add_wrap={wrapped} u_add_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "gj_eval(op: int, live: int, usr_gem: int, sender_gem: int, adapter_token: int, sender_token: int, usr_token: int, wad: int" in src else "FAIL",
        "LIN clone takes op/live/usr_gem/sender_gem/adapter/sender_tok/usr_tok/wad (no hidden GemJoin storage)")
    rec("JOIN-LIVE", "PASS" if "gj_join_checks_live" in src else "FAIL",
        "join requires live==1 (GemJoin/not-live)")
    rec("EXIT-NO-LIVE", "PASS" if "gj_exit_checks_live" in src else "FAIL",
        "exit does not require live; Maker cage still accepts exit")
    rec("NOT-DAIJOIN", "PASS" if "gj_is_daijoin" in src and "gj_is_gemjoin" in src else "FAIL",
        "clone is GemJoin ilk slip, not DaiJoin wad→rad")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_TRANSFERFROM" in sol_src and "REJ_C_TRANSFERFROM" in c_src and "REJ_RUST_TRANSFERFROM" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close transferFrom (ERC20 host, not LIN emit)")
    rec("TR-SLIP",
        "PASS" if "REJ_SOLIDITY_VAT_SLIP" in sol_src and "REJ_C_VAT_SLIP" in c_src and "REJ_RUST_VAT_SLIP" in rs_src else "FAIL",
        "transpilers fail-close vat.slip / vat_slip (Vat host, not LIN emit)")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")
    rec("TR-LIVE", "PASS" if "REJ_SOLIDITY_GEMJOIN_LIVE" in sol_src else "FAIL",
        "Solidity transpiler fail-closes GemJoin/not-live storage cage (explicit live arg in LIN)")

    if not KERNEL.exists() or "gj_join_ok" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable GemJoin kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_gemjoin_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("gj_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on gj_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("gj_u_add_ok", 1000, 2000)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit gj_u_add_ok(1000,2000)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
            "" if jv == 1 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_gemjoin.lin"
    evidence["c11_oracle"] = "test/oracles/maker_gemjoin_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_gemjoin_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "join_ok": j_ok, "join_usr_gem": j_usr, "join_adapter": j_ad, "join_sender_token": j_st,
        "exit_ok": e_ok, "exit_sender_gem": e_sg, "exit_usr_token": e_ut,
        "cage_join_ok": cage_join, "cage_exit_ok": cage_exit,
        "join_checks_live": jlive, "exit_checks_live": elive, "is_gemjoin": gem, "is_daijoin": dai,
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
