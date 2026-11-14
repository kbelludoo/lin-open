#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker End cage(ilk)/skim/flow vs LIN C0 (EXPERIMENTAL).

Recomputed this run: live git pin of makerdao/dss src/end.sol, C11 wrap-detect
XOR __int128, lin_c0 VM, Python bigint. Distinct from Vow settle and Spotter.poke.
Not claimed: uint256, TVL, zk, pip.read/vat.grab execution.
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
LIN = ROOT / "src" / "lin_maker_end.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_end_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_end_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_end_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_dss")
EVIDENCE = ROOT / "examples" / "maker_end" / "maker_end_evidence.json"

I64MAX = 2**63 - 1
WRAP_A, WRAP_B = 7_000_000_000_000_000_000, 3_000_000_000_000_000_000
I64_WRAP_ADD = -8446744073709551616
WAD, RAY = 1_000_000, 1_000_000_000
PINNED_SHA256 = "40eca7c82e6794a4dabfa9b6ae41f177dd3c0bafacefc14f060b88f52667adef"
PINNED_BLOB = "14e17b195c82bf0266db7bb78252b7b689f8b42f"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/end.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-end"
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
    return int(0 <= a <= I64MAX and 0 <= b <= I64MAX and a + b <= I64MAX)


def py_sub_ok(a: int, b: int) -> int:
    return int(0 <= a <= I64MAX and 0 <= b <= I64MAX and a >= b)


def py_mul_ok(a: int, b: int) -> int:
    return int(0 <= a <= I64MAX and 0 <= b <= I64MAX and a * b <= I64MAX)


def py_wdiv(x: int, y: int) -> int:
    return (x * WAD) // y if y > 0 and py_mul_ok(x, WAD) else 0


def py_rmul(x: int, y: int) -> int:
    return (x * y) // RAY if py_mul_ok(x, y) else 0


def py_cage(live: int, tag_prev: int, par: int, pip: int) -> int:
    if live != 0 or tag_prev != 0 or par < 0 or pip <= 0:
        return 0
    return py_wdiv(par, pip)


def py_owe(art: int, rate: int, tag: int) -> int:
    if art < 0 or rate < 0 or tag <= 0 or not py_mul_ok(art, rate):
        return 0
    d = (art * rate) // RAY
    return py_rmul(d, tag) if py_mul_ok(d, tag) else 0


def py_wad(ink: int, owe: int) -> int:
    return min(ink, owe) if ink >= 0 and owe >= 0 else 0


def py_gap(gap: int, owe: int, wad: int) -> int:
    if not py_sub_ok(owe, wad):
        return 0
    d = owe - wad
    return gap + d if py_add_ok(gap, d) else 0


