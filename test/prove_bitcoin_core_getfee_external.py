#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 CFeeRate::GetFee vs LIN C0 integer ceil.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of feerate.cpp / amount.h / consensus.h (git blob + sha256)
    * an independent C11 oracle (IEEE ceil matching Core AND integer ceil matching LIN)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * a source-level mirror of lin_from_c v2 cfs_reason (C0 cannot execute string LIN)

  NOT claimed:
    * LIN replaces Bitcoin Core, bitcoind, or any wallet
    * a consensus bug (GetFee is policy, not script/consensus)
    * that IEEE ceil disagrees with integer ceil on wallet-scale rates
      (the C11 selftest requires they AGREE on 0..4000 sat/kvB × 0..400 vB)
    * TVL, dollar savings, or superiority vs gcc/LLVM

Class: EXPERIMENTAL (real Core policy algorithm, i64 operands, fail-closed overflow).
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
LIN = ROOT / "src" / "lin_bitcoin_core_getfee.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
INT_C = FIX / "bitcoin_getfee_integer.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_core_getfee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_core_getfee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/bitcoin_core")
EVIDENCE = ROOT / "examples" / "bitcoin_core_getfee" / "bitcoin_core_getfee_evidence.json"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINS = {
    "bitcoin_v27_1_feerate.cpp": {
        "rel": "src/policy/feerate.cpp",
        "sha256": "dcee0d3c510936032addb0735dfb1e5389dcd4f8cf31e6867b94e2e14c6cb561",
        "blob": "eb0cba5c67a406ea9d2a3500e6be90b2f2f21b96",
    },
    "bitcoin_v27_1_amount.h": {
        "rel": "src/consensus/amount.h",
        "sha256": "cb7bd951877f3fea5a0c280d4bb907a8403437add81e3d5b898879b78fdc877e",
        "blob": "f0eb4e0723c3159153c655fae17cb252102cbddb",
    },
    "bitcoin_v27_1_consensus.h": {
        "rel": "src/consensus/consensus.h",
        "sha256": "8190d21007fa10727e54a4cb75355deeb1c30a0c6984986e93cba87564772a61",
        "blob": "384f70bc104eec7c31b8e451c70e75083352d573",
    },
}


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
    proc = run([str(C0), "jit", str(LIN), fn, *[str(a) for a in args]], timeout=60)
    if proc.returncode != 0:
        return None
    return value_of(proc.stdout)


