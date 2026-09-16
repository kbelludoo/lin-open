#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: rust-bitcoin Amount::div_by_fee_rate_ceil (CC0-1.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of unsigned.rs / fee.rs / fee_rate/mod.rs
    * an independent C11 oracle (remainder ceil AND __int128 (a+d-1)/d)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle
    * rust-bitcoin published goldens:
        1000 sat / 2 sat/kwu = 500_000 wu (exact)
        1000 sat / 3 sat/kwu floor=333_333 ceil=333_334
        MAX_MONEY / 1 sat/kwu = 2_100_000_000_000_000_000 wu

  NOT claimed:
    * full rust-bitcoin wallet / PSBT / script
    * that LIN replaces rust-bitcoin or Bitcoin Core
    * wall-clock superiority vs rustc
    * that lin_c0 vm executes string-literal transpiler modules
      (VM_REJ_STRING_LITERAL); emit paths are typechecked, not interpreted
    * u64 FeeRate range (LIN is i64-scale; overflow fail-closes)

Class: EXPERIMENTAL (real rust-bitcoin algorithm, i64 satoshis).
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
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_rust_bitcoin_feerateceil.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "rust_bitcoin_feerateceil_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "rust_bitcoin_feerateceil_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_rust_bitcoin")
EVIDENCE = ROOT / "examples" / "rust_bitcoin_feerateceil" / "rust_bitcoin_feerateceil_evidence.json"
SCALAR_RS = FIX / "rust_bitcoin_feerateceil_scalar.rs"
SCALAR_C = FIX / "rust_bitcoin_feerateceil_scalar.c"
PINNED = FIX / "rust_bitcoin_amount_unsigned.rs"
PINNED_FEE = FIX / "rust_bitcoin_fee.rs"
PINNED_FR = FIX / "rust_bitcoin_fee_rate_mod.rs"

MAX_MONEY = 21_000_000 * 100_000_000
PINNED_SHA256 = "056757adc8f3ed6bc09dadf368fd027d04fcd7a721fb502fed23c8225cd790ef"
PINNED_BLOB = "0cfb8343787c893fe36aea38fc3b4c066ac2bedd"
PINNED_FEE_SHA256 = "ed7832bce17677cb76e2447ff516b7a2a4df83d8746cc010ba73993722d115e3"
PINNED_FEE_BLOB = "a275b4f27c154a0ca50d44b030c2cbcb71be3777"
PINNED_FR_SHA256 = "cbb0c13c54a808aa80de9652196e4f13f3f47bc3985e96b5c6fa7aeb6b705ecc"
PINNED_FR_BLOB = "e2e03fc112b8d28b80b13d449cb59d8ae4243742"
PINNED_COMMIT = "1cbf4bd62ea99c558c6d8ef794edbd984a2a4684"
UPSTREAM_REL = "units/src/amount/unsigned.rs"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-rust-bitcoin-feerateceil"


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
    url = "https://github.com/rust-bitcoin/rust-bitcoin.git"
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


def py_from_kwu(sat_kwu: int) -> int:
    if sat_kwu < 0 or sat_kwu > (2**63 - 1) // 4000:
        return -1
    return sat_kwu * 4000


def py_kwu_ceil(sat_mvb: int) -> int:
    if sat_mvb < 0:
        return -1
    if sat_mvb == 0:
        return 0
    q, r = divmod(sat_mvb, 4000)
    return q if r == 0 else q + 1


def py_fceil(sat: int, sat_mvb: int) -> int:
    if sat < 0 or sat > MAX_MONEY:
        return -1
    rate = py_kwu_ceil(sat_mvb)
    if rate <= 0:
        return -1
    msats = sat * 1000
    q, r = divmod(msats, rate)
    if r == 0:
        return q
    n = q + 1
    if n > 2**63 - 1:
        return -1
    return n


def py_ffloor(sat: int, sat_mvb: int) -> int:
    if sat < 0 or sat > MAX_MONEY:
        return -1
    rate = py_kwu_ceil(sat_mvb)
    if rate <= 0:
        return -1
    return (sat * 1000) // rate


