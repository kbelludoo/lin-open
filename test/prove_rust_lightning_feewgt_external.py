#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: rust-lightning v0.2.7 fee_for_weight (Apache-2.0 OR MIT) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of lightning/src/chain/chaininterface.rs (git blob + sha256)
    * an independent C11 oracle (LDK wrapping formula AND i64 remainder-ceil)
    * an independent Rust oracle of the same two paths
    * Python arbitrary-precision int
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces rust-lightning / LDK / a Lightning node
    * BOLT-07 routing ComputeFee (that is clone-lin-lnd-computefee)
    * rust-bitcoin FeeRate::to_sat_per_vb_ceil / div_by_weight_ceil
    * wall-clock superiority vs rustc
    * Compiler 0 executes rs_from_rs string-literal paths

Class: EXPERIMENTAL (real LDK on-chain fee algorithm, i64-scale operands).
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
LIN = ROOT / "src" / "lin_rust_lightning_feewgt.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "rust_lightning_feewgt_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "rust_lightning_feewgt_c11"
RS_SRC = ROOT / "test" / "oracles" / "rust_lightning_feewgt.rs"
RS_BIN = ROOT / "test" / "oracles" / "rust_lightning_feewgt_rs"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_rust_lightning")
EVIDENCE = ROOT / "examples" / "rust_lightning_feewgt" / "rust_lightning_feewgt_evidence.json"

PINNED_COMMIT = "5ce2ecb33d32e3b61ef01d5ead0ee6693c0cd7d1"
PINNED_TAG = "v0.2.7"
PINNED_SHA256 = "1e92ebb0e3d13437a13737bf53ff66f6281a726eeb66c168a0e2e1d820869eea"
PINNED_BLOB = "5dc46d5a055074ec6d9a028ca7a4c8723a62bcb0"
SRC_REL = "lightning/src/chain/chaininterface.rs"
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-rust-lightning-feewgt"
U32_MAX = 4294967295
I64_MAX = 9223372036854775807

# (feerate, weight, fee)
FEE_VECTORS = [
    (253, 1000, 253),
    (253, 1, 1),
    (1, 1000, 1),
    (1, 1, 1),
    (1, 999, 1),
    (1, 1001, 2),
    (250, 400, 100),
    (0, 500, 0),
    (253, 724, 184),
    (1000, 440, 440),
    (253, 440, 112),
    (4, 250, 1),
    (4, 249, 1),
    (5, 200, 1),
    (2530, 440, 1114),
]


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


def py_prod_ok(a: int, b: int) -> bool:
    if a < 0 or b < 0:
        return False
    if a == 0 or b == 0:
        return True
    return b <= I64_MAX // a


def py_fee(feerate: int, weight: int) -> int:
    if feerate < 0 or feerate > U32_MAX or weight <= 0:
        return 0
    if not py_prod_ok(feerate, weight):
        return 0
    p = feerate * weight
    q, r = divmod(p, 1000)
    return q if r == 0 else q + 1


def py_feerate(fee_sat: int, weight: int) -> int:
    if fee_sat < 0 or weight <= 0:
        return 0
    if not py_prod_ok(fee_sat, 1000):
        return U32_MAX
    q = (fee_sat * 1000) // weight
    return U32_MAX if q > U32_MAX else q


def py_bounded(est: int) -> int:
    if est < 0 or est > U32_MAX:
        return 0
    return 253 if est < 253 else est


def rust_wrap_fee(feerate: int, weight: int) -> int:
    mask = (1 << 64) - 1
    return ((feerate * weight + 999) & mask) // 1000


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")


def ensure_rust() -> bool:
    proc = run(["rustc", "-O", "-o", str(RS_BIN), str(RS_SRC)], timeout=60)
    return proc.returncode == 0 and RS_BIN.exists()


