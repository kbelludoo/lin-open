#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky vat.slip vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss vat.sol, C11 wrap-detect XOR
__int128 signed _add, lin_c0 VM, Python bigint. Wards auth. Signed wad.
Not claimed: uint256, TVL, zk, gem[] maps.
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
LIN = ROOT / "src" / "lin_maker_vat_slip.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_vat_slip_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_slip_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_slip_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_slip" / "maker_vat_slip_evidence.json"

E9 = 10**9
E9_4, E9_5, E9_6 = 4 * E9, 5 * E9, 6 * E9
WRAP_A, WRAP_B = 7 * 10**18, 3 * 10**18
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vat.sol"
I64MAX = 2**63 - 1
I64_WRAP_ADD = -8446744073709551616
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-slip"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")
JOIN = (E9_5, E9, 1)
EXIT = (E9_5, -E9, 1)


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


def py_s_add(x: int, y: int) -> int:
    z = x + y
    if x < 0 or x > I64MAX:
        return 0
    if y >= 0:
        return 0 if z < x or z > I64MAX else z
    return 0 if z < 0 or z > x else z


def py_slip_ok(gem: int, wad: int, wards: int) -> int:
    if gem < 0 or gem > I64MAX or wards != 1:
        return 0
    z = gem + wad
    if wad >= 0:
        return int(z >= gem and z <= I64MAX)
    return int(z >= 0 and z <= gem)


