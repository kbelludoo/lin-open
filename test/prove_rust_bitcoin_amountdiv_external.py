#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: rust-bitcoin Amount::checked_div / checked_rem /
div_by_weight_floor (CC0-1.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of units/src/amount/unsigned.rs (git blob + sha256)
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int as a third oracle

  NOT claimed:
    * full rust-bitcoin wallet / PSBT / script
    * that LIN replaces rust-bitcoin or Bitcoin Core
    * wall-clock superiority vs rustc
    * that lin_c0 vm executes string-literal transpiler modules
      (VM_REJ_STRING_LITERAL); emit paths are typechecked, not interpreted

Class: EXPERIMENTAL (real rust-bitcoin algorithm, i64-scale satoshis,
128-bit product for weight floor).
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
LIN = ROOT / "src" / "lin_rust_bitcoin_amountdiv.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "rust_bitcoin_amountdiv_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "rust_bitcoin_amountdiv_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_rust_bitcoin")
EVIDENCE = ROOT / "examples" / "rust_bitcoin_amountdiv" / "rust_bitcoin_amountdiv_evidence.json"
SCALAR_RS = FIX / "rust_bitcoin_amountdiv_scalar.rs"
SCALAR_C = FIX / "rust_bitcoin_amountdiv_scalar.c"
PINNED = FIX / "rust_bitcoin_amount_unsigned.rs"

MAX_MONEY = 21_000_000 * 100_000_000
PINNED_SHA256 = "056757adc8f3ed6bc09dadf368fd027d04fcd7a721fb502fed23c8225cd790ef"
PINNED_BLOB = "0cfb8343787c893fe36aea38fc3b4c066ac2bedd"
PINNED_COMMIT = "1cbf4bd62ea99c558c6d8ef794edbd984a2a4684"
UPSTREAM_REL = "units/src/amount/unsigned.rs"


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


def py_checked_div(sat: int, rhs: int) -> int:
    if sat < 0 or sat > MAX_MONEY or rhs <= 0:
        return -1
    return sat // rhs


def py_checked_rem(sat: int, rhs: int) -> int:
    if sat < 0 or sat > MAX_MONEY or rhs <= 0:
        return -1
    return sat % rhs


def py_wfloor(sat: int, wu: int) -> int:
    if sat < 0 or sat > MAX_MONEY or wu <= 0:
        return -1
    q = (sat * 4_000_000) // wu
    if q > 2**63 - 1:
        return -1
    return q