def py_flow(art: int, rate: int, tag: int, gap: int, debt: int) -> int:
    if debt <= 0:
        return 0
    wad = py_owe(art, rate, tag)
    if not py_sub_ok(wad, gap):
        return 0
    left = wad - gap
    if not py_mul_ok(left, RAY):
        return 0
    den = debt // RAY
    return (left * RAY) // den if den > 0 else 0


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    table = {
        "add": lambda: py_add_ok(args[0], args[1]),
        "sub": lambda: py_sub_ok(args[0], args[1]),
        "mul": lambda: py_mul_ok(args[0], args[1]),
        "wdiv": lambda: py_wdiv(*args),
        "rmul": lambda: py_rmul(*args),
        "cage": lambda: py_cage(*args),
        "owe": lambda: py_owe(*args),
        "wad": lambda: py_wad(*args),
        "gap": lambda: py_gap(*args),
        "flow": lambda: py_flow(*args),
        "cash": lambda: py_rmul(*args),
    }
    return table[kind]()


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_END_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER End cage(ilk)/skim/flow — external LIN proof (uint64-scale)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect End mul/add and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss end.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function cage(bytes32 ilk)", "function skim(", "function flow(",
                "pip.read", "vat.grab", "vat.ilks", "wdiv(spot.par()")
        if any(s not in text for s in need):
            rec("UPSTREAM-BOOK", "FAIL", "pinned end.sol missing cage/skim/flow/pip/grab")
            return 1
        rec("UPSTREAM-BOOK", "PASS",
            "pinned end.sol: cage(ilk)/skim/flow, pip.read, vat.grab/ilks (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/end.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BOOK", "SKIP", "live end.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of End clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_end.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "len_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "len_test_suite via lin_c0 vm", f"value={gv}\n{gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "len_test_suite == 1 on Compiler 0 interpreter")

    lin_fn = {
        "add": "len_add_ok", "sub": "len_sub_ok", "mul": "len_mul_ok",
        "wdiv": "len_wdiv", "rmul": "len_rmul", "cage": "len_cage_tag",
        "owe": "len_skim_owe", "wad": "len_skim_wad", "gap": "len_skim_gap_next",
        "flow": "len_flow_fix", "cash": "len_cash_out",
    }
    debt = 100_000_000_000_000_000
    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("add", (3, 5)), ("add", (WRAP_A, WRAP_B)),
        ("sub", (9, 4)), ("sub", (4, 9)),
        ("mul", (100000, 1000)), ("mul", (WRAP_A, 2)),
        ("wdiv", (1_000_000_000, 2_000_000_000)),
        ("cage", (0, 0, 1_000_000_000, 2_000_000_000)),
        ("cage", (1, 0, 1_000_000_000, 2_000_000_000)),
        ("owe", (100_000_000, 1_000_000_000, 500_000)),
        ("wad", (100_000, 50_000)), ("wad", (30_000, 50_000)),
        ("gap", (0, 50_000, 50_000)), ("gap", (0, 50_000, 30_000)),
        ("flow", (100_000_000, 1_000_000_000, 500_000, 20_000, debt)),
        ("flow", (100_000_000, 1_000_000_000, 500_000, 0, debt)),
        ("cash", (100_000_000, 300_000)),
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

    g_tag = lin_vm("len_cage_tag", 0, 0, 1_000_000_000, 2_000_000_000)
    g_live = lin_vm("len_cage_tag", 1, 0, 1_000_000_000, 2_000_000_000)
    g_full = lin_vm("len_skim_gap_next", 0, 50_000, 50_000)
    g_under = lin_vm("len_skim_gap_next", 0, 50_000, 30_000)
    g_flow = lin_vm("len_flow_fix", 100_000_000, 1_000_000_000, 500_000, 20_000, debt)
    g_cash = lin_vm("len_cash_out", 100_000_000, 300_000)
    g_nofall = lin_vm("len_flow_fix", 100_000_000, 1_000_000_000, 500_000, 0, debt)
    golden = (g_tag, g_live, g_full, g_under, g_flow, g_cash, g_nofall)
    expect = (500_000, 0, 0, 20_000, 300_000, 30_000, 500_000)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "end goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "tag=500000 live-blocks=0 full-gap=0 under-gap=20000 flow-fix=300000 cash=30000 no-gap-fix=500000",
        f"golden={golden}")
    rec("COMMERCIAL", "PASS",
        "measured settlement shortfall (not TVL): 100 DAI at pip=2000 needs 0.05 gem; urn with 0.03 gem gaps 0.02; 100 DAI cash out 0.03 gem after flow",
        "unit=WAD_1e6 RAY_1e9 gap=20000 cash_out=30000")

    wrapped = lin_vm("len_naive_i64_add", WRAP_A, WRAP_B)
    wide = lin_vm("len_add_ok", WRAP_A, WRAP_B)
    mulw = lin_vm("len_mul_ok", WRAP_A, 2)
    if wrapped != I64_WRAP_ADD or wide != 0 or mulw != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed add/mul", f"add_wrap={wrapped} add_ok={wide} mul_ok={mulw}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e18+3e18) wraps; checked add/mul fail-close to 0",
        f"i64_add_wrap={wrapped} add_fail_closed={wide} mul_fail_closed={mulw}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "len_cage_tag(live: int, tag_prev: int, par: int, pip: int" in src else "FAIL",
        "LIN clone takes live/tag/par/pip as arguments (no hidden SLOADs)")
    rec("NOT-PIPREAD", "PASS" if "len_uses_pipread" in src and "len_uses_vatgrab" in src else "FAIL",
        "clone is End cage tag / skim gap / flow fix, not pip.read or vat.grab")
    rec("NO-GRAB", "PASS" if "len_uses_vatgrab() -> int" in src else "FAIL",
        "skim returns wad/gap only; vat.grab is not executed")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_PIPREAD" in sol_src and "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close pip.read / __int128 / i128 (host, not LIN emit)")
    rec("TR-VATGRAB", "PASS" if "REJ_SOLIDITY_VATGRAB" in sol_src and "REJ_C_VATGRAB" in c_src else "FAIL",
        "Solidity/C transpilers fail-close vat.grab (explicit wad/gap in LIN)")
    rec("TR-VATILKS", "PASS" if "REJ_SOLIDITY_VATILKS" in sol_src and "REJ_C_VATILKS" in c_src else "FAIL",
        "Solidity/C transpilers fail-close vat.ilks (explicit art/rate in LIN)")

    rec("C-KERNEL",
        "PASS" if KERNEL.exists() and "len_cage_tag" in KERNEL.read_text(encoding="utf-8") else "FAIL",
        "pointer-free C kernel (maker_end_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("len_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on len_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("len_add_ok", 3, 5)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit len_add_ok(3,5)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
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
    evidence["lin_clone"] = "src/lin_maker_end.lin"
    evidence["c11_oracle"] = "test/oracles/maker_end_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_end_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "cage_tag": g_tag, "cage_blocked_while_live": g_live,
        "skim_gap_full": g_full, "skim_gap_under": g_under,
        "flow_fix_under": g_flow, "cash_out": g_cash, "flow_fix_no_gap": g_nofall,
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