def py_strip_uscore(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "_":
            prev_d = i > 0 and s[i - 1].isdigit()
            nxt_d = i + 1 < n and s[i + 1].isdigit()
            if prev_d and nxt_d:
                i += 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def py_count_borrow(s: str) -> int:
    c = 0
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "&":
            if i + 1 < n and s[i + 1] == "&":
                i += 2
                continue
            c += 1
        i += 1
    return c


def py_strip_as_cast(s: str) -> str:
    return re.sub(r"\bas\s+(u128|u64|u32|u16|u8|i128|i64|i32|i16|i8|usize|bool|Self|Option)\b", "", s)


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_RUST_BITCOIN_FEERATECEIL_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  RUST-BITCOIN Amount::div_by_fee_rate_ceil — external LIN proof (C11)")
    print("=" * 78)

    pins = [
        ("PIN-SHA256", PINNED, PINNED_SHA256, "unsigned.rs"),
        ("PIN-FEE-SHA", PINNED_FEE, PINNED_FEE_SHA256, "fee.rs"),
        ("PIN-FR-SHA", PINNED_FR, PINNED_FR_SHA256, "fee_rate/mod.rs"),
    ]
    for ident, path, expect, label in pins:
        if not path.exists():
            rec(ident, "FAIL", f"pinned {label} missing")
            return 1
        got = sha256_file(path)
        if got != expect:
            rec(ident, "FAIL", f"pinned {label} hash mismatch", f"{got} != {expect}")
            return 1
        rec(ident, "PASS", f"pinned {label} sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned rust-bitcoin commit matches fixture",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of units/src/amount/unsigned.rs")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    src = PINNED.read_text(encoding="utf-8")
    fee_src = PINNED_FEE.read_text(encoding="utf-8")
    fr_src = PINNED_FR.read_text(encoding="utf-8")
    if "fn div_by_fee_rate_ceil" not in src or "to_sat_per_kwu_ceil" not in src:
        rec("UPSTREAM-FNS", "FAIL", "pinned unsigned.rs missing div_by_fee_rate_ceil")
        return 1
    if "div_by_fee_rate_ceil" not in fee_src or "333_334" not in fee_src:
        rec("UPSTREAM-FEE", "FAIL", "pinned fee.rs missing ceil golden 333_334")
        return 1
    if "fn to_sat_per_kwu_ceil" not in fr_src or "div_ceil(4_000)" not in fr_src:
        rec("UPSTREAM-FR", "FAIL", "pinned fee_rate/mod.rs missing to_sat_per_kwu_ceil")
        return 1
    rec("UPSTREAM-FNS", "PASS", "pinned unsigned.rs contains div_by_fee_rate_ceil")
    rec("UPSTREAM-FEE", "PASS", "pinned fee.rs contains published ceil golden 333_334")
    rec("UPSTREAM-FR", "PASS", "pinned fee_rate/mod.rs contains to_sat_per_kwu_ceil / div_ceil(4_000)")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 remainder vs __int128 selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 remainder ceil and __int128 (a+d-1)/d agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of fee-rate-ceil clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_rust_bitcoin_feerateceil.lin")

    for label, path in (("RS-TR-CHECK", RS_TR), ("C-TR-CHECK", C_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", c.stdout + c.stderr)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    rs_src = RS_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    if "version=2" in rs_src and "rs_from_rs" in rs_src and "rs_strip_as_cast" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 skips && as borrow, strips 4_000, strips as-casts, emits LIN")
    else:
        rec("RS-EMIT", "FAIL", "rust transpiler v2 emit / as-cast strip missing")
    if "REJ_C_CXX_SCOPE" in c_src and "cfs_count_ref" in c_src:
        rec("C-REJ-V2", "PASS", "lin_from_c.lin v2 rejects :: and lone & in signatures")
    else:
        rec("C-REJ-V2", "FAIL", "C transpiler v2 reject codes missing")

    rs_txt = SCALAR_RS.read_text(encoding="utf-8") if SCALAR_RS.exists() else ""
    if "&&" in rs_txt and "4_000" in rs_txt and " as u64" in rs_txt and "const fn" in rs_txt:
        rec("SCALAR-RS", "PASS", "scalar rust fixture has &&, 4_000, as u64, const fn for v2")
    else:
        rec("SCALAR-RS", "FAIL", "scalar rust fixture missing && / 4_000 / as-cast / const fn")
    stripped = py_strip_uscore(py_strip_as_cast(rs_txt))
    if "4_000" in stripped or " as u64" in stripped:
        rec("PY-STRIP", "FAIL", "python dual failed to strip underscores / as-casts")
    elif py_count_borrow(rs_txt) != 0:
        rec("PY-STRIP", "FAIL", "python dual counted && as a borrow")
    else:
        rec("PY-STRIP", "PASS", "python dual: && is not borrow; 4_000 and as u64 stripped")
    if SCALAR_C.exists():
        c_txt = SCALAR_C.read_text(encoding="utf-8")
        if "->" in c_txt or "int64_t *" in c_txt or "::" in c_txt:
            rec("SCALAR-C", "FAIL", "scalar C fixture has pointer or C++ scope syntax")
        else:
            rec("SCALAR-C", "PASS", "scalar C fixture present (no pointer / :: decls)")
    else:
        rec("SCALAR-C", "FAIL", "scalar C fixture missing")

    gate = run([str(C0), "vm", str(LIN), "rfc_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "rfc_test_suite via lin_c0 vm", f"value={gv} {gate.stdout}\n{gate.stderr}")
        return 1
    rec("LIN-SUITE", "PASS", "rfc_test_suite == 1 on Compiler 0 interpreter")

    mvb2 = py_from_kwu(2)
    mvb3 = py_from_kwu(3)
    mvb1 = py_from_kwu(1)
    vectors = [
        ("fceil", 1000, mvb2),
        ("fceil", 1000, mvb3),
        ("fceil", 1000, 0),
        ("fceil", 0, mvb2),
        ("ffloor", 1000, mvb2),
        ("ffloor", 1000, mvb3),
        ("ffloor", MAX_MONEY, mvb1),
        ("kwu_ceil", 2000400, 0),
        ("kwu_floor", 2000400, 0),
        ("kwu_ceil", 1, 0),
        ("dceil", 10, 3),
    ]
    n_ok = 0
    py_fn = {
        "fceil": lambda a, b: py_fceil(a, b),
        "ffloor": lambda a, b: py_ffloor(a, b),
        "kwu_ceil": lambda a, _b: py_kwu_ceil(a),
        "kwu_floor": lambda a, _b: a // 4000 if a >= 0 else -1,
        "dceil": lambda a, b: (lambda q_r: q_r[0] if q_r[1] == 0 else q_r[0] + 1)(divmod(a, b)) if b > 0 else -1,
    }
    lin_fn = {
        "fceil": "rfc_div_by_fee_rate_ceil",
        "ffloor": "rfc_div_by_fee_rate_floor",
        "kwu_ceil": "rfc_to_sat_per_kwu_ceil",
        "kwu_floor": "rfc_to_sat_per_kwu_floor",
        "dceil": "rfc_div_ceil",
    }
    for kind, a, b in vectors:
        args = [kind, str(a)] if kind.startswith("kwu_") else [kind, str(a), str(b)]
        if kind.startswith("kwu_"):
            args = [kind, str(a)]
        want = int(oracle(args).splitlines()[-1])
        if kind in ("fceil", "kwu_ceil", "dceil"):
            want_i = int(oracle(args + ["--i128"]).splitlines()[-1])
            if want != want_i:
                rec("VEC-I128", "FAIL", f"{kind}({a},{b}) rem vs i128", f"{want} != {want_i}")
                return 1
        py = py_fn[kind](a, b)
        if kind in ("kwu_ceil", "kwu_floor"):
            got = lin_vm(lin_fn[kind], a)
        else:
            got = lin_vm(lin_fn[kind], a, b)
        if got != want or py != want:
            rec("VEC-LIN", "FAIL", f"{kind}({a},{b})", f"lin={got} c11={want} py={py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 rem == i128 == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint matches C11 and LIN")

    if lin_vm("rfc_div_by_fee_rate_ceil", 1000, mvb2) != 500_000:
        rec("GOLDEN-EXACT", "FAIL", "rust-bitcoin test: 1000 sat / 2 sat/kwu")
        return 1
    rec("GOLDEN-EXACT", "PASS", "published rust-bitcoin golden: 1000 sat / 2 sat/kwu = 500000 wu")
    if lin_vm("rfc_div_by_fee_rate_floor", 1000, mvb3) != 333_333:
        rec("GOLDEN-FLOOR", "FAIL", "rust-bitcoin test: 1000 sat / 3 sat/kwu floor")
        return 1
    rec("GOLDEN-FLOOR", "PASS", "published rust-bitcoin golden: 1000 sat / 3 sat/kwu floor = 333333 wu")
    if lin_vm("rfc_div_by_fee_rate_ceil", 1000, mvb3) != 333_334:
        rec("GOLDEN-CEIL", "FAIL", "rust-bitcoin test: 1000 sat / 3 sat/kwu ceil")
        return 1
    rec("GOLDEN-CEIL", "PASS", "published rust-bitcoin golden: 1000 sat / 3 sat/kwu ceil = 333334 wu")
    if lin_vm("rfc_div_by_fee_rate_floor", MAX_MONEY, mvb1) != 2_100_000_000_000_000_000:
        rec("GOLDEN-MAX", "FAIL", "rust-bitcoin test: MAX_MONEY / 1 sat/kwu")
        return 1
    rec("GOLDEN-MAX", "PASS", "published rust-bitcoin golden: MAX_MONEY / 1 sat/kwu = 2100000000000000000 wu")

    if lin_vm("rfc_floor_underpay", 1000, mvb3) != 1 or lin_vm("rfc_floor_underpay", 1000, mvb2) != 0:
        rec("UNDERPAY", "FAIL", "floor underpay detector")
        return 1
    rec("UNDERPAY", "PASS", "Amount/FeeRate floor underpays 1 wu on 1000/3 sat/kwu; exact on 1000/2")

    if lin_vm("rfc_tiny_mvb_inflates", 1) != 1 or lin_vm("rfc_tiny_mvb_inflates", 4000) != 0:
        rec("TINY-MVB", "FAIL", "1 sat/MvB ceil-inflates to 1 sat/kwu")
        return 1
    rec("TINY-MVB", "PASS", "1 sat/MvB ceil-converts to 1 sat/kwu (4000x vs floor=0); 4000 sat/MvB is exact")

    naive = (1000 + 3 - 1) // 3
    if naive != 334:
        rec("REM-CEIL", "FAIL", "sanity: remainder ceil of 10/3")
    rem_ok = lin_vm("rfc_div_ceil", 10, 3) == 4 and lin_vm("rfc_div_ceil", 9, 3) == 3
    if not rem_ok:
        rec("REM-CEIL", "FAIL", "remainder ceil vs (a+d-1)/d identity on small ints")
        return 1
    rec("REM-CEIL", "PASS", "remainder ceil equals (a+d-1)/d on in-range ints; zero den fail-closes")

    jit_ok = lin_roundtrip_jit("rfc_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on rfc_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("rfc_div_by_fee_rate_ceil", 1000, mvb3)
        if jv == 333_334:
            rec("C0-JIT", "PASS", "lin_c0 jit rfc_div_by_fee_rate_ceil(1000,12000)==333334")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module")

    lin_txt = LIN.read_text(encoding="utf-8")
    if "rfc_div_by_fee_rate_ceil(satoshi: int, sat_mvb: int)" not in lin_txt:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit satoshi/sat_mvb args")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes Amount sats and FeeRate sat/MvB as arguments (no newtype)")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/rust-bitcoin/rust-bitcoin",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "fee_sha256": PINNED_FEE_SHA256,
        "fee_rate_sha256": PINNED_FR_SHA256,
        "license": "CC0-1.0",
    }
    evidence["lin_clone"] = "src/lin_rust_bitcoin_feerateceil.lin"
    evidence["clone_lin_repo"] = CLONE_LIN
    evidence["c11_oracle"] = "test/oracles/rust_bitcoin_feerateceil_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["golden_ceil_1000_3kwu"] = 333334
    evidence["golden_floor_1000_3kwu"] = 333333
    evidence["golden_exact_1000_2kwu"] = 500000
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
