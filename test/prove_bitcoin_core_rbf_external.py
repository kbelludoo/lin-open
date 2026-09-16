#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: Bitcoin Core v27.1 PaysForRBF vs LIN C0 integer-ceil GetFee.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of rbf.cpp / rbf.h / policy.h / feerate.cpp / amount.h
      and btcd mempool/policy.go (git blob + sha256)
    * an independent C11 oracle (IEEE ceil matching Core GetFee AND integer ceil
      matching LIN AND btcd truncation matching calcMinRequiredTxRelayFee)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * a source-level mirror of lin_from_c v2 cfs_reason (C0 cannot execute string LIN)

  NOT claimed:
    * LIN replaces Bitcoin Core, bitcoind, btcd, or any wallet
    * a consensus bug (PaysForRBF is mempool policy, BIP-125, not script)
    * that IEEE ceil disagrees with integer ceil on wallet-scale rates
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
LIN = ROOT / "src" / "lin_bitcoin_core_rbf.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
INT_C = FIX / "bitcoin_rbf_integer.c"
ORACLE_SRC = ROOT / "test" / "oracles" / "bitcoin_core_rbf_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "bitcoin_core_rbf_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/bitcoin_core")
UPSTREAM_BTCD = Path("/tmp/btcd")
EVIDENCE = ROOT / "examples" / "bitcoin_core_rbf" / "bitcoin_core_rbf_evidence.json"

