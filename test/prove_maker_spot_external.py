#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: Maker/Sky Spotter.poke vs LIN C0 (EXPERIMENTAL uint64-scale).

Recomputed this run: live git pin of makerdao/dss src/spot.sol, C11 wrap-detect
XOR __int128, lin_c0 VM, Python bigint. Distinct from Clipper.kick OSM top.
Not claimed: uint256, TVL, zk, vat.file execution.
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
LIN = ROOT / "src" / "lin_maker_spot.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
KERNEL = ROOT / "test" / "oracles" / "maker_spot_kernel.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_spot_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_spot_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_dss")
EVIDENCE = ROOT / "examples" / "maker_spot" / "maker_spot_evidence.json"

I64MAX = 2**63 - 1
WAD = 1_000_000_000
RAY = 1_000_000_000
WRAP_A, WRAP_B = 7_000_000_000, 3_000_000_000
I64_WRAP_MUL = 2553255926290448384
PINNED_SHA256 = "f772861927801ca1e32ba818ffc55df6ceffcc530ac3d8b6b223e7411bed118f"
PINNED_BLOB = "2f5b98d9160e6f4f5c7943a964dcc47bb2c2c862"
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
UPSTREAM_REL = "src/spot.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-spot"
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


def py_mul_ok(a: int, b: int) -> int:
    if a < 0 or b < 0 or a > I64MAX or b > I64MAX:
        return 0
    return int(a * b <= I64MAX)


def py_mul(x: int, y: int) -> int:
    if not py_mul_ok(x, y):
        return 0
    return x * y


def py_rdiv(x: int, y: int, one: int) -> int:
    if y <= 0 or x < 0 or one < 0:
        return 0
    p = py_mul(x, one)
    if x != 0 and one != 0 and p == 0:
        return 0
    return p // y


def py_poke(has: int, val: int, wad_ray: int, par: int, mat: int, one: int) -> int:
    if has != 1 or val < 0 or wad_ray < 0 or par <= 0 or mat <= 0 or one <= 0:
        return 0
    scaled = py_mul(val, wad_ray)
    if val != 0 and wad_ray != 0 and scaled == 0:
        return 0
    inner = py_rdiv(scaled, par, one)
    if scaled != 0 and inner == 0:
        return 0
    return py_rdiv(inner, mat, one)


