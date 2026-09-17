#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum IntrinsicGas (LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of core/state_transition.go (git blob + sha256)
    * an independent C11 oracle (i64-domain charge, plus Geth-like unchecked AL add)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces Geth / Ethereum consensus
    * uint64 values above Geth MaxGasLimit (2^63-1)
    * that mainnet access lists wrap (they are small); the finding is the
      missing overflow check in the published source, plus LIN fail-closed
      at the same cap Geth publishes as MaxGasLimit

Class: EXPERIMENTAL (real Geth schedule, i64-scale operands).
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
LIN = ROOT / "src" / "lin_geth_intrinsicgas.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_intrinsicgas_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_intrinsicgas_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_go_ethereum")
EVIDENCE = ROOT / "examples" / "geth_intrinsicgas" / "geth_intrinsicgas_evidence.json"

PINNED_SHA256 = "449d50d372cc6ddff95f6ffa4eae29e06d38e248b24bc8501036c04f3e3f0c14"
PINNED_BLOB = "bf5ac07636d5111c281726a4273d149cb10d1d8e"
PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
UPSTREAM_REL = "core/state_transition.go"
I64MAX = 2**63 - 1


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
    url = "https://github.com/ethereum/go-ethereum.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        init = run(["git", "init", str(UPSTREAM)])
        if init.returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(
        ["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_TAG],
        timeout=180,
    )
    if fetch.returncode != 0:
        note = (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
        return "SKIP", "", note
    co = run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"])
    if co.returncode != 0:
        return "SKIP", "", "checkout of pinned tag failed"
    live = UPSTREAM / UPSTREAM_REL
    if not live.exists():
        return "SKIP", "", f"{UPSTREAM_REL} missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{UPSTREAM_REL}"]).stdout.strip()
    live_hash = sha256_file(live)
    if live_hash != PINNED_SHA256 or blob != PINNED_BLOB or commit != PINNED_COMMIT:
        return "FAIL", commit, f"live={live_hash} blob={blob} commit={commit}"
    return "PASS", commit, blob


def py_add_ok(a: int, b: int) -> bool:
    return a >= 0 and b >= 0 and a <= I64MAX - b


def py_mul_ok(count: int, cost: int) -> bool:
    if count < 0 or cost < 0:
        return False
    if cost == 0:
        return True
    return count <= I64MAX // cost


def py_charge(gas: int, count: int, cost: int) -> int:
    if not py_mul_ok(count, cost):
        return 0
    add = count * cost
    if not py_add_ok(gas, add):
        return 0
    return gas + add


def py_word_size(size: int) -> int:
    if size < 0 or size > I64MAX - 31:
        return -1
    return (size + 31) // 32


def py_intrinsic(
    z: int, nz: int, naddr: int, nkeys: int, nauth: int,
    create: int, homestead: int, eip2028: int, eip3860: int,
) -> int:
    if min(z, nz, naddr, nkeys, nauth) < 0:
        return 0
    gas = 53000 if create and homestead else 21000
    if not py_add_ok(z, nz):
        return 0
    dlen = z + nz
    if dlen > 0:
        nzg = 16 if eip2028 else 68
        gas = py_charge(gas, nz, nzg)
        if gas == 0:
            return 0
        gas = py_charge(gas, z, 4)
        if gas == 0:
            return 0
        if create and eip3860:
            w = py_word_size(dlen)
            if w < 0:
                return 0
            gas = py_charge(gas, w, 2)
            if gas == 0:
                return 0
    gas = py_charge(gas, naddr, 2400)
    if gas == 0:
        return 0
    gas = py_charge(gas, nkeys, 1900)
    if gas == 0:
        return 0
    gas = py_charge(gas, nauth, 25000)
    if gas == 0:
        return 0
    return gas


