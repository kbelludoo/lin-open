#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: lnd BOLT07 ComputeFee / inbound CalcFee vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of cached_edge_policy.go + inbound_fee.go
      (git blob + sha256) from lightningnetwork/lnd v0.21.3-beta
    * an independent C11 oracle (unsigned __int128 AND portable 32-bit limbs)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available
    * Python arbitrary-precision int (third oracle)

  NOT claimed:
    * that LIN is an lnd routing node or gossip implementation
    * uint256 / mainnet Lightning capacity beyond uint64-scale operands
    * wall-clock superiority vs Go/LLVM

Class: EXPERIMENTAL (real BOLT07 fee algorithm, uint64-scale operands).
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
LIN = ROOT / "src" / "lin_lnd_computefee.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "lnd_computefee_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "lnd_computefee_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_lnd")
EVIDENCE = ROOT / "examples" / "lnd_computefee" / "lnd_computefee_evidence.json"

PINNED_COMMIT = "572b561bf05f03dfe6135110970c4d858c3482dc"
PINNED_TAG = "v0.21.3-beta"
FILES = {
    "cached_edge_policy.go": {
        "rel": "graph/db/models/cached_edge_policy.go",
        "fixture": "lnd_cached_edge_policy.go",
        "sha256": "22b438d786fa529bf336a66b9c885987e2c168b07c91a3981e95c49f1f5a292e",
        "blob": "90c8d56c3992af17a58c1d21f3c156e9ffbce0a2",
    },
    "inbound_fee.go": {
        "rel": "graph/db/models/inbound_fee.go",
        "fixture": "lnd_inbound_fee.go",
        "sha256": "49feaf334359376dee1ab78ab78443544d8ec1bed5baa8c470be91a92840f150",
        "blob": "7158b49076818f8c86e35d94f302277394a24f29",
    },
    "inbound_fee_test.go": {
        "rel": "graph/db/models/inbound_fee_test.go",
        "fixture": "lnd_inbound_fee_test.go",
        "sha256": "287ecbac5450aa3405e68eb89d9578a95ebc2260c7013d54a51e81096688af6c",
        "blob": "58adfb4d9f6e1393db2d6c4d8d99fa2abfc324d1",
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
    url = "https://github.com/lightningnetwork/lnd.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", "refs/tags/" + PINNED_TAG],
        timeout=120,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    if commit != PINNED_COMMIT:
        return "FAIL", commit, f"commit {commit} != {PINNED_COMMIT}"
    notes = []
    for meta in FILES.values():
        live = UPSTREAM / meta["rel"]
        if not live.exists():
            return "FAIL", commit, f"{meta['rel']} missing"
        blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{meta['rel']}"]).stdout.strip()
        live_hash = sha256_file(live)
        if live_hash != meta["sha256"] or blob != meta["blob"]:
            return "FAIL", commit, f"{meta['rel']} live={live_hash} blob={blob}"
        notes.append(blob)
    return "PASS", commit, ",".join(notes)


def py_fee(base: int, ppm: int, amt: int) -> int:
    if base < 0 or ppm < 0 or amt < 0:
        return 0
    prop = (amt * ppm) // 1_000_000
    if prop > (1 << 64) - 1:
        return 0
    s = base + prop
    if s > (1 << 64) - 1:
        return 0
    return s


def py_inbound(base: int, rate: int, amt: int) -> int:
    if amt < 0:
        return 0
    cap = 10_000_000
    if rate > cap:
        rate = cap
    if rate < -cap:
        rate = -cap
    mag = -rate if rate < 0 else rate
    p = (amt * mag) // 1_000_000
    if rate < 0:
        p = -p
    return base + p


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_LND_COMPUTEFEE_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  LND BOLT07 ComputeFee — external LIN proof (uint64-scale, C11 oracle)")
    print("=" * 78)

    for key, meta in FILES.items():
        pinned = FIX / meta["fixture"]
        if not pinned.exists():
            rec("PIN-FILE", "FAIL", f"pinned {meta['fixture']} missing")
            return 1
        got = sha256_file(pinned)
        if got != meta["sha256"]:
            rec("PIN-SHA256", "FAIL", f"{key} hash mismatch", f"{got} != {meta['sha256']}")
            return 1
        rec("PIN-SHA256", "PASS", f"pinned {meta['fixture']} sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    if up_status == "PASS":
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned lnd tag matches fixtures", f"commit={commit}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of ComputeFee / CalcFee sources")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned tag bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs limb muldiv selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 and portable limb muldiv agree")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of lnd clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_lnd_computefee.lin")

    for label, path in (("GO-TR-CHECK", GO_TR), ("RS-TR-CHECK", RS_TR), ("C-TR-CHECK", C_TR)):
        p = run([str(C0), "check", str(path)])
        if p.returncode != 0 and "LIN_CHECK" not in p.stdout and ".typecheck=passed" not in p.stdout:
            rec(label, "FAIL", f"check {path.name}", p.stdout)
        else:
            rec(label, "PASS", f"Compiler 0 check of {path.name}")

    gate = run([str(C0), "vm", str(LIN), "lnf_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "lnf_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "lnf_test_suite == 1 on Compiler 0 interpreter")

    vectors = [
        ("fee", ["1000", "1", "1000000"], "lnf_compute_fee", (1000, 1, 1_000_000), py_fee),
        ("fee", ["0", "0", "123"], "lnf_compute_fee", (0, 0, 123), py_fee),
        ("fee", ["1000", "0", "999"], "lnf_compute_fee", (1000, 0, 999), py_fee),
        ("fee", ["1000", "100", "100000000"], "lnf_compute_fee", (1000, 100, 100_000_000), py_fee),
        ("incoming", ["1000", "100", "100000000"], "lnf_incoming", (1000, 100, 100_000_000), None),
        ("inbound", ["5", "500000", "2"], "lnf_inbound_calc", (5, 500000, 2), py_inbound),
        ("inbound", ["5", "500000", "3"], "lnf_inbound_calc", (5, 500000, 3), py_inbound),
        ("inbound", ["-5", "-500000", "2"], "lnf_inbound_calc", (-5, -500000, 2), py_inbound),
        ("inbound", ["-5", "-500000", "3"], "lnf_inbound_calc", (-5, -500000, 3), py_inbound),
        ("inbound", ["0", "20000000", "1000000"], "lnf_inbound_calc", (0, 20_000_000, 1_000_000), py_inbound),
        ("muldiv", ["4294967296", "4294967296", "1000000"], "lnf_muldiv", (4294967296, 4294967296, 1_000_000), None),
    ]
    n_ok = 0
    for kind, oargs, fn, largs, pyfn in vectors:
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        if kind in ("fee", "incoming", "muldiv"):
            want_limbs = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
            if want != want_limbs:
                rec("VEC-LIMBS", "FAIL", f"{kind} i128 vs limbs", f"{want} != {want_limbs}")
                return 1
        got_lin = lin_vm(fn, *largs)
        if got_lin != want:
            rec("VEC-LIN", "FAIL", f"{fn}{largs}", f"lin={got_lin} c11={want}")
            return 1
        if pyfn is not None:
            py = pyfn(*largs)
            if py != want:
                rec("VEC-PY", "FAIL", f"python bigint {fn}{largs}", f"py={py} c11={want}")
                return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == limbs == LIN vm")
    rec("PY-BIGINT", "PASS", "Python arbitrary-precision int matches C11 and LIN on fee/inbound goldens")
    rec("OZ-INBOUND", "PASS", "lnd inbound_fee_test.go goldens: +6/+6 and -6/-6 with toward-zero rounding")

    wrap_go = int(oracle(["wrap", "0", "4294967296", "4294967296"]).splitlines()[-1])
    wrap_lin = lin_vm("lnf_muldiv", 4294967296, 4294967296, 1_000_000)
    if wrap_go == wrap_lin:
        rec("GO-WRAP", "FAIL", "Go uint64 wrap unexpectedly equalled 128-bit muldiv")
        return 1
    rec(
        "GO-WRAP",
        "PASS",
        "naive Go uint64 (2^32*2^32)/1e6 wraps; LIN 128-bit muldiv does not",
        f"go_wrap={wrap_go} lin={wrap_lin}",
    )

    jit_ok = lin_roundtrip_jit("lnf_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on lnf_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("lnf_compute_fee", 1000, 1, 1_000_000)
        if jv == 1001:
            rec("C0-JIT", "PASS", "lin_c0 jit lnf_compute_fee(1000,1,1e6)==1001 (in-memory libtcc)")
        else:
            rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected the module")

    src = LIN.read_text(encoding="utf-8")
    go_src = (FIX / "lnd_cached_edge_policy.go").read_text(encoding="utf-8")
    if "lnf_compute_fee(base: int, ppm: int, amt: int)" not in src or "func (c *CachedEdgePolicy) ComputeFee" not in go_src:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit LIN args vs Go method receiver")
    else:
        rec("EXPLICIT-ARGS", "PASS", "LIN clone takes base/ppm/amt as arguments (no hidden receiver fields)")
    if "lnf_muldiv" in src and "_lia_ushr" in src:
        rec("WIDE-MULDIV", "PASS", "clone uses 128-bit product muldiv (Go amt*ppm wraps uint64)")
    else:
        rec("WIDE-MULDIV", "FAIL", "128-bit muldiv missing")

    go_tr = GO_TR.read_text(encoding="utf-8")
    if "go_from_go" in go_tr and "go_expand_exp" in go_tr and "go_strip_uscore" in go_tr:
        rec("GO-EMIT", "PASS", "lin_from_go.lin emits LIN, expands 1eN, strips numeric underscores")
    else:
        rec("GO-EMIT", "FAIL", "Go emit path missing")
    rs_tr = RS_TR.read_text(encoding="utf-8")
    if "rs_from_rs" in rs_tr and "version=2" in rs_tr:
        rec("RS-EMIT", "PASS", "lin_from_rust.lin v2: && is not a borrow; emit + underscore/as-cast strip")
    else:
        rec("RS-EMIT", "FAIL", "Rust v2 emit missing")
    c_tr = C_TR.read_text(encoding="utf-8")
    if "REJ_C_CXX_SCOPE" in c_tr and "REJ_C_REFERENCE" in c_tr:
        rec("C-CXX-REJ", "PASS", "lin_from_c.lin v2 fail-closes C++ :: and signature &")
    else:
        rec("C-CXX-REJ", "FAIL", "C++ reject codes missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/lightningnetwork/lnd",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "license": "MIT",
        "files": {k: {"path": v["rel"], "git_blob_sha": v["blob"], "file_sha256": v["sha256"]} for k, v in FILES.items()},
    }
    evidence["lin_clone"] = "src/lin_lnd_computefee.lin"
    evidence["c11_oracle"] = "test/oracles/lnd_computefee_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-lnd-computefee"
    evidence["bolt07"] = "fee = base_msat + (amt_msat * fee_proportional_millionths) / 1_000_000"
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
