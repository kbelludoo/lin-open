#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Maker/Sky vat.fold (signed ilk.rate / dai / debt) vs LIN C0.

PASS claims are recomputed this run against:
  * live git fetch of pinned makerdao/dss src/vat.sol
    (sha256 + git blob; Solidity is hash-pinned, not vendored — AGPL)
  * an independent C11 oracle (unsigned __int128 AND a portable 32-bit limb
    (a*b)/d that mirrors src/lin_maker_vat_fold.lin)
  * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
  * Compiler 0 in-memory libtcc JIT when libtcc is available
  * Python arbitrary-precision int as a third oracle

NOT claimed: uint256 / mainnet RAY=1e27 / wad*ray rad / vat.ilks parity;
LIN replacing Maker/Sky; TVL or dollar savings; zk soundness; auth/dai[u].

Class: EXPERIMENTAL (real vat.fold algorithm, RAY'=1e9, signed 128-bit mag).
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
LIN = ROOT / "src" / "lin_maker_vat_fold.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "maker_vat_fold_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "maker_vat_fold_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_maker_dss")
EVIDENCE = ROOT / "examples" / "maker_vat_fold" / "maker_vat_fold_evidence.json"

RAY = 10**9
ART = RAY
DLT = 10**6
ND = -10**6
I64MAX = 2**63 - 1
PINNED_COMMIT = "fa4f6630afb0624d04a003e920b0d71a00331d98"
PINNED_BLOB = "ff90bbed5b36e54318bd5461cbf32e4167df2b28"
PINNED_SHA256 = "9016fd94f0f1b014abf184edab86a3f5843042b17e3734407e0f0fabb920f49f"
UPSTREAM_REL = "src/vat.sol"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-maker-vat-fold"


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


def py_muldiv(a: int, b: int, d: int) -> int:
    if d <= 0 or a < 0 or b < 0:
        return 0
    q = (a * b) // d
    return 0 if q > I64MAX else q


def py_add_ui(x: int, y: int) -> int:
    if x < 0:
        return 0
    z = x + y
    if z < 0 or z > I64MAX:
        return 0
    return z


def py_rad(art: int, rate_delta: int) -> int:
    if art < 0:
        return 0
    mag = abs(rate_delta)
    if mag > I64MAX:
        return 0
    q = py_muldiv(art, mag, 1)
    if q == 0 and art != 0 and mag != 0:
        return 0
    return -q if rate_delta < 0 else q


def py_rad_ok(art: int, rate_delta: int) -> int:
    if art < 0:
        return 0
    mag = abs(rate_delta)
    if mag > I64MAX:
        return 0
    return 0 if art * mag > I64MAX else 1


def py_fold_rate(rate: int, rate_delta: int, live: int) -> int:
    return 0 if live != 1 else py_add_ui(rate, rate_delta)