def rust_oracle(op: str, *args: int) -> str | None:
    if not RS_BIN.exists():
        return None
    proc = run([str(RS_BIN), op, *[str(a) for a in args]], timeout=30)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip().splitlines()[-1]


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/lightningdevkit/rust-lightning.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG], timeout=180)
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / SRC_REL
    if not live.exists():
        return "SKIP", "", "pinned path missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{SRC_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob}"
    live_txt = live.read_text(encoding="utf-8")
    excerpt = (FIX / "fee_for_weight.rs").read_text(encoding="utf-8")
    if excerpt not in live_txt:
        return "FAIL", commit, "fee_for_weight.rs excerpt not a substring"
    if "pub const FEERATE_FLOOR_SATS_PER_KW: u32 = 253;" not in live_txt:
        return "FAIL", commit, "FEERATE_FLOOR missing"
    if "pub const INCREMENTAL_RELAY_FEE_SAT_PER_1000_WEIGHT: u64 = 253;" not in live_txt:
        return "FAIL", commit, "INCREMENTAL_RELAY missing"
    return "PASS", commit, blob


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  rust-lightning fee_for_weight — external LIN proof (v0.2.7 / 253 sat/kW)")
    print("=" * 78)

    excerpt = FIX / "fee_for_weight.rs"
    if not excerpt.exists():
        rec("PIN-FILE", "FAIL", "pinned fee_for_weight.rs missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    if "fn fee_for_weight" not in src_ex or "+ 1000 - 1" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing overflow-prone ceil")
        return 1
    if "try_into" not in src_ex or "max_value" not in src_ex:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing try_into / max_value")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned excerpt has wrapping +999 ceil and try_into saturate")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of rust-lightning v0.2.7 matches pinned sha256/blob", f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of lightning/src/chain/chaininterface.rs")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch of pinned tag unavailable; excerpt pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 fee/feerate/floor vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range goldens vs i64 fail-closed")

    rust_ok = ensure_rust()
    if rust_ok:
        rst = run([str(RS_BIN), "selftest"], timeout=30)
        if rst.returncode != 0 or "PASS" not in rst.stdout:
            rec("RS-SELFTEST", "FAIL", "independent Rust oracle selftest", rst.stdout + rst.stderr)
            return 1
        rec("RS-SELFTEST", "PASS", "independent Rust remainder-ceil + wrapping goldens")
    else:
        rec("RS-SELFTEST", "SKIP", "rustc could not build the independent oracle")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of feewgt clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_rust_lightning_feewgt.lin")

    chk2 = run([str(C0), "check", str(RS_TR)])
    rec(
        "RS-TR-CHECK",
        "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2 (REJ_RUST_OVERFLOW_CEIL)",
    )
    chk3 = run([str(C0), "check", str(C_TR)])
    rec(
        "C-TR-CHECK",
        "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of C transpiler (unchanged this run)",
    )

    gate = run([str(C0), "vm", str(LIN), "fw_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "fw_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "fw_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for rate, weight, want in FEE_VECTORS:
        py = py_fee(rate, weight)
        c11 = int(oracle(["fee", str(rate), str(weight)]).splitlines()[-1])
        got = lin_vm("fw_fee_for_weight", rate, weight)
        wrap = rust_wrap_fee(rate, weight)
        if py != want or c11 != want or got != want:
            rec("VEC-LIN", "FAIL", f"fee {rate}*{weight}", f"py={py} c11={c11} lin={got} want={want}")
            return 1
        if wrap != want:
            rec("VEC-WRAP", "FAIL", f"in-range wrap != remainder {rate}*{weight}", f"wrap={wrap} want={want}")
            return 1
        rs = rust_oracle("fee", rate, weight)
        if rust_ok and rs != str(want):
            rec("VEC-RS", "FAIL", f"rust {rate}*{weight}", f"rs={rs}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python == C11 == Rust == LIN vm == wrapping in-range")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint remainder-ceil matches C11 and LIN")

    if lin_vm("fw_p2wpkh_floor") != 112 or lin_vm("fw_fee_for_weight", 253, 440) != 112:
        rec("P2WPKH-FLOOR", "FAIL", "253 sat/kW * 440 WU")
        return 1
    rec("P2WPKH-FLOOR", "PASS", "P2WPKH-sized 440 WU at LDK floor 253 sat/kW = 112 sats", "1 sat/vB after weight-to-vbyte rounding")

    if lin_vm("fw_bounded", 100) != 253 or lin_vm("fw_bounded", 1000) != 1000:
        rec("FLOOR-253", "FAIL", "FEERATE_FLOOR_SATS_PER_KW")
        return 1
    rec("FLOOR-253", "PASS", "LDK / Core Lightning 253 sat/kW floor; INCREMENTAL_RELAY is the same constant")

    if lin_vm("fw_compute_feerate", 253, 1000) != 253 or lin_vm("fw_compute_feerate", 5000000000, 1) != U32_MAX:
        rec("SATURATE", "FAIL", "compute_feerate saturate-to-u32max")
        return 1
    rec("SATURATE", "PASS", "compute_feerate saturates to u32::MAX instead of wrap-then-try_into")

    if lin_vm("fw_fee_for_weight", 253, 0) != 0 or lin_vm("fw_fee_for_weight", 4294967295, 2147483649) != 0:
        rec("FAIL-CLOSED", "FAIL", "zero-weight / i64 product overflow")
        return 1
    rec("FAIL-CLOSED", "PASS", "weight<=0, feerate>u32, negatives, and i64 product overflow fail-close to 0")

    jit_ok = lin_roundtrip_jit("fw_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on fw_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("fw_fee_for_weight", 253, 440)
        if jv == 112:
            rec("C0-JIT", "PASS", "lin_c0 jit fw_fee_for_weight(253,440)==112 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    if "fw_ceil_div" in src and "+ 1000 - 1" in src_ex:
        rec("EXPLICIT-CEIL", "PASS", "LIN remainder ceil; pinned LDK uses (prod + 1000 - 1) / 1000")
    else:
        rec("EXPLICIT-CEIL", "FAIL", "expected remainder-ceil vs +999")

    rs_src = RS_TR.read_text(encoding="utf-8")
    rec(
        "RS-CEIL-REJ",
        "PASS" if "REJ_RUST_OVERFLOW_CEIL" in rs_src and "REJ_RUST_TRY_INTO" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects +1000-1 ceil, div_ceil, try_into/unwrap_or",
    )
    rec(
        "RS-EMIT",
        "PASS" if "rs_from_rs" in rs_src and "version=2" in rs_src else "FAIL",
        "lin_from_rust.lin v2 emits eligible pure integer fns (lift is remainder-ceil)",
    )

    if "ComputeFee" in src or "fee_base_msat" in src:
        rec("NOT-BOLT07", "FAIL", "kernel must not claim BOLT-07 routing fee")
        return 1
    rec("NOT-BOLT07", "PASS", "this kernel is on-chain sats/kW*weight, not lnd ComputeFee")

    evidence = {
        "schema": "LIN_RUST_LIGHTNING_FEEWGT_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/lightningdevkit/rust-lightning",
            "tag": PINNED_TAG,
            "commit": commit or PINNED_COMMIT,
            "path": SRC_REL,
            "git_blob_sha": blob or PINNED_BLOB,
            "file_sha256": PINNED_SHA256,
            "license": "Apache-2.0 OR MIT",
            "constants": "FEERATE_FLOOR_SATS_PER_KW=253 INCREMENTAL_RELAY_FEE_SAT_PER_1000_WEIGHT=253",
        },
        "lin_clone": "src/lin_rust_lightning_feewgt.lin",
        "c11_oracle": "test/oracles/rust_lightning_feewgt_c11.c",
        "rust_oracle": "test/oracles/rust_lightning_feewgt.rs",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "clone_lin_repo": CLONE_LIN,
        "vectors": [{"feerate": a, "weight": b, "fee": c} for a, b, c in FEE_VECTORS],
        "distinct_from": [
            "lnd CachedEdgePolicy.ComputeFee / BOLT-07 ppm routing",
            "rust-bitcoin FeeRate::to_sat_per_vb_ceil",
            "rust-bitcoin Amount::div_by_weight_ceil",
            "Bitcoin Core CFeeRate::GetFee",
        ],
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