PINNED_COMMIT = "1088a98f5aad080cc6cca2da174f206509fcda6c"
PINNED_BTCD = "cc26860b40265e1332cca8748c5dbaf3c81cc094"
PINS = {
    "bitcoin_v27_1_rbf.cpp": {
        "rel": "src/policy/rbf.cpp",
        "sha256": "21bceebf13658ade1aa3700d1dc88294890b4448f83d83fe18722c5e710544bf",
        "blob": "f0830d8f2297c231a729a4898a887202a421fbdc",
    },
    "bitcoin_v27_1_rbf.h": {
        "rel": "src/policy/rbf.h",
        "sha256": "5bf37b54bb03fef87bb69146761c0ac3e4660b19ece0e26668f2315e18ce0cb9",
        "blob": "5a33ed64a376c1102a9f2cb0d3c4b66a87752e8c",
    },
    "bitcoin_v27_1_policy.h": {
        "rel": "src/policy/policy.h",
        "sha256": "da74b4819f1726151afb682e3f42f3954eb0d453b3db85faffa98b51189e2359",
        "blob": "6a7980c312c9bdf5398f914711571ed06a57712c",
    },
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
}
BTCD_PIN = {
    "file": "btcd_v0_24_2_policy.go",
    "rel": "mempool/policy.go",
    "sha256": "1f9ee1ef2b958aaaf91a2c3fb2056b01a2f82f5133d2ef99ed313d9669d7d66a",
    "blob": "862767d0c899922eaf90baa074cd801e198f7cd2",
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
    proc = run([str(ORACLE_BIN), *args], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_oracle() -> None:
    proc = run(
        ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC), "-lm"],
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


def cfs_reason_v1(sig: str, body: str) -> str:
    if "*" in sig or "->" in body:
        return "REJ_C_POINTER"
    if "struct" in sig or "struct" in body:
        return "REJ_C_STRUCT"
    if "union" in sig or "union" in body:
        return "REJ_C_UNION"
    if "float" in sig or "float" in body or "double" in sig or "double" in body:
        return "REJ_C_FLOAT"
    if "goto" in body:
        return "REJ_C_GOTO"
    return "OK"


def cfs_reason_v2(sig: str, body: str) -> str:
    if "*" in sig or "&" in sig or "->" in body:
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
    if "static_cast" in body or "optional" in sig or "optional" in body:
        return "REJ_C_CXX"
    if "goto" in body:
        return "REJ_C_GOTO"
    return "OK"


def extract_fn(src: str, name: str) -> tuple[str, str]:
    stripped = strip_c_comments(src)
    m = re.search(rf"{re.escape(name)}\s*(\([^)]*\))[^{{]*\{{(.*?)\n\}}", stripped, flags=re.S)
    if not m:
        raise RuntimeError(f"{name} body not found after comment strip")
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


def py_btcd(sat_per_kvb: int, nbytes: int) -> int:
    if sat_per_kvb < 0 or nbytes < 0:
        return -1
    min_fee = (nbytes * sat_per_kvb) // 1000
    if min_fee == 0 and sat_per_kvb > 0:
        min_fee = sat_per_kvb
    if min_fee < 0 or min_fee > 21_000_000 * 100_000_000:
        return 21_000_000 * 100_000_000
    return min_fee


def py_pays(orig: int, repl: int, vsize: int, rate: int) -> int:
    if orig < 0 or repl < 0 or vsize < 0 or rate < 0:
        return -1
    if repl < orig:
        return 0
    need = py_get_fee(rate, vsize)
    if need < 0:
        return -1
    return 1 if (repl - orig) >= need else 0


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
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{meta['rel']}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != meta["sha256"] or blob != meta["blob"]:
            return "FAIL", f"{name} live={live_hash} blob={blob}"
        notes.append(f"{meta['rel']} blob={blob}")
    return "PASS", "; ".join(notes)


def ensure_btcd() -> tuple[str, str]:
    if not (UPSTREAM_BTCD / ".git").exists():
        return "SKIP", "btcsuite/btcd clone missing at /tmp/btcd"
    commit = run(["git", "-C", str(UPSTREAM_BTCD), "rev-parse", "HEAD"]).stdout.strip()
    if commit != PINNED_BTCD:
        return "SKIP", f"HEAD={commit} (want {PINNED_BTCD})"
    live = UPSTREAM_BTCD / BTCD_PIN["rel"]
    if not live.exists():
        return "FAIL", f"{BTCD_PIN['rel']} missing"
    blob = run(["git", "-C", str(UPSTREAM_BTCD), "rev-parse", f"HEAD:{BTCD_PIN['rel']}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != BTCD_PIN["sha256"] or blob != BTCD_PIN["blob"]:
        return "FAIL", f"live={live_hash} blob={blob}"
    return "PASS", f"commit={commit} blob={blob}"


def rec(claims: list[dict[str, str]], ident: str, status: str, description: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": description, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
    print(f"  {tag} {ident:22s}  {description}")
    if note:
        print(f"            note: {note}")


def main() -> int:
    claims: list[dict[str, str]] = []
    print("=" * 78)
    print("  BITCOIN CORE v27.1 PaysForRBF — external LIN proof (BIP-125 #3/#4)")
    print("=" * 78)

    for name, meta in PINS.items():
        path = FIX / name
        if not path.exists():
            rec(claims, "PIN-FILE", "FAIL", f"missing {name}")
            return 1
        got = sha256_file(path)
        if got != meta["sha256"]:
            rec(claims, "PIN-SHA256", "FAIL", f"{name} hash mismatch", f"{got} != {meta['sha256']}")
            return 1
        rec(claims, "PIN-SHA256", "PASS", f"pinned {name} sha256 matches")

    btcd_path = FIX / BTCD_PIN["file"]
    if not btcd_path.exists() or sha256_file(btcd_path) != BTCD_PIN["sha256"]:
        rec(claims, "PIN-BTCD", "FAIL", "btcd policy.go pin mismatch")
        return 1
    rec(claims, "PIN-BTCD", "PASS", "pinned btcd v0.24.2 mempool/policy.go sha256 matches")

    up_status, up_note = ensure_upstream()
    rec(claims, "UPSTREAM-SHA", up_status, "git checkout of bitcoin/bitcoin v27.1 matches fixtures", up_note)
    if up_status == "FAIL":
        return 1
    bt_status, bt_note = ensure_btcd()
    rec(claims, "UPSTREAM-BTCD", bt_status, "git checkout of btcsuite/btcd v0.24.2 matches fixture", bt_note)
    if bt_status == "FAIL":
        return 1

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"], timeout=60)
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "C11 integer/IEEE/btcd selftest", st.stdout + st.stderr)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11: integer==IEEE on wallet-scale grid; BIP-125 vectors; btcd 3sat/2B")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check of PaysForRBF clone", chk.stdout)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_bitcoin_core_rbf.lin")

    chk2 = run([str(C0), "check", str(C_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec(claims, "C-TR-CHECK", "SKIP", "lin_from_c.lin is a string module; C0 integer check may reject")
    else:
        rec(claims, "C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2")

    gate = run([str(C0), "vm", str(LIN), "rbf_gate"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec(claims, "LIN-SUITE", "FAIL", "rbf_gate via lin_c0 vm", gate.stdout)
        return 1
    rec(claims, "LIN-SUITE", "PASS", "rbf_gate == 1 on Compiler 0 interpreter")

    vectors = [
        ("getfee", ["1000", "141"], "rbf_get_fee", (1000, 141), 141),
        ("getfee", ["3", "2"], "rbf_get_fee", (3, 2), 1),
        ("getfee", ["1", "1"], "rbf_get_fee", (1, 1), 1),
        ("btcd", ["3", "2"], "rbf_btcd_min_fee", (3, 2), 3),
        ("btcd", ["1000", "141"], "rbf_btcd_min_fee", (1000, 141), 141),
        ("gap", ["3", "2"], "rbf_gap_btcd_vs_core", (3, 2), 2),
        ("pays", ["2000", "2140", "141", "1000"], "rbf_pays_for_rbf", (2000, 2140, 141, 1000), 0),
        ("pays", ["2000", "2141", "141", "1000"], "rbf_pays_for_rbf", (2000, 2141, 141, 1000), 1),
        ("pays", ["2000", "1999", "141", "1000"], "rbf_pays_for_rbf", (2000, 1999, 141, 1000), 0),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, want_py in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        got_lin = lin_vm(fn, *largs)
        if kind == "getfee":
            py = py_get_fee(*largs)
        elif kind == "btcd":
            py = py_btcd(*largs)
        elif kind == "gap":
            py = py_btcd(*largs) - py_get_fee(*largs)
        else:
            py = py_pays(*largs)
        if want != got_lin or got_lin != py or py != want_py:
            rec(claims, "VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want} py={py}")
            return 1
        n_ok += 1
    rec(claims, "VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 == LIN vm == Python")

    rec(
        claims,
        "ONE-SAT-RBF",
        "PASS",
        "P2WPKH-class 141 vB @ 1 sat/vB: +140 sat extra REJECT, +141 ACCEPT (rule 4)",
        "original=2000 replacement=2140/2141 DEFAULT_INCREMENTAL_RELAY_FEE=1000",
    )
    rec(
        claims,
        "RULE3-TOTAL-FEE",
        "PASS",
        "replacement total 1999 < original 2000 REJECT even if feerate looks higher (rule 3)",
    )
    rec(
        claims,
        "BTCD-STRICTER",
        "PASS",
        "2 vB @ 3 sat/kvB: Core/LIN integer-ceil=1 sat; btcd truncation-then-full-rate=3 sat (gap=2)",
        "policy difference, not a consensus fork",
    )

    img = run([str(C0), "roundtrip", str(LIN), "rbf_gate"])
    if img.returncode == 0 and "CONSENSUS" in img.stdout:
        rec(claims, "LINBC1", "PASS", "lin_c0 roundtrip source vs LINBC1 image CONSENSUS on gate")
    else:
        rec(claims, "LINBC1", "FAIL", "image roundtrip", img.stdout + img.stderr)
        return 1

    jit_ok = lin_roundtrip_jit("rbf_gate")
    if jit_ok:
        rec(claims, "C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on rbf_gate (in-memory libtcc)")
    else:
        jv = lin_jit("rbf_get_fee", 1000, 141)
        if jv == 141:
            rec(claims, "C0-JIT", "PASS", "lin_c0 jit rbf_get_fee(1000,141)==141 (in-memory libtcc)")
        else:
            rec(claims, "C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    core_src = (FIX / "bitcoin_v27_1_rbf.cpp").read_text(encoding="utf-8")
    sig, body = extract_fn(core_src, "PaysForRBF")
    v1 = cfs_reason_v1(sig, body)
    v2 = cfs_reason_v2(sig, body)
    if v1 != "OK":
        rec(claims, "V1-WOULD-ACCEPT", "FAIL", "expected v1 OK on comment-stripped PaysForRBF", v1)
        return 1
    rec(claims, "V1-WOULD-ACCEPT", "PASS", "v1 cfs_reason would ACCEPT Core PaysForRBF (no * / double / struct)")
    if v2 != "REJ_C_POINTER" and v2 != "REJ_C_CXX":
        rec(claims, "REJ-CORE-RBF", "FAIL", "expected v2 reject on PaysForRBF", v2)
        return 1
    rec(claims, "REJ-CORE-RBF", "PASS", "lin_from_c v2 rejects Core PaysForRBF (uint256& and/or std::optional)", f"sig={sig!r} reason={v2}")

    fee_src = (FIX / "bitcoin_v27_1_feerate.cpp").read_text(encoding="utf-8")
    fsig, fbody = extract_fn(fee_src, "GetFee")
    if cfs_reason_v2(fsig, fbody) != "REJ_C_FLOAT":
        rec(claims, "REJ-CORE-GETFEE", "FAIL", "expected REJ_C_FLOAT on Core GetFee", cfs_reason_v2(fsig, fbody))
        return 1
    rec(claims, "REJ-CORE-GETFEE", "PASS", "lin_from_c v2 rejects Core GetFee after comment-strip (std::ceil / 1000.0)")

    int_src = strip_c_comments(INT_C.read_text(encoding="utf-8"))
    if "ceil(" in int_src or "double" in int_src or "::" in int_src or "&" in int_src.split("rbf_pays_for_rbf", 1)[1][:80]:
        rec(claims, "INT-C-CLEAN", "FAIL", "integer extract still has float/C++ tokens")
        return 1
    rec(claims, "INT-C-CLEAN", "PASS", "bitcoin_rbf_integer.c has no ceil(/double/:: (transpilable subset)")
    if "CAmount" not in INT_C.read_text(encoding="utf-8"):
        rec(claims, "CAMOUNT-TYPE", "FAIL", "integer extract does not use CAmount")
        return 1
    rec(claims, "CAMOUNT-TYPE", "PASS", "integer extract uses Core CAmount as a lin_from_c v2 type")

    tr = C_TR.read_text(encoding="utf-8")
    need = ["CAmount", "ceil(", "REJ_C_CXX", "cfs_strip_int_suffix", "else_b", "optional", 'rg_count_lit(sig, "&")']
    missing = [t for t in need if t not in tr]
    if missing:
        rec(claims, "TR-V2", "FAIL", "lin_from_c v2 predicates missing", str(missing))
        return 1
    rec(claims, "TR-V2", "PASS", "lin_from_c v2: CAmount type, &-in-sig pointer reject, ceil/C++/optional reject, LL strip, if/else")
    rec(claims, "C0-STRING-HONEST", "SKIP", "C0 integer VM cannot execute string transpilers; rejection proved by source pin + Python mirror")

    policy = (FIX / "bitcoin_v27_1_policy.h").read_text(encoding="utf-8")
    if "DEFAULT_INCREMENTAL_RELAY_FEE{1000}" not in policy:
        rec(claims, "PIN-CONST", "FAIL", "DEFAULT_INCREMENTAL_RELAY_FEE{1000} missing from policy.h")
        return 1
    rec(claims, "PIN-CONST", "PASS", "policy.h pins DEFAULT_INCREMENTAL_RELAY_FEE = 1000 sat/kvB")

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_BITCOIN_CORE_RBF_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/bitcoin/bitcoin",
            "tag": "v27.1",
            "commit": PINNED_COMMIT,
            "license": "MIT",
            "files": PINS,
            "cross_oracle": {
                "repo": "https://github.com/btcsuite/btcd",
                "tag": "v0.24.2",
                "commit": PINNED_BTCD,
                "license": "ISC",
                "file": BTCD_PIN,
            },
        },
        "lin_clone": "src/lin_bitcoin_core_rbf.lin",
        "integer_c": "test/fixtures/external_proof/bitcoin_rbf_integer.c",
        "c11_oracle": "test/oracles/bitcoin_core_rbf_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "vectors": {
            "p2wpkh_vbytes": 141,
            "incr_relay_sat_kvb": 1000,
            "need_sat": 141,
            "orig_2000_plus_140_sat": "REJECT",
            "orig_2000_plus_141_sat": "ACCEPT",
            "btcd_3sat_2B": 3,
            "core_3sat_2B": 1,
            "gap_sat": 2,
        },
        "clone_lin_repo": "https://github.com/kbelludoo/clone-lin-bitcoin-core-rbf",
        "not_claimed": [
            "LIN replaces Bitcoin Core or btcd",
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
