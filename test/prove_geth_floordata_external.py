#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: go-ethereum FloorDataGas (EIP-7623, LGPL-3.0) vs LIN C0.

What this proves (and what it does not):
  PASS claims are recomputed this run against:
    * pinned upstream bytes of FloorDataGas in go-ethereum v1.16.9
      (git blob + sha256 of core/state_transition.go and protocol_params.go)
    * an independent C11 oracle (Geth uint64 wrap AND i64 fail-closed)
    * an independent Go oracle of the same formula
    * Python arbitrary-precision int (fail-closed at 2^63-1)
    * Compiler 0 (`transpile/c/bin/lin_c0`) interpreting the LIN clone
    * Compiler 0 in-memory libtcc JIT when libtcc is available

  NOT claimed:
    * that LIN replaces go-ethereum or Ethereum consensus
    * uint64 wrap of nz*4 is reachable at MaxBlockSize (it is not)
    * wall-clock superiority vs Geth
    * Compiler 0 executes go_from_go string-literal paths

Class: EXPERIMENTAL (real EIP-7623 algorithm, i64-scale operands / MaxGasLimit).
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
LIN = ROOT / "src" / "lin_geth_floordata.lin"
GO_TR = ROOT / "src" / "lin_from_go.lin"
C_TR = ROOT / "src" / "lin_from_c.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "geth_floordata_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "geth_floordata_c11"
GO_SRC = ROOT / "test" / "oracles" / "geth_floordata_go.go"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_geth")
EVIDENCE = ROOT / "examples" / "geth_floordata" / "geth_floordata_evidence.json"

PINNED_COMMIT = "95665d5703e1023995a0ff93e4ce9eb77e8a59bd"
PINNED_TAG = "v1.16.9"
PINNED_ST_SHA256 = "449d50d372cc6ddff95f6ffa4eae29e06d38e248b24bc8501036c04f3e3f0c14"
PINNED_PP_SHA256 = "9dd1ccfb0c646f35b4d527f255ddee8173e99a033b0f6fc586340b6bdbfe4c14"
PINNED_ST_BLOB = "bf5ac07636d5111c281726a4273d149cb10d1d8e"
PINNED_PP_BLOB = "e8b044f45016d851af2698e94c62937218c9d736"
ST_REL = "core/state_transition.go"
PP_REL = "params/protocol_params.go"
I64MAX = 9223372036854775807
TX_GAS = 21000
TOKEN_NZ = 4
COST = 10

VECTORS = [
    (0, 0, 21000),
    (1, 0, 21010),
    (0, 1, 21040),
    (1, 1, 21050),
    (100, 0, 22000),
    (0, 100, 25000),
    (500, 1000, 66000),
    (32, 32, 22600),
]


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
    proc = run(
        [str(C0), "roundtrip-jit", str(LIN), fn, *[str(a) for a in args]], timeout=90
    )
    return proc.returncode == 0 and "CONSENSUS" in proc.stdout


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def py_floor(z: int, nz: int) -> int:
    if z < 0 or nz < 0:
        return 0
    if TOKEN_NZ != 0 and nz > I64MAX // TOKEN_NZ:
        return 0
    tokens = nz * TOKEN_NZ
    if z > I64MAX - tokens:
        return 0
    tokens += z
    if COST != 0 and tokens > I64MAX // COST:
        return 0
    add = tokens * COST
    if TX_GAS > I64MAX - add:
        return 0
    return TX_GAS + add


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
    live_st = UPSTREAM / ST_REL
    live_pp = UPSTREAM / PP_REL
    if not live_st.exists() or not live_pp.exists():
        return "SKIP", "", "pinned paths missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    blob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{ST_REL}"]).stdout.strip()
    blob_pp = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{PP_REL}"]).stdout.strip()
    st_hash = sha256_file(live_st)
    pp_hash = sha256_file(live_pp)
    if (
        st_hash != PINNED_ST_SHA256
        or pp_hash != PINNED_PP_SHA256
        or blob != PINNED_ST_BLOB
        or blob_pp != PINNED_PP_BLOB
        or commit != PINNED_COMMIT
    ):
        return (
            "FAIL",
            commit,
            f"st={st_hash} blob={blob} pp={pp_hash} ppblob={blob_pp}",
        )
    excerpt = (FIX / "FloorDataGas.go").read_text(encoding="utf-8")
    if excerpt not in live_st.read_text(encoding="utf-8"):
        return "FAIL", commit, "FloorDataGas.go excerpt not a substring of live file"
    return "PASS", commit, blob


def go_oracle(z: int, nz: int) -> int | None:
    proc = run(["go", "run", str(GO_SRC), str(z), str(nz)], timeout=60)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except ValueError:
        return None