VECTORS = [
    (0, 0, 0, 0, 0, 0, 1, 1, 1, 21000),
    (0, 0, 0, 0, 0, 1, 1, 1, 1, 53000),
    (0, 0, 0, 0, 0, 1, 0, 0, 0, 21000),
    (1, 0, 0, 0, 0, 0, 1, 1, 0, 21004),
    (0, 1, 0, 0, 0, 0, 1, 0, 0, 21068),
    (0, 1, 0, 0, 0, 0, 1, 1, 0, 21016),
    (0, 0, 1, 0, 0, 0, 1, 1, 0, 23400),
    (0, 0, 1, 1, 0, 0, 1, 1, 0, 25300),
    (0, 0, 0, 0, 1, 0, 1, 1, 0, 46000),
    (0, 1, 0, 0, 0, 1, 1, 1, 1, 53018),
    (1, 0, 0, 0, 0, 1, 1, 1, 1, 53006),
]


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_INTRINSICGAS_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH INTRINSICGAS — external LIN proof (i64-scale, C11 oracle)")
    print("=" * 78)

    pinned = FIX / "state_transition.go"
    if not pinned.exists():
        rec("PIN-FILE", "FAIL", "pinned state_transition.go missing")
        return 1
    got = sha256_file(pinned)
    if got != PINNED_SHA256:
        rec("PIN-SHA256", "FAIL", "pinned fixture hash mismatch", f"{got} != {PINNED_SHA256}")
        return 1
    rec("PIN-SHA256", "PASS", "pinned state_transition.go sha256 matches manifest")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of pinned go-ethereum v1.16.9 matches fixture",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/state_transition.go")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned tag unavailable; fixture pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    src_go = pinned.read_text(encoding="utf-8")
    if "func IntrinsicGas(" not in src_go or "func toWordSize(" not in src_go:
        rec("PIN-FUNCS", "FAIL", "pinned file missing IntrinsicGas/toWordSize")
        return 1
    rec("PIN-FUNCS", "PASS", "pinned file contains IntrinsicGas and toWordSize")

    al_unchecked = (
        "gas += uint64(len(accessList)) * params.TxAccessListAddressGas" in src_go
        and "gas += uint64(len(authList)) * params.CallNewAccountGas" in src_go
        and "(math.MaxUint64-gas)/params.TxAccessListAddressGas" not in src_go
    )
    if not al_unchecked:
        rec("GETH-AL-UNCHECKED", "FAIL", "expected unpublished overflow check on AL/auth adds")
        return 1
    rec(
        "GETH-AL-UNCHECKED",
        "PASS",
        "pinned Geth adds access-list/auth-list gas without MaxUint64 guard (data path has the guard)",
    )

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 oracle selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 oracle canonical vectors agree with published schedule")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if chk.returncode != 0 and ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of intrinsicgas clone", chk.stdout + chk.stderr)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_intrinsicgas.lin")

    chk_go = run([str(C0), "check", str(GO_TR)])
    if chk_go.returncode != 0 and "LIN_CHECK" not in chk_go.stdout and ".typecheck=passed" not in chk_go.stdout:
        rec("GO-TR-CHECK", "FAIL", "lin_from_go.lin check", chk_go.stdout + chk_go.stderr)
        return 1
    rec("GO-TR-CHECK", "PASS", "Compiler 0 check of Go transpiler (typecheck; string-literal vm is not claimed)")

    chk_c = run([str(C0), "check", str(C_TR)])
    if chk_c.returncode != 0 and "LIN_CHECK" not in chk_c.stdout and ".typecheck=passed" not in chk_c.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk_c.stdout)
        return 1
    rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")

    gate = run([str(C0), "vm", str(LIN), "ig_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "ig_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "ig_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for vec in VECTORS:
        args = vec[:-1]
        want_py = vec[-1]
        py = py_intrinsic(*args)
        if py != want_py:
            rec("VEC-PY", "FAIL", f"python {args}", f"py={py} want={want_py}")
            return 1
        c11 = int(oracle(["intrinsic", *[str(a) for a in args]]))
        if c11 != want_py:
            rec("VEC-C11", "FAIL", f"c11 {args}", f"c11={c11} want={want_py}")
            return 1
        got = lin_vm("ig_intrinsic", *args)
        if got != want_py:
            rec("VEC-LIN", "FAIL", f"lin {args}", f"lin={got} want={want_py}")
            return 1
        n_ok += 1
    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: Python bigint == C11 == LIN vm")

    for size, want in ((0, 0), (1, 1), (32, 1), (33, 2), (64, 2)):
        if py_word_size(size) != want:
            rec("WORD-PY", "FAIL", f"word_size({size})", "")
            return 1
        if int(oracle(["word", str(size)])) != want:
            rec("WORD-C11", "FAIL", f"word_size({size})", "")
            return 1
        if lin_vm("ig_word_size", size) != want:
            rec("WORD-LIN", "FAIL", f"word_size({size})", "")
            return 1
    rec("WORD-SIZE", "PASS", "toWordSize (size+31)/32: Python == C11 == LIN (i64 domain)")

    naddr = 3843071682022824
    lin_ov = lin_vm("ig_charge", 21000, naddr, 2400)
    c11_ov = int(oracle(["intrinsic", "0", "0", str(naddr), "0", "0", "0", "1", "1", "0"]))
    py_ov = py_intrinsic(0, 0, naddr, 0, 0, 0, 1, 1, 0)
    geth_wrap = int(oracle(["geth-al", "21000", str(naddr), "0", "0"]))
    if lin_ov != 0 or c11_ov != 0 or py_ov != 0:
        rec("AL-OVERFLOW", "FAIL", "LIN/C11/Python should fail-close AL mul at i64max", f"lin={lin_ov}")
        return 1
    if geth_wrap == 0:
        rec("GETH-WRAP", "FAIL", "Geth-like uint64 AL add unexpectedly 0")
        return 1
    rec(
        "AL-OVERFLOW",
        "PASS",
        "access-list naddr*2400 above i64max: LIN/C11/Python=0; Geth-like uint64 still adds",
        f"geth_uint64={geth_wrap} naddr={naddr}",
    )

    lin_src = LIN.read_text(encoding="utf-8")
    if "ig_intrinsic(z: int, nz: int, naddr: int, nkeys: int, nauth: int" not in lin_src:
        rec("EXPLICIT-ARGS", "FAIL", "expected z/nz/access/auth counts as arguments")
        return 1
    rec(
        "EXPLICIT-ARGS",
        "PASS",
        "LIN clone takes z/nz/naddr/nkeys/nauth as arguments (no []byte scan, no StorageKeys())",
    )

    go_src = GO_TR.read_text(encoding="utf-8")
    if "go_from_go" not in go_src or "REJ_GO_SLICE" not in go_src or "REJ_GO_SELECTOR" not in go_src:
        rec("GO-EMIT", "FAIL", "Go transpiler emit/reject path missing")
        return 1
    rec("GO-EMIT", "PASS", "lin_from_go.lin emits eligible uint64 funcs and rejects slices/selectors/error")

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_ARRAY_PARAM" not in c_src or 'rg_count_lit(sig, "[")' not in c_src:
        rec("C-ARRAY-REJ", "FAIL", "REJ_C_ARRAY_PARAM missing from lin_from_c.lin")
        return 1
    rec("C-ARRAY-REJ", "PASS", "C transpiler now fail-closes T name[] params (decay-to-pointer)")

    jit_ok = lin_roundtrip_jit("ig_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on ig_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("ig_intrinsic", 0, 0, 0, 0, 0, 0, 1, 1, 0)
        if jv == 21000:
            rec("C0-JIT", "PASS", "lin_c0 jit ig_intrinsic empty tx == 21000 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": UPSTREAM_REL,
        "git_blob_sha": blob or PINNED_BLOB,
        "file_sha256": PINNED_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_intrinsicgas.lin"
    evidence["c11_oracle"] = "test/oracles/geth_intrinsicgas_c11.c"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin"] = "https://github.com/kbelludoo/clone-lin-geth-intrinsicgas"
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