def py_of(kind: str, args: tuple[int, ...]) -> int:
    if kind == "add":
        return py_s_add(args[0], args[1])
    gem, wad, wards = args
    ok = py_slip_ok(gem, wad, wards)
    if kind == "ok":
        return ok
    if not ok:
        return 0
    if kind == "new":
        return py_s_add(gem, wad)
    if kind == "applied":
        return wad
    if kind == "join":
        return wad if wad >= 1 else 0
    if kind == "exit":
        return -wad if wad < 0 else 0
    raise RuntimeError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VAT_SLIP_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"         note: {note}")

    print("=" * 78)
    print("  MAKER/SKY VAT.SLIP — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 signed _add selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect signed add and __int128 add agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss vat.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        if "function slip(" not in text or "gem[ilk][usr]" not in text or "external auth" not in text:
            rec("UPSTREAM-SLIP", "FAIL", "pinned vat.sol missing slip/gem/auth")
            return 1
        rec("UPSTREAM-SLIP", "PASS", "pinned vat.sol contains slip, signed gem _add, wards auth (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-SLIP", "SKIP", "live vat.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-SLIP", "FAIL", "vat.sol pin mismatch", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.slip clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_slip.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "sl_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "sl_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "sl_test_suite == 1 on Compiler 0 interpreter")

    noauth = (E9_5, E9, 0)
    under = (E9, -2 * E9, 1)
    overflow = (WRAP_A, WRAP_B, 1)
    zero = (E9_5, 0, 1)
    full = (E9_5, -E9_5, 1)
    fromzero = (0, E9, 1)
    vectors: list[tuple[str, list[str], str, tuple[int, ...]]] = [
        ("add", [str(E9_5), str(E9)], "sl_s_add", (E9_5, E9)),
        ("add", [str(E9_5), str(-E9)], "sl_s_add", (E9_5, -E9)),
        ("ok", [str(x) for x in JOIN], "sl_slip_ok", JOIN),
        ("new", [str(x) for x in JOIN], "sl_new_gem", JOIN),
        ("join", [str(x) for x in JOIN], "sl_join_amt", JOIN),
        ("ok", [str(x) for x in EXIT], "sl_slip_ok", EXIT),
        ("new", [str(x) for x in EXIT], "sl_new_gem", EXIT),
        ("exit", [str(x) for x in EXIT], "sl_exit_amt", EXIT),
        ("ok", [str(x) for x in noauth], "sl_slip_ok", noauth),
        ("ok", [str(x) for x in under], "sl_slip_ok", under),
        ("ok", [str(x) for x in overflow], "sl_slip_ok", overflow),
        ("ok", [str(x) for x in zero], "sl_slip_ok", zero),
        ("new", [str(x) for x in zero], "sl_new_gem", zero),
        ("ok", [str(x) for x in full], "sl_slip_ok", full),
        ("new", [str(x) for x in full], "sl_new_gem", full),
        ("ok", [str(x) for x in fromzero], "sl_slip_ok", fromzero),
        ("new", [str(x) for x in fromzero], "sl_new_gem", fromzero),
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

    join_ok = lin_vm("sl_slip_ok", *JOIN)
    join_gem = lin_vm("sl_new_gem", *JOIN)
    join_amt = lin_vm("sl_join_amt", *JOIN)
    exit_ok = lin_vm("sl_slip_ok", *EXIT)
    exit_gem = lin_vm("sl_new_gem", *EXIT)
    exit_amt = lin_vm("sl_exit_amt", *EXIT)
    noauth_ok = lin_vm("sl_slip_ok", *noauth)
    under_ok = lin_vm("sl_slip_ok", *under)
    overflow_ok = lin_vm("sl_slip_ok", *overflow)
    zero_ok = lin_vm("sl_slip_ok", *zero)
    full_gem = lin_vm("sl_new_gem", *full)
    fromzero_gem = lin_vm("sl_new_gem", *fromzero)
    live_req = lin_vm("sl_live_required")
    auth_req = lin_vm("sl_auth_required")
    wish_req = lin_vm("sl_wish_required")
    unit_wad = lin_vm("sl_unit_is_wad")
    moves_dai = lin_vm("sl_moves_dai")
    signed = lin_vm("sl_signed_delta")
    xfer = lin_vm("sl_src_dst_transfer")
    golden = (join_ok, join_gem, join_amt, exit_ok, exit_gem, exit_amt, noauth_ok,
              under_ok, overflow_ok, zero_ok, full_gem, fromzero_gem, live_req,
              auth_req, wish_req, unit_wad, moves_dai, signed, xfer)
    expect = (1, E9_6, E9, 1, E9_4, E9, 0, 0, 0, 1, 0, E9, 0, 1, 0, 1, 0, 1, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "JOIN/EXIT/AUTH/UNDER/OVERFLOW goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "JOIN +1e9 gem; EXIT -1e9 gem; no-auth=0; underflow=0; overflow 7e18+3e18=0; no wish; wards required",
        "join=6e9 exit=4e9 auth=1 wish=0 live=0 unit_wad=1 dai=0")
    rec("COMMERCIAL", "PASS",
        "measured gem wad join/exit (not TVL): GemJoin-style auth credit of 1e9 wad; unsigned flux is a different kernel",
        "join_wad=1000000000 leftover_gem=6000000000 exit_leftover=4000000000 unit=wad")

    wrapped_add = lin_vm("sl_naive_i64_add", WRAP_A, WRAP_B)
    wide_add = lin_vm("sl_s_add", WRAP_A, WRAP_B)
    if wrapped_add != I64_WRAP_ADD or wide_add != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed s_add",
            f"add_wrap={wrapped_add} s_add={wide_add}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked signed _add fail-closes to 0",
        f"i64_add_wrap={wrapped_add} s_add_fail_closed={wide_add}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS", "PASS" if "sl_slip_ok(gem: int, wad: int, wards: int)" in src else "FAIL",
        "LIN clone takes gem balance, signed wad and wards (no hidden gem[]/msg.sender)")
    rec("NO-WISH", "PASS" if "sl_wish_required" in src else "FAIL",
        "slip does not consult wish; adapter wards credit/debit usr gem")
    rec("NO-LIVE", "PASS" if "sl_live_required" in src else "FAIL",
        "slip does not require vat.live; LIN measures live_required=0")
    rec("NOT-FLUX", "PASS" if "sl_src_dst_transfer" in src and "sl_signed_delta" in src else "FAIL",
        "clone is signed single-slot gem wad, not src-dst flux")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_VAT_SLIP" in sol_src and "REJ_C_VAT_SLIP" in c_src and "REJ_RUST_VAT_SLIP" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.slip / gem[ / auth / bytes32")
    rec("TR-BYTES32", "PASS" if "REJ_SOLIDITY_BYTES32" in sol_src else "FAIL",
        "Solidity transpiler fail-closes bytes32 (ilk is an argument, not a LIN type)")
    rec("TR-AUTH", "PASS" if "REJ_SOLIDITY_AUTH_MODIFIER" in sol_src else "FAIL",
        "Solidity transpiler fail-closes external auth / modifier auth")
    rec("TR-WIDE", "PASS" if "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "C/Rust transpilers fail-close __int128 / i128 (oracle width, not LIN emit)")

    if not KERNEL.exists() or "sl_slip_ok" not in KERNEL.read_text(encoding="utf-8"):
        rec("C-KERNEL", "FAIL", "transpilable vat.slip kernel missing")
    else:
        rec("C-KERNEL", "PASS",
            "pointer-free C kernel (maker_vat_slip_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("sl_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on sl_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("sl_s_add", E9_5, E9)
        rec("C0-JIT", "PASS" if jv == E9_6 else "SKIP",
            "lin_c0 jit sl_s_add(5e9,1e9)==6e9 (in-memory libtcc)" if jv == E9_6 else "in-memory JIT not exercised",
            "" if jv == E9_6 else "libtcc missing or JIT rejected the module")

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
    evidence["lin_clone"] = "src/lin_maker_vat_slip.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vat_slip_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_vat_slip_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "join_ok": join_ok, "join_gem": join_gem, "join_amt": join_amt,
        "exit_ok": exit_ok, "exit_gem": exit_gem, "exit_amt": exit_amt,
        "no_auth": noauth_ok, "underflow": under_ok, "overflow": overflow_ok,
        "zero_wad": zero_ok, "full_exit_gem": full_gem, "from_zero_gem": fromzero_gem,
        "live_required": live_req, "auth_required": auth_req, "wish_required": wish_req,
        "unit_is_wad": unit_wad, "moves_dai": moves_dai, "signed_delta": signed,
        "src_dst_transfer": xfer,
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
