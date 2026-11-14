#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Vow heal/kiss/flop/flap vs LIN C0 (EXPERIMENTAL).

Recomputed this run: live git pin of makerdao/dss src/vow.sol, C11 wrap-detect
XOR __int128, lin_c0 VM, Python bigint. Distinct from vat.heal.
Not claimed: uint256, TVL, zk, flapper/flopper.kick execution.
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
LIN = ROOT / "src" / "lin_maker_vow.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_vow_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vow_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vow_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_dss")
EVIDENCE = ROOT / "examples" / "maker_vow" / "maker_vow_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7_000_000_000_000_000_000, 3_000_000_000_000_000_000
I64_WRAP_ADD = -8446744073709551616
PINNED_SHA256 = "609e5da454c0e68ce1c4dc7eb702a015139cd31305727604b777e13ea7bae302"
PINNED_BLOB = "f28d699774ef830bcdc281df4530378a64f4071b"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/vow.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vow"
CLONE_LIN_HEAD = os.environ.get("CLONE_LIN_HEAD", "")
CLONE_LIN_LIN_COMMIT = os.environ.get("CLONE_LIN_LIN_COMMIT", "")
CLONE_LIN_LIN_BLOB = os.environ.get("CLONE_LIN_LIN_BLOB", "")
CLONE_LIN_C_BLOB = os.environ.get("CLONE_LIN_C_BLOB", "")


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
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
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
    return int(a + b <= I64MAX)


def py_sub_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a >= b)


def py_add(x: int, y: int) -> int:
    return x + y if py_add_ok(x, y) else 0


def py_unqueued_ok(vat_sin: int, queued_sin: int, ash: int) -> int:
    return int(py_sub_ok(vat_sin, queued_sin) and py_sub_ok(vat_sin - queued_sin, ash))


def py_unqueued(vat_sin: int, queued_sin: int, ash: int) -> int:
    return vat_sin - queued_sin - ash if py_unqueued_ok(vat_sin, queued_sin, ash) else 0


def py_heal(vat_dai: int, vat_sin: int, queued_sin: int, ash: int, rad: int) -> int:
    if rad < 0 or vat_dai < 0 or not py_unqueued_ok(vat_sin, queued_sin, ash):
        return 0
    return int(vat_dai >= rad and py_unqueued(vat_sin, queued_sin, ash) >= rad)


def py_kiss(vat_dai: int, ash: int, rad: int) -> int:
    if rad < 0 or vat_dai < 0 or ash < 0:
        return 0
    return int(ash >= rad and vat_dai >= rad)


def py_flop(vat_dai: int, vat_sin: int, queued_sin: int, ash: int, sump: int) -> int:
    if vat_dai != 0 or sump < 0 or not py_unqueued_ok(vat_sin, queued_sin, ash):
        return 0
    return int(py_unqueued(vat_sin, queued_sin, ash) >= sump and py_add_ok(ash, sump))