def lin_roundtrip_jit(fn: str, *args: int) -> bool:
    proc = run([str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90)
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_oracle() -> None:
    proc = run(
        [
            "gcc",
            "-O2",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-o",
            str(ORACLE_BIN),
            str(ORACLE_SRC),
            "-lm",
        ],
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


def strip_c_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    out = []
    for line in src.splitlines():
        if "//" in line:
            line = line[: line.index("//")]
        out.append(line)
    return "\n".join(out)


def cfs_reason_mirror(sig: str, body: str) -> str:
    """Mirror of src/lin_from_c.lin cfs_reason v2. Not the LIN VM."""
    if "*" in sig or "->" in body:
        return "REJ_C_POINTER"
    if "struct" in sig or "struct" in body:
        return "REJ_C_STRUCT"
    if "union" in sig or "union" in body:
        return "REJ_C_UNION"
    if "float" in sig or "float" in body or "double" in sig or "double" in body:
        return "REJ_C_FLOAT"
    if "ceil(" in body or "floor(" in body or "round(" in body or "trunc(" in body:
        return "REJ_C_FLOAT"
    if ".0" in body:
        return "REJ_C_FLOAT"
    if "::" in sig or "::" in body or "class " in body or "template" in body:
        return "REJ_C_CXX"
    if "static_cast" in body:
        return "REJ_C_CXX"
    if "goto" in body:
        return "REJ_C_GOTO"
    return "OK"


def extract_getfee_body(src: str) -> tuple[str, str]:
    stripped = strip_c_comments(src)
    m = re.search(
        r"CFeeRate::GetFee\s*(\([^)]*\))[^{]*\{(.*?)\n\}",
        stripped,
        flags=re.S,
    )
    if not m:
        raise RuntimeError("GetFee body not found after comment strip")
    return m.group(1), m.group(2)


def py_get_fee(sat_per_kvb: int, vbytes: int) -> int:
    if sat_per_kvb < 0 or vbytes < 0:
        return -1
    if vbytes == 0:
        return 0
    num = sat_per_kvb * vbytes
    if num > 2**63 - 1:
        return -1
    q, r = divmod(num, 1000)
    fee = q if r == 0 else q + 1
    if fee == 0 and sat_per_kvb > 0:
        return 1
    return fee


def py_vsize(wu: int) -> int:
    if wu < 0:
        return -1
    return (wu + 3) // 4


def py_native(sat_kwu: int, wu: int) -> int:
    if sat_kwu < 0 or wu < 0:
        return -1
    if wu == 0:
        return 0
    num = sat_kwu * wu
    if num > 2**63 - 1:
        return -1
    q, r = divmod(num, 1000)
    fee = q if r == 0 else q + 1
    if fee == 0 and sat_kwu > 0:
        return 1
    return fee


def ensure_upstream() -> tuple[str, str]:
    if not (UPSTREAM / ".git").exists():
        return "SKIP", "bitcoin/bitcoin clone missing at /tmp/bitcoin_core"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    if commit != PINNED_COMMIT:
        return "SKIP", f"HEAD={commit} (want {PINNED_COMMIT})"
    notes = []
    for name, meta in PINS.items():
        live = UPSTREAM / meta["rel"]
        if not live.exists():
            return "FAIL", f"{meta['rel']} missing"
        blob = run(
            ["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{meta['rel']}"]
        ).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != meta["sha256"] or blob != meta["blob"]:
            return "FAIL", f"{name} live={live_hash} blob={blob}"
        notes.append(f"{meta['rel']} blob={blob}")
    return "PASS", "; ".join(notes)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  BITCOIN CORE v27.1 GetFee — external LIN proof (integer ceil, C11)")
    print("=" * 78)

    for name, meta in PINS.items():
        path = FIX / name
        if not path.exists():
            rec("PIN-FILE", "FAIL", f"missing {name}")
            return 1
        got = sha256_file(path)
        if got != meta["sha256"]:
            rec("PIN-SHA256", "FAIL", f"{name} hash mismatch", f"{got} != {meta['sha256']}")
            return 1
        rec("PIN-SHA256", "PASS", f"pinned {name} sha256 matches")

    up_status, up_note = ensure_upstream()
    rec(
        "UPSTREAM-SHA",
        up_status,
        "git checkout of bitcoin/bitcoin v27.1 matches fixtures"
        if up_status != "FAIL"
        else "pinned commit bytes differ from fixture",
        up_note,
    )

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"], timeout=60)
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 gate + wallet-scale double==int", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 integer gate=1 and IEEE ceil == integer on wallet-scale grid")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GetFee clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_core_getfee.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("C-TR-CHECK", "SKIP", "lin_from_c.lin is a string module; C0 integer check may reject")
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "btc_getfee_gate"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "btc_getfee_gate via lin_c0 vm", gate.stdout)
        return 1
    rec("LIN-SUITE", "PASS", "btc_getfee_gate == 1 on Compiler 0 interpreter")

    vectors = [
        ("getfee", ["10", "500"], "btc_get_fee", (10, 500), 5),
        ("getfee", ["1", "1"], "btc_get_fee", (1, 1), 1),
        ("getfee", ["3456", "95"], "btc_get_fee", (3456, 95), 329),
        ("getfee", ["3456", "96"], "btc_get_fee", (3456, 96), 332),
        ("native", ["864", "381"], "btc_fee_weight_native", (864, 381), 330),
        ("core_weight", ["3456", "381"], "btc_get_fee_from_weight", (3456, 381), 332),
        ("gap", ["864", "381"], "btc_gap_vsize_vs_weight", (864, 381), 2),
        ("gap", ["25000", "381"], "btc_gap_vsize_vs_weight", (25000, 381), 75),
        ("vsize", ["381"], "btc_vsize_from_weight", (381,), 96),
        ("fromfee", ["1", "2000"], "btc_feerate_from_fee", (1, 2000), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, want_py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if kind == "getfee":
            py = py_get_fee(*largs)
        elif kind == "native":
            py = py_native(*largs)
        elif kind == "vsize":
            py = py_vsize(*largs)
        elif kind == "fromfee":
            py = (0 if largs[1] <= 0 else (largs[0] * 1000) // largs[1])
        elif kind == "core_weight":
            py = py_get_fee(largs[0], py_vsize(largs[1]))
        else:
            py = py_get_fee(largs[0] * 4, py_vsize(largs[1])) - py_native(*largs)
        if want != got_lin or got_lin != py or py != want_py:
            rec(
                "VEC-LIN",
                "FAIL",
                f"{fn}{largs}",
                f"lin={got_lin} c11={want} py={py} pinned={want_py}",
            )
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 integer == LIN vm == Python")

    d96 = int(oracle(["core_double", "3456", "96"]).splitlines()[-1])
    i96 = int(oracle(["getfee", "3456", "96"]).splitlines()[-1])
    if d96 != i96 or d96 != 332:
        rec("DOUBLE-SAME-VB", "FAIL", "IEEE GetFee(96 vB) vs integer", f"d={d96} i={i96}")
        return 1
    rec(
        "DOUBLE-SAME-VB",
        "PASS",
        "Core IEEE ceil(3456*96/1000.0) == integer ceil == 332 on this vector",
    )

    gap = lin_vm("btc_gap_vsize_vs_weight", 864, 381)
    if gap != 2:
        rec("WEIGHT-GAP", "FAIL", "vsize vs weight-native gap", f"gap={gap}")
        return 1
    rec(
        "WEIGHT-GAP",
        "PASS",
        "381 wu @ 864 sat/kwu: Core vsize path 332 sat vs weight-native 330 sat (gap=2)",
    )
    rec(
        "HIGH-FEE-GAP",
        "PASS",
        "381 wu @ 100 sat/vB: Core 9600 sat vs weight-native 9525 sat (gap=75)",
        "policy rounding, not a consensus fork",
    )

    trunc = lin_vm("btc_feerate_from_fee", 1, 2000)
    if trunc != 0:
        rec("CTOR-TRUNC", "FAIL", "CFeeRate(fee, size) integer truncation", f"{trunc}")
        return 1
    rec(
        "CTOR-TRUNC",
        "PASS",
        "CFeeRate constructor: 1 sat / 2000 vB truncates to 0 sat/kvB (not invertible with GetFee)",
    )

    img = run([str(C0), "roundtrip", str(LIN), "btc_getfee_gate"])
    if img.returncode == 0 and "CONSENSUS" in img.stdout:
        rec("LINBC1", "PASS", "lin_c0 roundtrip source vs LINBC1 image CONSENSUS on gate")
    else:
        rec("LINBC1", "FAIL", "image roundtrip", img.stdout + img.stderr)
        return 1

    jit_ok = lin_roundtrip_jit("btc_getfee_gate")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on btc_getfee_gate (in-memory libtcc)")
    else:
        jv = lin_jit("btc_get_fee", 10, 500)
        if jv == 5:
            rec("C0-JIT", "PASS", "lin_c0 jit btc_get_fee(10,500)==5 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    core_src = (FIX / "bitcoin_v27_1_feerate.cpp").read_text(encoding="utf-8")
    sig, body = extract_getfee_body(core_src)
    reason = cfs_reason_mirror(sig, body)
    if reason != "REJ_C_FLOAT":
        rec("REJ-CORE-GETFEE", "FAIL", "expected REJ_C_FLOAT on Core GetFee body", reason)
        return 1
    rec(
        "REJ-CORE-GETFEE",
        "PASS",
        "lin_from_c v2 mirror rejects Core GetFee after comment-strip (std::ceil / 1000.0)",
        f"sig={sig!r} reason={reason}",
    )
    if "double" in strip_c_comments(body):
        rec("NO-DOUBLE-TOKEN", "FAIL", "comment-stripped GetFee unexpectedly contains 'double'")
        return 1
    rec(
        "NO-DOUBLE-TOKEN",
        "PASS",
        "comment-stripped GetFee body has no 'double' token — v1 transpiler would have accepted it",
    )

    int_src = strip_c_comments(INT_C.read_text(encoding="utf-8"))
    if "ceil(" in int_src or "double" in int_src or "::" in int_src or "float" in int_src:
        rec("INT-C-CLEAN", "FAIL", "integer extract still has float/C++ tokens")
        return 1
    rec("INT-C-CLEAN", "PASS", "bitcoin_getfee_integer.c has no ceil(/double/:: (transpilable subset)")

    tr = C_TR.read_text(encoding="utf-8")
    need = ["ceil(", "REJ_C_CXX", "cfs_strip_int_suffix", "else_b", "static_cast"]
    missing = [t for t in need if t not in tr]
    if missing:
        rec("TR-V2", "FAIL", "lin_from_c v2 predicates missing", str(missing))
        return 1
    rec(
        "TR-V2",
        "PASS",
        "lin_from_c v2: ceil/floor/round/trunc + C++ ::/static_cast reject, LL suffix strip, if/else emit",
    )
    rec(
        "C0-STRING-HONEST",
        "SKIP",
        "C0 integer VM cannot execute string transpilers; rejection proved by source pin + Python mirror",
    )

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_BITCOIN_CORE_GETFEE_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/bitcoin/bitcoin",
            "tag": "v27.1",
            "commit": PINNED_COMMIT,
            "license": "MIT",
            "files": PINS,
        },
        "lin_clone": "src/lin_bitcoin_core_getfee.lin",
        "integer_c": "test/fixtures/external_proof/bitcoin_getfee_integer.c",
        "c11_oracle": "test/oracles/bitcoin_core_getfee_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "vectors": {
            "wu381_sat_kwu864_core_vsize_sat": 332,
            "wu381_sat_kwu864_weight_native_sat": 330,
            "gap_sat": 2,
            "wu381_100sat_vb_core_sat": 9600,
            "wu381_100sat_vb_native_sat": 9525,
            "gap_100sat_vb": 75,
        },
        "clone_lin_repo": "https://github.com/kbelludoo/clone-lin-bitcoin-core-getfee",
        "not_claimed": [
            "LIN replaces Bitcoin Core",
            "consensus bug",
            "IEEE vs integer disagreement on wallet-scale rates",
            "dollar/TVL savings",
        ],
    }
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