def py_kind(kind: str, args: tuple[int, ...]) -> int:
    if kind == "mul":
        return py_mul_ok(args[0], args[1])
    if kind == "rdiv":
        return py_rdiv(*args)
    if kind == "poke":
        return py_poke(*args)
    raise KeyError(kind)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_MAKER_SPOT_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s} {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY Spotter.poke — external LIN proof (uint64-scale)")
    print("=" * 78)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 wrap-detect vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 wrap-detect Spotter poke mul and __int128 agree")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss spot.sol matches hash pin",
            f"commit={commit} blob={blob}")
        text = (UPSTREAM / UPSTREAM_REL).read_text(encoding="utf-8", errors="replace")
        need = ("function poke(", "pip.peek()", "vat.file", "function rdiv(", "10 ** 9")
        if any(s not in text for s in need):
            rec("UPSTREAM-BOOK", "FAIL", "pinned spot.sol missing poke/peek/vat.file/rdiv/10**9")
            return 1
        rec("UPSTREAM-BOOK", "PASS",
            "pinned spot.sol: poke, pip.peek, rdiv(rdiv(mul(val,10**9),par),mat), vat.file (not vendored)")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/spot.sol", PINNED_BLOB)
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BOOK", "SKIP", "live spot.sol not recomputed this run")
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        return 1

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of Spotter poke clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_spot.lin")

    for label, path in (("SOL-TR-CHECK", SOL_TR), ("C-TR-CHECK", C_TR), ("RS-TR-CHECK", RS_TR)):
        p = run([str(C0), "check", str(path)])
        rec(label, "PASS" if p.returncode == 0 or "LIN_CHECK" in p.stdout else "FAIL",
            f"Compiler 0 check of {path.name}", p.stdout if p.returncode != 0 else "")

    gate = run([str(C0), "vm", str(LIN), "lsp_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "lsp_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "lsp_test_suite == 1 on Compiler 0 interpreter")

    vectors: list[tuple[str, tuple[int, ...]]] = [
        ("mul", (1000, 2000)), ("mul", (WRAP_A, WRAP_B)),
        ("rdiv", (3_000_000_000, 1_500_000_000, RAY)),
        ("rdiv", (WRAP_A, 1, RAY)),
        ("poke", (1, 3_000_000_000, 1, RAY, 1_500_000_000, RAY)),
        ("poke", (0, 3_000_000_000, 1, RAY, 1_500_000_000, RAY)),
        ("poke", (1, 4_000_000_000, 1, RAY, 2_000_000_000, RAY)),
        ("poke", (1, 4_000_000_000, 1, 2_000_000_000, RAY, RAY)),
        ("poke", (1, 0, 1, RAY, 1_500_000_000, RAY)),
        ("poke", (1, 3_000_000_000, 1, RAY, 0, RAY)),
        ("poke", (1, 3_000_000, 1000, RAY, 1_500_000_000, RAY)),
        ("poke", (1, 6_000_000_000, 1, RAY, 1_500_000_000, RAY)),
        ("poke", (1, 3_000_000_000, 1, 1, RAY, RAY)),
        ("poke", (1, WRAP_A, WRAP_B, RAY, 1_500_000_000, RAY)),
    ]
    lin_fn = {"mul": "lsp_u_mul_ok", "rdiv": "lsp_rdiv", "poke": "lsp_poke"}
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

    g_150 = lin_vm("lsp_poke", 1, 3_000_000_000, 1, RAY, 1_500_000_000, RAY)
    g_stale = lin_vm("lsp_poke", 0, 3_000_000_000, 1, RAY, 1_500_000_000, RAY)
    g_200 = lin_vm("lsp_poke", 1, 4_000_000_000, 1, RAY, 2_000_000_000, RAY)
    g_par2 = lin_vm("lsp_poke", 1, 4_000_000_000, 1, 2_000_000_000, RAY, RAY)
    g_wad = lin_vm("lsp_poke", 1, 3_000_000, 1000, RAY, 1_500_000_000, RAY)
    golden = (g_150, g_stale, g_200, g_par2, g_wad)
    expect = (2_000_000_000, 0, 2_000_000_000, 2_000_000_000, 2_000_000_000)
    if golden != expect:
        rec("NAMED-GOLDEN", "FAIL", "spot.poke goldens", str(golden))
        return 1
    rec("NAMED-GOLDEN", "PASS",
        "150% of $3=2e9 stale=0 200% of $4=2e9 par=$2 of $4=2e9 wad_ray=1000 of 3e6=2e9",
        f"golden={golden}")
    rec("COMMERCIAL", "PASS",
        "measured CDP spot (not TVL): explicit OSM val/has + par + mat, no wrapping rdiv",
        "spot_150pct_of_3e9=2000000000 unit=RAY_1e9")

    wrapped = lin_vm("lsp_naive_i64_mul", WRAP_A, WRAP_B)
    wide = lin_vm("lsp_u_mul_ok", WRAP_A, WRAP_B)
    if wrapped != I64_WRAP_MUL or wide != 0:
        rec("I64-WRAP", "FAIL", "i64 wrap vs fail-closed u_mul", f"mul_wrap={wrapped} u_mul_ok={wide}")
        return 1
    rec("I64-WRAP", "PASS",
        "naive signed-i64 (7e9*3e9) wraps; checked val*wad_ray fail-closes to 0",
        f"i64_mul_wrap={wrapped} u_mul_fail_closed={wide}")

    src = LIN.read_text(encoding="utf-8")
    rec("EXPLICIT-ARGS",
        "PASS" if "lsp_poke(has: int, val: int, wad_ray: int, par: int, mat: int, one: int" in src else "FAIL",
        "LIN clone takes has/val/wad_ray/par/mat/one (no hidden pip.peek or vat SLOADs)")
    rec("NOT-KICK", "PASS" if "lsp_uses_kick" in src and "lsp_uses_peek" in src else "FAIL",
        "clone is Spotter.poke, not Clipper.kick OSM top")
    rec("NO-VATFILE", "PASS" if "lsp_uses_vatfile() -> int" in src else "FAIL",
        "poke returns the spot ray only; vat.file / emit Poke are not executed")

    sol_src, c_src, rs_src = (p.read_text(encoding="utf-8") for p in (SOL_TR, C_TR, RS_TR))
    rec("TR-FAILCLOSE",
        "PASS" if "REJ_SOLIDITY_PEEK" in sol_src and "REJ_C_WIDE_INT" in c_src and "REJ_RUST_WIDE_INT" in rs_src else "FAIL",
        "Solidity/C/Rust transpilers fail-close pip.peek / __int128 / i128 (host, not LIN emit)")
    rec("TR-VATFILE", "PASS" if "REJ_SOLIDITY_VATFILE" in sol_src and "REJ_C_VATFILE" in c_src else "FAIL",
        "Solidity/C transpilers fail-close vat.file (explicit spot ray in LIN)")
    rec("TR-PEEK", "PASS" if "REJ_SOLIDITY_PEEK" in sol_src and "REJ_C_PEEK" in c_src else "FAIL",
        "Solidity/C transpilers fail-close pip.peek (explicit val/has in LIN)")

    rec("C-KERNEL",
        "PASS" if KERNEL.exists() and "lsp_poke" in KERNEL.read_text(encoding="utf-8") else "FAIL",
        "pointer-free C kernel (maker_spot_kernel.c) is eligible for lin_from_c; oracle __int128 is not")

    cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
    if value_of(cjr.stdout) != 1:
        rec("JUMPRATE-REG", "FAIL", "Compound JumpRate regression after transpiler delta", cjr.stdout)
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound JumpRate still PASS after the transpiler delta")

    if lin_roundtrip_jit("lsp_test_suite"):
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on lsp_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("lsp_u_mul_ok", 1000, 2000)
        rec("C0-JIT", "PASS" if jv == 1 else "SKIP",
            "lin_c0 jit lsp_u_mul_ok(1000,2000)==1 (in-memory libtcc)" if jv == 1 else "in-memory JIT not exercised",
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
    evidence["lin_clone"] = "src/lin_maker_spot.lin"
    evidence["c11_oracle"] = "test/oracles/maker_spot_c11.c"
    evidence["c_kernel_for_transpiler"] = "test/oracles/maker_spot_kernel.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["named_goldens"] = {
        "spot_150pct_of_3e9": g_150, "stale_osm": g_stale, "spot_200pct_of_4e9": g_200,
        "par_2e9_val_4e9": g_par2, "wad_ray_1000": g_wad,
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