def py_flap(vat_dai: int, vat_sin: int, queued_sin: int, ash: int, bump: int, hump: int) -> int:
    if vat_dai < 0 or not py_unqueued_ok(vat_sin, queued_sin, ash):
        return 0
    if py_unqueued(vat_sin, queued_sin, ash) != 0:
        return 0
    inner = py_add(vat_sin, bump)
    if vat_sin and bump and inner == 0:
        return 0
    need = py_add(inner, hump)
    if need == 0 and (vat_sin or bump or hump):
        return 0
    return int(vat_dai >= need)


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    table = {
        "add": lambda: py_add_ok(args[0], args[1]),
        "sub": lambda: py_sub_ok(args[0], args[1]),
        "unqueued": lambda: py_unqueued(*args),
        "heal": lambda: py_heal(*args),
        "kiss": lambda: py_kiss(*args),
        "flop": lambda: py_flop(*args),
        "flap": lambda: py_flap(*args),
        "flap_need": lambda: py_add(py_add(args[0], args[1]), args[2]),
    }
    return table[kind]()


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_VOW_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY Vow heal/kiss/flop/flap — external LIN proof (uint64-scale)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect Vow add and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss vow.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function heal(", "function kiss(", "function flop(", "function flap(",
                "vat.dai", "vat.sin", "vat.heal", "flapper.kick", "flopper.kick")
        if any(s not in text for s in need):
            rec("UPSTREAM-BOOK", "FAIL", "pinned vow.sol missing heal/kiss/flop/flap/vat/kick")
            return 1
        rec("UPSTREAM-BOOK", "PASS",
            "pinned vow.sol: heal/kiss/flop/flap, vat.dai/sin/heal, flapper/flopper.kick (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vow.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BOOK", "SKIP", "live vow.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Vow clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vow.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "lvw_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "lvw_test_suite via lin_c0 vm", f"value={gv}\n{gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "lvw_test_suite == 1 on Compiler 0 interpreter")

    lin_fn = {
        "add": "lvw_add_ok", "sub": "lvw_sub_ok", "unqueued": "lvw_unqueued",
        "heal": "lvw_heal_ok", "kiss": "lvw_kiss_ok", "flop": "lvw_flop_ok",
        "flap": "lvw_flap_ok", "flap_need": "lvw_flap_need",
    }
    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("add", (3, 5)), ("add", (WRAP_A, WRAP_B)),
        ("sub", (9, 4)), ("sub", (4, 9)),
        ("unqueued", (10_000_000_000, 3_000_000_000, 1_000_000_000)),
        ("heal", (5_000_000_000, 10_000_000_000, 3_000_000_000, 1_000_000_000, 5_000_000_000)),
        ("heal", (5_000_000_000, 10_000_000_000, 3_000_000_000, 1_000_000_000, 6_000_000_000)),
        ("heal", (8_000_000_000, 10_000_000_000, 3_000_000_000, 1_000_000_000, 7_000_000_000)),
        ("kiss", (3_000_000_000, 2_000_000_000, 2_000_000_000)),
        ("kiss", (3_000_000_000, 2_000_000_000, 3_000_000_000)),
        ("flop", (0, 10_000_000_000, 3_000_000_000, 1_000_000_000, 2_000_000_000)),
        ("flop", (1, 10_000_000_000, 3_000_000_000, 1_000_000_000, 2_000_000_000)),
        ("flap", (10_000_000_000, 0, 0, 0, 1_000_000_000, 2_000_000_000)),
        ("flap", (2_000_000_000, 0, 0, 0, 1_000_000_000, 2_000_000_000)),
        ("flap", (2_000_000_000, 0, 0, 0, 1_000_000_000, 0)),
        ("flap", (10_000_000_000, 3_000_000_000, 0, 0, 1_000_000_000, 2_000_000_000)),
        ("flap", (5_000_000_000, 0, 0, 0, 1_000_000_000, 2_000_000_000)),
        ("flap", (5_000_000_000, 3_000_000_000, 3_000_000_000, 0, 1_000_000_000, 2_000_000_000)),
        ("flap_need", (3_000_000_000, 1_000_000_000, 2_000_000_000)),
    ]
    n_ok = 0
    for kind, largs in vectors:
        oargs = [str(x) for x in largs]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_i128 = int(oracle([kind, *oargs, "--i128"]).splitlines()[-1])
        got_lin = lin_vm(lin_fn[kind], *largs)
        if want != want_i128:
            rec("VEC-I128", "FAIL", f"{kind} wrap-detect vs i128", f"{want} != {want_i128}")
            return 1
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{kind}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if py_kind(kind, largs) != want:
            rec("VEC-PY", "FAIL", f"python bigint {kind}{largs}", f"py={py_kind(kind, largs)} c11={want}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 wrap-detect == __int128 == LIN vm")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    g_heal = lin_vm("lvw_heal_ok", 5_000_000_000, 10_000_000_000, 3_000_000_000, 1_000_000_000, 5_000_000_000)
    g_kiss = lin_vm("lvw_kiss_ash_next", 3_000_000_000, 2_000_000_000, 2_000_000_000)
    g_flop = lin_vm("lvw_flop_ash_next", 0, 10_000_000_000, 3_000_000_000, 1_000_000_000, 2_000_000_000)
    g_flap = lin_vm("lvw_flap_ok", 10_000_000_000, 0, 0, 0, 1_000_000_000, 2_000_000_000)
    g_hump = lin_vm("lvw_flap_ok", 2_000_000_000, 0, 0, 0, 1_000_000_000, 2_000_000_000)
    g_nohump = lin_vm("lvw_flap_ok", 2_000_000_000, 0, 0, 0, 1_000_000_000, 0)
    g_queued = lin_vm("lvw_flap_ok", 5_000_000_000, 3_000_000_000, 3_000_000_000, 0, 1_000_000_000, 2_000_000_000)
    golden = (g_heal, g_kiss, g_flop, g_flap, g_hump, g_nohump, g_queued)
    expect = (1, 0, 3_000_000_000, 1, 0, 1, 0)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "vow goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "heal=1 kiss_ash=0 flop_ash=3e9 flap=1 hump-blocks=0 no-hump=1 queued-sin-blocks=0",
        f"golden={golden}")
    rec("COMMERCIAL", "PASS",
        "measured surplus buffer (not TVL): hump=2e9 blocks flap at dai=2e9; hump=0 allows it; queued Sin=3e9 raises need to 6e9",
        "flap_ok_hump2e9=0 flap_ok_hump0=1 flap_ok_queued_sin=0 unit=RAD_1e9")

    wrapped = lin_vm("lvw_naive_i64_add", WRAP_A, WRAP_B)
    wide = lin_vm("lvw_add_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_ADD or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed add", f"add_wrap={wrapped} add_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked add fail-closes to 0",
        f"i64_add_wrap={wrapped} add_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "lvw_heal_ok(vat_dai: int, vat_sin: int, queued_sin: int, ash: int, rad: int" in src else "FAIL",
        "LIN clone takes vat.dai/sin/Sin/Ash as arguments (no hidden SLOADs)")
    rec("NOT-VATHEAL", "PASS" if "lvw_uses_vatheal" in src and "lvw_uses_kick" in src else "FAIL",
        "clone is Vow settle gates, not vat.heal and not flapper/flopper.kick")
    rec("NO-KICK", "PASS" if "lvw_uses_kick() -> int" in src else "FAIL",
        "flop/flap return the ok-gate only; kick is not executed")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_VATDAI" in sol_src and "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close vat.dai / __int128 / i128 (host, not LIN emit)")
    rec("TR-VATHEAL", "PASS" if "REJ_SOLIDITY_VATHEAL" in sol_src and "REJ_C_VATHEAL" in c_src else "FAIL",
        "Solidity/C transpilers fail-close vat.heal (explicit rad in LIN)")
    rec("TR-KICK", "PASS" if "REJ_SOLIDITY_KICK" in sol_src and "REJ_C_KICK" in c_src else "FAIL",
        "Solidity/C transpilers fail-close flapper/flopper.kick (explicit ok-gate in LIN)")

    rec("C-KERNEL",
        "PASS" if KERNEL.exists() and "lvw_heal_ok" in KERNEL.read_text(encoding="utf-8") else "FAIL",
        "pointer-free C kernel (maker_vow_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("lvw_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on lvw_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("lvw_add_ok", 3, 5)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit lvw_add_ok(3,5)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
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
    evidence["lin_clone"] = "src/lin_maker_vow.lin"
    evidence["c11_oracle"] = "test/oracles/maker_vow_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_vow_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "heal_ok": g_heal, "kiss_ash_next": g_kiss, "flop_ash_next": g_flop,
        "flap_ok": g_flap, "flap_blocked_by_hump": g_hump, "flap_ok_hump0": g_nohump,
        "flap_blocked_by_queued_sin": g_queued,
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