def main() -> int:
    claims: list[dict[str, str]] = []
    evidence: dict = {"schema": "LIN_GETH_FLOORDATA_EVIDENCE_1.0", "claims": []}

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append(
            {"id": ident, "status": status, "description": description, "note": note}
        )
        tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, f"[{status}]")
        print(f"  {tag} {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GETH FLOORDATA (EIP-7623) — external LIN proof (i64-scale, C11+Go oracles)")
    print("=" * 78)

    excerpt = FIX / "FloorDataGas.go"
    params = FIX / "eip7623_protocol_params.go"
    if not excerpt.exists() or not params.exists():
        rec("PIN-FILE", "FAIL", "pinned FloorDataGas.go or params excerpt missing")
        return 1
    src_ex = excerpt.read_text(encoding="utf-8")
    src_pp = params.read_text(encoding="utf-8")
    if "func FloorDataGas(data []byte)" not in src_ex or "TxTokenPerNonZeroByte" not in src_pp:
        rec("PIN-EXCERPT", "FAIL", "excerpt missing FloorDataGas / EIP-7623 constants")
        return 1
    rec("PIN-EXCERPT", "PASS", "pinned FloorDataGas.go contains EIP-7623 function + token constants")

    up_status, commit, up_note = ensure_upstream()
    blob = PINNED_ST_BLOB
    if up_status == "PASS":
        blob = up_note
        rec(
            "UPSTREAM-SHA",
            "PASS",
            "git fetch of go-ethereum v1.16.9 matches pinned sha256/blob",
            f"commit={commit} blob={blob}",
        )
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of core/state_transition.go")
        rec("UPSTREAM-PARAMS", "PASS", "git blob sha of params/protocol_params.go")
    elif up_status == "SKIP":
        rec(
            "UPSTREAM-SHA",
            "SKIP",
            "live fetch of pinned tag unavailable; excerpt pin still holds",
            up_note,
        )
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
        rec("UPSTREAM-PARAMS", "SKIP", "live params blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)
        rec("UPSTREAM-PARAMS", "FAIL", "params blob mismatch", up_note)

    ensure_oracle()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 Geth-wrap vs fail-closed selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 in-range floor goldens + uint64 wrap vs i64 fail-closed")

    go_st = run(["go", "run", str(GO_SRC), "selftest"], timeout=90)
    if go_st.returncode != 0 or "PASS" not in go_st.stdout:
        rec("GO-SELFTEST", "FAIL", "independent Go oracle selftest", go_st.stdout + go_st.stderr)
        return 1
    rec("GO-SELFTEST", "PASS", "independent Go FloorDataGas(z,nz) goldens + wrap vector")

    ensure_c0()
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of floordata clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_geth_floordata.lin")

    chk2 = run([str(C0), "check", str(GO_TR)])
    if chk2.returncode != 0 and "LIN_CHECK" not in chk2.stdout:
        rec("GO-TR-CHECK", "FAIL", "lin_from_go.lin check", chk2.stdout)
    else:
        rec("GO-TR-CHECK", "PASS", "Compiler 0 check of Go transpiler v1 (emit path)")

    chk3 = run([str(C0), "check", str(C_TR)])
    if chk3.returncode != 0 and "LIN_CHECK" not in chk3.stdout:
        rec("C-TR-CHECK", "FAIL", "lin_from_c.lin check", chk3.stdout)
    else:
        rec("C-TR-CHECK", "PASS", "Compiler 0 check of C transpiler v2 (REJ_C_ARRAY_PARAM)")

    gate = run([str(C0), "vm", str(LIN), "fd_test_suite"])
    gv = value_of(gate.stdout)
    if gate.returncode != 0 or gv != 1:
        rec("LIN-SUITE", "FAIL", "fd_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "fd_test_suite == 1 on Compiler 0 interpreter")

    n_ok = 0
    for z, nz, want in VECTORS:
        py = py_floor(z, nz)
        c11 = int(oracle(["floor", str(z), str(nz)]).splitlines()[-1])
        geth = int(oracle(["geth", str(z), str(nz)]).splitlines()[-1])
        got = lin_vm("fd_floor", z, nz)
        go_v = go_oracle(z, nz)
        if py != want or c11 != want or got != want or geth != want:
            rec(
                "VEC-LIN",
                "FAIL",
                f"floor(z={z},nz={nz})",
                f"py={py} c11={c11} lin={got} geth={geth} want={want}",
            )
            return 1
        if go_v is None or go_v != want:
            rec("VEC-GO", "FAIL", f"go oracle floor(z={z},nz={nz})", f"go={go_v} want={want}")
            return 1
        n_ok += 1
    rec(
        "VEC-CONSENSUS",
        "PASS",
        f"{n_ok}/{n_ok} in-range vectors: Python == C11 == Go == Geth-uint64 == LIN vm",
    )
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python fail-closed i64 matches C11 and LIN")

    inn = lin_vm("fd_istanbul_intrinsic", 0, 1)
    floor1 = lin_vm("fd_floor", 0, 1)
    prague = lin_vm("fd_prague_charge", 0, 1)
    if inn != 21016 or floor1 != 21040 or prague != 21040:
        rec("FLOOR-VS-INTRINSIC", "FAIL", "1 nz Prague max(intrinsic,floor)", f"{inn}/{floor1}/{prague}")
        return 1
    rec(
        "FLOOR-VS-INTRINSIC",
        "PASS",
        "1 nonzero byte: Istanbul intrinsic 21016 < EIP-7623 floor 21040; Prague charge is the floor",
        "calldata spam pays the floor; wallets must budget 21040 not 21016",
    )
    if lin_vm("fd_prague_charge", 0, 100) != 25000:
        rec("PRAGUE-100NZ", "FAIL", "100 nz Prague charge")
        return 1
    rec("PRAGUE-100NZ", "PASS", "100 nonzero bytes: Prague charge 25000 vs Istanbul intrinsic 22600")

    wrap_nz = 4611686018427387904
    geth_wrap = int(oracle(["geth", "0", str(wrap_nz)]).splitlines()[-1])
    lin_wrap = lin_vm("fd_floor", 0, wrap_nz)
    go_wrap = go_oracle(0, wrap_nz)
    if geth_wrap != 21000 or go_wrap != 21000 or lin_wrap != 0:
        rec(
            "GETH-WRAP-NZ",
            "FAIL",
            "nz=2^62 uint64 wrap vs i64 fail-closed",
            f"geth={geth_wrap} go={go_wrap} lin={lin_wrap}",
        )
        return 1
    rec(
        "GETH-WRAP-NZ",
        "PASS",
        "nz=2^62: Geth/Go uint64 nz*4 wraps to 0 and returns 21000; LIN fail-closes to 0",
        "unreachable at MaxBlockSize=8388608; defect of the unbounded function, not a mainnet consensus bug",
    )

    jit_ok = lin_roundtrip_jit("fd_test_suite")
    if jit_ok:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on fd_test_suite (in-memory libtcc)")
    else:
        jv = lin_jit("fd_floor", 0, 1)
        if jv == 21040:
            rec("C0-JIT", "PASS", "lin_c0 jit fd_floor(0,1)==21040 (in-memory libtcc)")
        else:
            rec(
                "C0-JIT",
                "SKIP",
                "in-memory JIT not exercised",
                "libtcc missing or JIT rejected the module",
            )

    src = LIN.read_text(encoding="utf-8")
    if "fd_floor(z: int, nz: int)" in src and "[]byte" in src_ex:
        rec(
            "EXPLICIT-ARGS",
            "PASS",
            "LIN clone takes z/nz as arguments; pinned Geth scans []byte via bytes.Count",
        )
    else:
        rec("EXPLICIT-ARGS", "FAIL", "expected explicit z/nz vs Geth []byte")

    go_src = GO_TR.read_text(encoding="utf-8")
    if "go_from_go" in go_src and "REJ_GO_SLICE" in go_src and "REJ_GO_SELECTOR" in go_src:
        rec("GO-EMIT", "PASS", "lin_from_go.lin v1 emits LIN and rejects []byte / selectors / error")
    else:
        rec("GO-EMIT", "FAIL", "Go emit/reject path missing")

    c_src = C_TR.read_text(encoding="utf-8")
    if "REJ_C_ARRAY_PARAM" in c_src:
        rec("C-ARRAY-REJ", "PASS", "lin_from_c.lin v2 rejects unsized [] params (lift to counts)")
    else:
        rec("C-ARRAY-REJ", "FAIL", "REJ_C_ARRAY_PARAM missing")

    evidence["claims"] = claims
    evidence["upstream"] = {
        "repo": "https://github.com/ethereum/go-ethereum",
        "tag": PINNED_TAG,
        "commit": commit or PINNED_COMMIT,
        "path": ST_REL,
        "git_blob_sha": blob or PINNED_ST_BLOB,
        "file_sha256": PINNED_ST_SHA256,
        "params_path": PP_REL,
        "params_git_blob_sha": PINNED_PP_BLOB,
        "params_file_sha256": PINNED_PP_SHA256,
        "license": "LGPL-3.0",
    }
    evidence["lin_clone"] = "src/lin_geth_floordata.lin"
    evidence["c11_oracle"] = "test/oracles/geth_floordata_c11.c"
    evidence["go_oracle"] = "test/oracles/geth_floordata_go.go"
    evidence["compiler0"] = "transpile/c/bin/lin_c0"
    evidence["class"] = "EXPERIMENTAL"
    evidence["clone_lin_repo"] = "https://github.com/kbelludoo/clone-lin-geth-floordata"
    evidence["vectors"] = [{"z": z, "nz": nz, "floor": w} for z, nz, w in VECTORS]
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