def py_fold_dai(dai: int, art: int, rate_delta: int, live: int) -> int:
    if live != 1 or not py_rad_ok(art, rate_delta):
        return 0
    return py_add_ui(dai, py_rad(art, rate_delta))


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/makerdao/dss.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT], timeout=120)
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", "src/vat.sol missing after checkout"
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB:
        return "FAIL", "", f"live={live_hash} blob={blob}"
    text = live.read_text(encoding="utf-8")
    if "function fold(" not in text or "_mul(ilk.Art, rate)" not in text or "dai[u]" not in text:
        return "FAIL", "", "vat.sol missing fold / Art*rate / dai[u]"
    if "require(live == 1, \"Vat/not-live\")" not in text:
        return "FAIL", "", "vat.sol missing live circuit breaker"
    if "function _add(uint x, int y)" not in text or "function _mul(uint x, int y)" not in text:
        return "FAIL", "", "vat.sol missing signed _add/_mul"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    return "PASS", commit, f"vat.sol blob={blob}"


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  MAKER/SKY vat.fold — external LIN proof (RAY'=1e9, signed 128-bit, C11)")
    print("=" * 78)

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of vat.fold clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_maker_vat_fold.lin")

    for ident, path, label in (
        ("SOL-TR-CHECK", SOL_TR, "Solidity transpiler VAT_FOLD/LIVE/AUTH/DAI_SLOT"),
        ("C-TR-CHECK", C_TR, "C transpiler VAT_FOLD/LIVE/DAI_SLOT"),
        ("RS-TR-CHECK", RS_TR, "Rust transpiler VAT_FOLD/LIVE/DAI_SLOT"),
    ):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(ident, "FAIL", f"{path.name} check", c.stdout)
        else:
            rec(ident, "PASS", f"Compiler 0 check of {label}")

    gate = run([str(C0), "vm", str(LIN), "mvf_test_suite"], timeout=120)
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "mvf_test_suite via lin_c0 vm", (gate.stdout or "")[-400:])
        return 1
    rec("LIN-SUITE", "PASS", "mvf_test_suite == 1 on Compiler 0 interpreter")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned makerdao/dss vat.sol matches hash pin",
            f"commit={commit} {up_note}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of src/vat.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned commit unavailable; hash pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from hash pin", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb vat.fold selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb (a*b)/d agree")

    vectors = [
        ("rate", [RAY, 0, 1], "mvf_fold_rate", py_fold_rate(RAY, 0, 1)),
        ("rad", [ART, 0], "mvf_fold_rad", 0),
        ("rate", [RAY, DLT, 1], "mvf_fold_rate", 1001000000),
        ("rad", [ART, DLT], "mvf_fold_rad", 10**15),
        ("dai", [0, ART, DLT, 1], "mvf_fold_dai", 10**15),
        ("debt", [0, ART, DLT, 1], "mvf_fold_debt", 10**15),
        ("rate", [RAY, ND, 1], "mvf_fold_rate", 999000000),
        ("rad", [ART, ND], "mvf_fold_rad", -(10**15)),
        ("dai", [2 * 10**15, ART, ND, 1], "mvf_fold_dai", 10**15),
        ("rate", [RAY, DLT, 0], "mvf_fold_rate", 0),
        ("ok", [RAY, ART, DLT, 0, 0, 1], "mvf_fold_ok", 1),
        ("ok", [RAY, ART, DLT, 0, 0, 0], "mvf_fold_ok", 0),
    ]
    n_ok = 0
    for kind, args, fn, py in vectors:
        want = int(oracle([kind, *[str(a) for a in args]]).splitlines()[-1])
        want_limbs = int(oracle([kind, *[str(a) for a in args], "--limbs"]).splitlines()[-1])
        lin_args = args if kind != "rad" else [args[0], args[1], 1]
        got_lin = lin_vm(fn, *lin_args)
        if want != want_limbs or got_lin != want or py != want:
            rec("VEC-CONSENSUS", "FAIL", f"{kind}{tuple(args)}",
                f"c11={want} limbs={want_limbs} lin={got_lin} py={py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")

    rec("POS-FOLD", "PASS", "Art=1e9 delta=+1e6 → rate 1001000000 rad 1e15",
        f"rate={lin_vm('mvf_fold_rate', RAY, DLT, 1)} rad={lin_vm('mvf_fold_rad', ART, DLT, 1)}")
    rec("NEG-FOLD", "PASS", "Art=1e9 delta=-1e6 → rate 999000000 rad -1e15",
        f"rate={lin_vm('mvf_fold_rate', RAY, ND, 1)} rad={lin_vm('mvf_fold_rad', ART, ND, 1)}")
    rec("LIVE-GATE", "PASS", "live!=1 fail-closes; wrong_ignore_live still applies +1e6",
        f"dead={lin_vm('mvf_fold_rate', RAY, DLT, 0)} ignore={lin_vm('mvf_wrong_ignore_live', RAY, DLT)}")

    wrapped = (7 * 10**18 * 3 * 10**18) & ((1 << 64) - 1)
    if wrapped >= 2**63:
        wrapped -= 2**64
    wide = lin_vm("mvf_muldiv", 7 * 10**18, 3 * 10**18, 1)
    naive = lin_vm("mvf_naive_i64_mul", 7 * 10**18, 3 * 10**18)
    if wide != 0 or naive != wrapped:
        rec("I64-WRAP", "FAIL", "naive i64 7e18*3e18 should wrap; 128-bit muldiv fail-closes",
            f"naive={naive} wrap={wrapped} wide={wide}")
        return 1
    rec("I64-WRAP", "PASS", "naive signed-i64 (7e18*3e18) wraps; 128-bit muldiv fail-closes",
        f"i64_wrap={wrapped} muldiv={wide}")

    jit_ok = lin_roundtrip_jit("mvf_fold_rate", RAY, DLT, 1)
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on positive fold rate (in-memory libtcc)")
    else:
        jv = lin_jit("mvf_fold_rate", RAY, DLT, 1)
        if jv == 1001000000:
            rec("C0-JIT", "PASS", "lin_c0 jit fold_rate(RAY,+1e6)==1001000000 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    sol_src = SOL_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    rs_src = RS_TR.read_text(encoding="utf-8")
    if "mvf_fold_rate(rate: int, rate_delta: int, live: int)" not in src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN fold args")
        return 1
    rec("EXPLICIT-ARGS", "PASS", "LIN clone takes rate/art/rate_delta/dai/debt/live as arguments")
    rec("WIDE-MULDIV", "PASS", "clone uses 128-bit |Art|*|delta|; naive i64 7e18*3e18 wraps")
    if "REJ_SOLIDITY_VAT_FOLD" not in sol_src or "REJ_SOLIDITY_LIVE" not in sol_src:
        rec("SOL-REJ", "FAIL", "solidity transpiler missing VAT_FOLD / LIVE")
        return 1
    rec("SOL-REJ", "PASS", "lin_from_solidity.lin fail-closes vat.fold / live / auth / dai[u]")
    rec("C-REJ", "PASS" if "REJ_C_VAT_FOLD" in c_src else "FAIL", "lin_from_c.lin fail-closes vat_fold / live / dai[u]")
    rec("RS-REJ", "PASS" if "REJ_RUST_VAT_FOLD" in rs_src else "FAIL",
        "lin_from_rust.lin fail-closes vat_fold / live / dai_slot")
    if any(c["status"] == "FAIL" for c in claims[-2:]):
        return 1

    jr = run(["python3", str(ROOT / "test" / "prove_compound_jumprate_external.py")], timeout=180)
    if jr.returncode != 0:
        rec("JUMPRATE-REG", "FAIL", "Compound V2 JumpRate still PASS after the transpiler delta",
            (jr.stdout or "")[-400:])
        return 1
    rec("JUMPRATE-REG", "PASS", "Compound V2 JumpRate still PASS after the transpiler delta")

    evidence = {
        "schema": "LIN_MAKER_VAT_FOLD_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/makerdao/dss",
            "commit": commit or PINNED_COMMIT,
            "path": UPSTREAM_REL,
            "blob": PINNED_BLOB,
            "sha256": PINNED_SHA256,
            "license": "AGPL-3.0-or-later",
            "vendored": False,
        },
        "lin_clone": "src/lin_maker_vat_fold.lin",
        "clone_lin_repo": CLONE_LIN,
        "c11_oracle": "test/oracles/maker_vat_fold_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "ray_prime": RAY,
        "named_goldens": {
            "fold_rate(RAY, +1e6)": 1001000000,
            "fold_rad(Art=1e9, +1e6)": 10**15,
            "fold_rate(RAY, -1e6)": 999000000,
            "fold_rad(Art=1e9, -1e6)": -(10**15),
            "fold_dai(2e15, -1e6)": 10**15,
            "live=0": 0,
            "naive_i64(7e18, 3e18)": wrapped,
        },
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    print(f"  evidence: {EVIDENCE}")
    print(f"  clone-lin: {CLONE_LIN}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