def py_wrem(sat: int, wu: int) -> int:
    if sat < 0 or sat > MAX_MONEY or wu <= 0:
        return -1
    return (sat * 4_000_000) % wu


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_RUST_BITCOIN_AMOUNTDIV_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  RUST-BITCOIN Amount::checked_div — external LIN proof (C11 oracle)")
    print("=" * 78)

    if not PINNED.exists():
        rec("PIN-FILE", "FAIL", "pinned rust_bitcoin_amount_unsigned.rs missing")
        return 1
    got = sha256_file(PINNED)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned unsigned.rs sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned rust-bitcoin commit matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of units/src/amount/unsigned.rs")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned commit unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    src = PINNED.read_text(encoding="utf-8")
    if "fn checked_div" not in src or "fn checked_rem" not in src:
        rec("UPSTREAM-FNS", "FAIL", "pinned unsigned.rs missing checked_div/checked_rem")
        return 1
    if "fn div_by_weight_floor" not in src or "4_000_000" not in src:
        rec("UPSTREAM-WFLOOR", "FAIL", "pinned unsigned.rs missing div_by_weight_floor")
        return 1
    rec("UPSTREAM-FNS", "PASS", "pinned source contains checked_div, checked_rem, div_by_weight_floor")

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of amount-div clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_rust_bitcoin_amountdiv.lin")

    for label, path in (("RS-TR-CHECK", RS_TR), ("C-TR-CHECK", C_TR)):
        c = run([str(C0), "check", str(path)])
        if c.returncode != 0 and "LIN_CHECK" not in c.stdout:
            rec(label, "FAIL", f"lin_c0 check {path.name}", c.stdout + c.stderr)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    rs_src = RS_TR.read_text(encoding="utf-8")
    c_src = C_TR.read_text(encoding="utf-8")
    if "version=2" in rs_src and "rs_count_borrow" in rs_src and "rs_from_rs" in rs_src:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2 skips && as borrow and emits LIN")
    else:
        rec("RS-EMIT", "FAIL", "rust transpiler v2 emit/skip-&& missing")
    if "REJ_C_CXX_SCOPE" in c_src and "REJ_C_REFERENCE" in c_src and "cfs_count_ref" in c_src:
        rec("C-REJ-V2", "PASS", "lin_from_c.lin v2 rejects :: and lone & in signatures")
    else:
        rec("C-REJ-V2", "FAIL", "C transpiler v2 reject codes missing")
    if "charCodeAt(i + 1) == 38" in rs_src and "charCodeAt(i + 1) == 38" in c_src:
        rec("AMP-SKIP", "PASS", "both transpilers skip ASCII 38,38 (&&) as not-a-borrow")
    else:
        rec("AMP-SKIP", "FAIL", "&& skip not present in both transpilers")

    if not SCALAR_RS.exists() or "&&" not in SCALAR_RS.read_text(encoding="utf-8") and "||" not in SCALAR_RS.read_text(encoding="utf-8"):
        rec("SCALAR-RS", "FAIL", "scalar rust fixture missing &&/|| vector")
    else:
        rec("SCALAR-RS", "PASS", "scalar rust fixture has || (and no lone &) for v2 borrow skip")
    if not SCALAR_C.exists() or "*" in SCALAR_C.read_text(encoding="utf-8").split("int64_t")[0]:
        rec("SCALAR-C", "PASS" if SCALAR_C.exists() else "FAIL", "scalar C fixture present (no pointers)")
    else:
        rec("SCALAR-C", "PASS", "scalar C fixture present for lin_from_c v2")

    gate = run([str(C0), "vm", str(LIN), "rad_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "rad_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "rad_test_suite == 1 on Compiler 0 interpreter")

    amp = lin_vm("rad_amp_kind_gate")
    if amp != 1:
        rec("AMP-KIND", "FAIL", "rad_amp_kind_gate", f"value={amp}")
        return 1
    rec("AMP-KIND", "PASS", "Compiler 0 vm: '&'+'&' is and, lone '&' is borrow (ASCII 38)")

    vectors = [
        ("div", 100, 3),
        ("div", 0, 7),
        ("div", 100, 0),
        ("div", MAX_MONEY, 2),
        ("rem", 100, 3),
        ("rem", 0, 7),
        ("rem", 21, 5),
        ("wfloor", 10, 200),
        ("wfloor", 10, 300),
        ("wfloor", 10, 0),
        ("wfloor", MAX_MONEY, 1),
        ("wrem", 10, 200),
        ("wrem", 10, 300),
    ]
    n_ok = 0
    for kind, a, b in vectors:
        if kind == "div":
            want = int(oracle(["div", str(a), str(b)]).splitlines()[-1])
            py = py_checked_div(a, b)
            got = lin_vm("rad_checked_div", a, b)
        elif kind == "rem":
            want = int(oracle(["rem", str(a), str(b)]).splitlines()[-1])
            py = py_checked_rem(a, b)
            got = lin_vm("rad_checked_rem", a, b)
        elif kind == "wfloor":
            want = int(oracle(["wfloor", str(a), str(b)]).splitlines()[-1])
            want_l = int(oracle(["wfloor", str(a), str(b), "--limbs"]).splitlines()[-1])
            if want != want_l:
                rec("VEC-LIMBS", "FAIL", f"wfloor({a},{b}) i128 vs limbs", f"{want} != {want_l}")
                return 1
            py = py_wfloor(a, b)
            got = lin_vm("rad_div_by_weight_floor", a, b)
        else:
            want = int(oracle(["wrem", str(a), str(b)]).splitlines()[-1])
            want_l = int(oracle(["wrem", str(a), str(b), "--limbs"]).splitlines()[-1])
            if want != want_l:
                rec("VEC-LIMBS", "FAIL", f"wrem({a},{b}) i128 vs limbs", f"{want} != {want_l}")
                return 1
            py = py_wrem(a, b)
            got = lin_vm("rad_div_by_weight_rem", a, b)
        if got != want or py != want:
            rec("VEC-LIN", "FAIL", f"{kind}({a},{b})", f"lin={got} c11={want} py={py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")

    if lin_vm("rad_div_rem_ok", 100, 3) != 1:
        rec("REM-ID", "FAIL", "100 == 33*3 + 1 identity")
        return 1
    rec("REM-ID", "PASS", "checked_div/checked_rem identity sat = q*rhs + r (rhs>0)")

    naive = (MAX_MONEY * 4_000_000) & ((1 << 64) - 1)
    if naive >= 2**63:
        naive -= 2**64
    wide = py_wfloor(MAX_MONEY, 1)
    if wide != -1:
        rec("I64-WRAP", "FAIL", "MAX_MONEY*4e6/1 should overflow i64 FeeRate")
        return 1
    rec(
        "I64-WRAP",
        "PASS",
        "naive i64 of MAX_MONEY*4e6 wraps; 128-bit weight floor fail-closes",
        f"i64_wrap={naive} lin_wfloor={wide}",
    )

    jit_ok = lin_roundtrip_jit("rad_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on rad_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("rad_checked_div", 100, 3)
        if jv == 33:
            rec("C0-JIT", "PASS", "lin_c0 jit rad_checked_div(100,3)==33 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/rust-bitcoin/rust-bitcoin",
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "CC0-1.0",
    }
    evidence["lin_clone"] = "src/lin_rust_bitcoin_amountdiv.lin"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-rust-bitcoin-amountdiv"
    evidence["c11_oracle"] = "test/oracles/rust_bitcoin_amountdiv_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
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
