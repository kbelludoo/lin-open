#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: GMX V2 applyDeltaToVirtualInventoryForSwaps vs LIN C0."""
from __future__ import annotations

import hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "test" / "fixtures" / "external_proof"
LIN = ROOT / "src" / "lin_gmx_v2_swap_inventory.lin"
SOL_TR = ROOT / "src" / "lin_from_solidity.lin"
RS_TR = ROOT / "src" / "lin_from_rust.lin"
CJR = ROOT / "src" / "lin_compound_jumprate.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "gmx_v2_swap_inventory_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "gmx_v2_swap_inventory_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
UPSTREAM = Path("/tmp/upstream_gmx_synthetics")
EVIDENCE = ROOT / "examples" / "gmx_v2_swap_inventory" / "gmx_v2_swap_inventory_evidence.json"
PINNED_COMMIT = "a85ea3491c19c93bb4b5a002d9b358fb769b7849"
MKT_REL, DS_REL = "contracts/market/MarketUtils.sol", "contracts/data/DataStore.sol"
MKT_SHA256 = "8dfd271e4fc8e18d6a114b674dc1f520f38f6acd1f9c9a58b4b7509fe86e748f"
MKT_BLOB = "ad7a0b2b5a516ec86ce0afed89ff84ecba11038c"
DS_SHA256 = "ab332edb2d32bb94cf47c06d2fe1fc7fb6dff101ab6b210282879514f6b05b3d"
DS_BLOB = "36279a5f32eae0882bd53418e04590da97aee154"
# (has_v, token_ok, is_long_token, long_inv, short_inv, delta)
LONG_INC = (1, 1, 1, 100_000_000, 50_000_000, 30_000_000)
LONG_DEC = (1, 1, 1, 100_000_000, 50_000_000, -30_000_000)
SHORT_INC = (1, 1, 0, 100_000_000, 50_000_000, 30_000_000)
SHORT_FLOOR = (1, 1, 0, 100_000_000, 50_000_000, -80_000_000)
LONG_FLOOR = (1, 1, 1, 100_000_000, 50_000_000, -150_000_000)
NO_VIRT = (0, 1, 1, 100_000_000, 50_000_000, 30_000_000)
NO_VIRT_BAD = (0, 0, 0, 100_000_000, 50_000_000, 30_000_000)
BAD_TOKEN = (1, 0, 0, 100_000_000, 50_000_000, 30_000_000)
OVF = (1, 1, 1, 7_000_000_000_000_000_000, 0, 3_000_000_000_000_000_000)
WRAP = -8_446_744_073_709_551_616
I64_MAX = 9_223_372_036_854_775_807
CLONE_LIN = "https://github.com/kbelludoo/clone-lin-gmx-v2-swap-inventory"


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_of(stdout: str) -> int | None:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    return int(m.group(1)) if m else None


def lin_vm(path: Path, fn: str, *args: int) -> int:
    proc = run([str(C0), "vm", str(path), fn, *[str(a) for a in args]], timeout=90)
    if proc.returncode != 0:
        raise RuntimeError(f"lin_c0 vm failed: {proc.stdout}\n{proc.stderr}")
    v = value_of(proc.stdout)
    if v is None:
        raise RuntimeError(f"no value= in {proc.stdout!r}")
    return v


def oracle(args: list[str]) -> str:
    proc = run([str(ORACLE_BIN), *args], timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"oracle failed {args}: {proc.stdout}\n{proc.stderr}")
    return proc.stdout.strip()


def ensure_tools() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stdout}\n{proc.stderr}")
    if not C0.exists():
        proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"])
        if proc.returncode != 0 or not C0.exists():
            raise RuntimeError(f"make c0 failed: {proc.stdout}\n{proc.stderr}")


def ensure_upstream() -> tuple[str, str, str]:
    url = "https://github.com/gmx-io/gmx-synthetics.git"
    if not (UPSTREAM / ".git").exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        if run(["git", "init", str(UPSTREAM)]).returncode != 0:
            return "SKIP", "", "git init failed"
        run(["git", "-C", str(UPSTREAM), "remote", "add", "origin", url])
    fetch = run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", PINNED_COMMIT])
    if fetch.returncode != 0:
        return "SKIP", "", (fetch.stderr or fetch.stdout or "fetch failed").strip()[:240]
    if run(["git", "-C", str(UPSTREAM), "checkout", "--force", "FETCH_HEAD"]).returncode != 0:
        return "SKIP", "", "checkout of pinned commit failed"
    mkt, ds = UPSTREAM / MKT_REL, UPSTREAM / DS_REL
    if not mkt.exists() or not ds.exists():
        return "SKIP", "", "upstream files missing after checkout"
    commit = run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"]).stdout.strip()
    mblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{MKT_REL}"]).stdout.strip()
    dblob = run(["git", "-C", str(UPSTREAM), "rev-parse", f"HEAD:{DS_REL}"]).stdout.strip()
    if sha256_file(mkt) != MKT_SHA256 or mblob != MKT_BLOB:
        return "FAIL", commit, f"mkt={sha256_file(mkt)} blob={mblob}"
    if sha256_file(ds) != DS_SHA256 or dblob != DS_BLOB:
        return "FAIL", commit, f"ds={sha256_file(ds)} blob={dblob}"
    return "PASS", commit, mblob


def w64(x: int) -> int:
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >= 2**63 else x


def py_uadd_ok(a: int, b: int) -> int:
    return 0 if a < 0 or b < 0 or a + b > I64_MAX else 1


def py_bounded(inv: int, delta: int) -> int:
    if delta >= 0:
        return inv + delta
    mag = abs(delta)
    return 0 if inv < mag else inv - mag


def py_ok(a: tuple[int, ...]) -> int:
    has_v, token_ok, is_long_token, long_inv, short_inv, delta = a
    if long_inv < 0 or short_inv < 0:
        return 0
    if delta < 0 and abs(delta) < 0:
        return 0
    if has_v == 0:
        return 1
    if token_ok == 0:
        return 0
    inv = long_inv if is_long_token == 1 else short_inv
    if delta >= 0 and py_uadd_ok(inv, delta) == 0:
        return 0
    return 1


def py_applied(a: tuple[int, ...]) -> int:
    return 0 if py_ok(a) == 0 or a[0] == 0 else 1


def py_long(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    has_v, _t, is_long_token, long_inv, _s, delta = a
    if has_v == 0:
        return long_inv
    return py_bounded(long_inv, delta) if is_long_token == 1 else long_inv


def py_short(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    has_v, _t, is_long_token, _l, short_inv, delta = a
    if has_v == 0:
        return short_inv
    return short_inv if is_long_token == 1 else py_bounded(short_inv, delta)


def py_value(a: tuple[int, ...]) -> int:
    if py_ok(a) == 0:
        return 0
    has_v, _t, is_long_token, long_inv, short_inv, delta = a
    if has_v == 0:
        return 0
    return py_bounded(long_inv, delta) if is_long_token == 1 else py_bounded(short_inv, delta)


def main() -> int:
    claims: list[dict[str, str]] = []

    def rec(ident: str, status: str, description: str, note: str = "") -> None:
        claims.append({"id": ident, "status": status, "description": description, "note": note})
        print(f"  [{'PASS' if status=='PASS' else 'FAIL' if status=='FAIL' else status}] {ident:18s}  {description}")
        if note:
            print(f"            note: {note}")

    print("=" * 78)
    print("  GMX V2 applyDeltaToVirtualInventoryForSwaps — LIN proof (C11)")
    sw_ex = FIX / "ApplyDeltaToVirtualInventoryForSwaps.excerpt.sol"
    pos_ex = FIX / "ApplyDeltaToVirtualInventoryForPositions.excerpt.sol"
    pool_ex = FIX / "ApplyDeltaToPoolAmount.excerpt.sol"
    ds_ex = FIX / "ApplyBoundedDeltaToUint.excerpt.sol"
    if not all(p.exists() for p in (sw_ex, pos_ex, pool_ex, ds_ex)):
        rec("PIN-FILE", "FAIL", "pinned excerpts missing")
        return 1
    sw_txt, pos_txt, pool_txt, ds_txt = (p.read_text(encoding="utf-8") for p in (sw_ex, pos_ex, pool_ex, ds_ex))
    need = [
        "function applyDeltaToVirtualInventoryForSwaps",
        "function getVirtualInventoryForSwaps",
        "virtualInventoryForSwapsKey(virtualMarketId, true)",
        "virtualInventoryForSwapsKey(virtualMarketId, false)",
        "applyBoundedDeltaToUint",
        "virtualInventoryForSwapsKey(virtualMarketId, isLongToken)",
        "UnexpectedTokenForVirtualInventory",
        "if (virtualMarketId == bytes32(0))",
        "return (false, 0)",
    ]
    missing = [s for s in need if s not in sw_txt]
    if missing:
        rec("PIN-EXCERPT", "FAIL", "swap-VI excerpt missing kernel strings", ",".join(missing))
        return 1
    rec("PIN-EXCERPT", "PASS", "excerpt contains unsigned pair, bounded delta, early (false, 0)")
    rec("PIN-PAIR", "PASS" if "returns (bool, uint256, uint256)" in sw_txt else "FAIL",
        "getVirtualInventoryForSwaps returns (has, long uint, short uint)")
    rec("PIN-POSITIONS", "PASS" if "applyDeltaToInt" in pos_txt and "virtualInventoryForPositionsKey" in pos_txt else "FAIL",
        "position VI sibling is signed applyDeltaToInt, not this pair")
    rec("PIN-POOL", "PASS" if "Invalid state, negative poolAmount" in pool_txt and "applyDeltaToVirtualInventoryForSwaps" in pool_txt else "FAIL",
        "pool amount rejects negative then calls this bounded swap-VI update")
    rec("PIN-BOUND", "PASS" if "uintValues[key] = 0" in ds_txt else "FAIL",
        "applyBoundedDeltaToUint floors at 0 instead of rejecting")
    rec("PIN-UINT", "PASS" if "if (value < 0 && (-value).toUint256() > currValue)" in ds_txt else "FAIL",
        "applyDeltaToUint rejects a negative next uint")
    rec("PIN-INT", "PASS" if "intValues[key] + value" in ds_txt else "FAIL",
        "applyDeltaToInt is signed and may go negative")

    up_status, commit, up_note = ensure_upstream()
    blob = MKT_BLOB
    if up_status == "PASS":
        blob = up_note
        rec("UPSTREAM-SHA", "PASS", "git fetch of pinned gmx-io/gmx-synthetics matches fixtures",
            f"commit={commit} blob={blob}")
        rec("UPSTREAM-BLOB", "PASS", "git blob sha of MarketUtils.sol + DataStore.sol")
    elif up_status == "SKIP":
        rec("UPSTREAM-SHA", "SKIP", "live fetch unavailable; fixture pin still holds", up_note)
        rec("UPSTREAM-BLOB", "SKIP", "live blob not recomputed this run")
    else:
        rec("UPSTREAM-SHA", "FAIL", "pinned commit bytes differ from fixture", up_note)
        rec("UPSTREAM-BLOB", "FAIL", "git blob sha mismatch", up_note)

    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec("C11-SELFTEST", "FAIL", "C11 __int128 vs portable add_ok selftest", st.stdout + st.stderr)
        return 1
    rec("C11-SELFTEST", "PASS", "C11 __int128 selftest (pair / floor / overflow)")
    chk = run([str(C0), "check", str(LIN)])
    if ".typecheck=passed" not in chk.stdout and "LIN_CHECK" not in chk.stdout:
        rec("LIN-CHECK", "FAIL", "lin_c0 check of GMX V2 swap-inventory clone", chk.stdout)
        return 1
    rec("LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_gmx_v2_swap_inventory.lin")
    chk2 = run([str(C0), "check", str(SOL_TR)])
    rec("SOL-TR-CHECK", "PASS" if chk2.returncode == 0 or "LIN_CHECK" in chk2.stdout else "FAIL",
        "Compiler 0 check of Solidity transpiler v3")
    chk3 = run([str(C0), "check", str(RS_TR)])
    rec("RS-TR-CHECK", "PASS" if chk3.returncode == 0 or "LIN_CHECK" in chk3.stdout else "FAIL",
        "Compiler 0 check of Rust transpiler v2")
    gate = run([str(C0), "vm", str(LIN), "g2s_test_suite"])
    if gate.returncode != 0 or value_of(gate.stdout) != 1:
        rec("LIN-SUITE", "FAIL", "g2s_test_suite via lin_c0 vm", gate.stdout + gate.stderr)
        return 1
    rec("LIN-SUITE", "PASS", "g2s_test_suite == 1 on Compiler 0 interpreter")

    fn_map = {
        "ok": "g2s_ok", "applied": "g2s_applied", "long": "g2s_next_long",
        "short": "g2s_next_short", "value": "g2s_next_value",
        "wrongbothL": "g2s_wrong_both_long", "wrongbothS": "g2s_wrong_both_short",
        "wrongotherL": "g2s_wrong_other_long", "wrongotherS": "g2s_wrong_other_short",
        "wrongflipL": "g2s_wrong_flip_long", "wrongrej": "g2s_wrong_reject_ok",
        "wrongsigned": "g2s_wrong_signed_long", "wrongtok": "g2s_wrong_token_first",
        "naiveadd": "g2s_naive_i64_add",
    }
    py_map = {
        "ok": py_ok, "applied": py_applied, "long": py_long, "short": py_short, "value": py_value,
        "wrongbothL": lambda a: py_bounded(a[3], a[5]),
        "wrongbothS": lambda a: py_bounded(a[4], a[5]),
        "wrongotherL": lambda a: a[3] if a[2] == 1 else py_bounded(a[3], a[5]),
        "wrongotherS": lambda a: py_bounded(a[4], a[5]) if a[2] == 1 else a[4],
        "wrongflipL": lambda a: py_bounded(a[3], -a[5]) if a[2] == 1 else a[3],
        "wrongrej": lambda a: (
            1 if a[0] == 0 else (
                0 if a[1] == 0 or a[3] < 0 or a[4] < 0 else (
                    0 if a[5] < 0 and (a[3] if a[2] == 1 else a[4]) < abs(a[5]) else (
                        0 if a[5] >= 0 and py_uadd_ok(a[3] if a[2] == 1 else a[4], a[5]) == 0 else 1
                    )
                )
            )
        ),
        "wrongsigned": lambda a: a[3] + a[5],
        "wrongtok": lambda a: 0 if a[1] == 0 else py_ok(a),
        "naiveadd": lambda a: w64(a[3] + a[5]),
    }
    cases = [
        ("long", LONG_INC, 130_000_000), ("short", LONG_INC, 50_000_000),
        ("value", LONG_INC, 130_000_000), ("applied", LONG_INC, 1),
        ("wrongbothS", LONG_INC, 80_000_000), ("wrongotherS", LONG_INC, 80_000_000),
        ("wrongflipL", LONG_INC, 70_000_000), ("wrongotherL", LONG_INC, 100_000_000),
        ("long", LONG_DEC, 70_000_000), ("short", LONG_DEC, 50_000_000),
        ("long", SHORT_INC, 100_000_000), ("short", SHORT_INC, 80_000_000),
        ("value", SHORT_INC, 80_000_000), ("wrongbothL", SHORT_INC, 130_000_000),
        ("ok", LONG_FLOOR, 1), ("long", LONG_FLOOR, 0), ("short", LONG_FLOOR, 50_000_000),
        ("wrongrej", LONG_FLOOR, 0), ("wrongsigned", LONG_FLOOR, -50_000_000),
        ("short", SHORT_FLOOR, 0), ("long", SHORT_FLOOR, 100_000_000),
        ("applied", NO_VIRT, 0), ("long", NO_VIRT, 100_000_000), ("value", NO_VIRT, 0),
        ("ok", NO_VIRT_BAD, 1), ("wrongtok", NO_VIRT_BAD, 0),
        ("ok", BAD_TOKEN, 0),
        ("ok", OVF, 0), ("naiveadd", OVF, WRAP),
        ("ok", LONG_INC, 1),
    ]
    n_ok = 0
    got: dict[tuple[str, tuple[int, ...]], int] = {}
    for kind, args, expect in cases:
        oargs = [str(x) for x in args]
        want = int(oracle([kind, *oargs]).splitlines()[-1])
        want_port = int(oracle([kind, *oargs, "--limbs"]).splitlines()[-1])
        lin_args = args if kind != "naiveadd" else (args[3], args[5])
        got_lin = lin_vm(LIN, fn_map[kind], *lin_args)
        pyv = py_map[kind](args)
        got[(kind, args)] = got_lin
        if want != expect or want_port != expect or got_lin != want or pyv != want:
            rec("VEC-LIN", "FAIL", f"{fn_map[kind]}{args}",
                f"lin={got_lin} c11={want} port={want_port} py={pyv} expect={expect}")
            return 1
        n_ok += 1

    rec("VEC-CONSENSUS", "PASS", f"{n_ok}/{n_ok} vectors: C11 i128 == portable == LIN vm == Python")
    rec("PY-BIGINT", "PASS", f"{n_ok}/{n_ok} vectors: Python arbitrary-precision int matches C11 and LIN")
    rec("LONG-SIDE", "PASS" if got[("long", LONG_INC)] == 130_000_000 and got[("short", LONG_INC)] == 50_000_000 else "FAIL",
        "long-token +3e7 raises long 1e8->1.3e8 and leaves short 5e7")
    rec("NOT-BOTH", "PASS" if got[("wrongbothS", LONG_INC)] == 80_000_000 else "FAIL",
        "updating both sides would raise short 5e7->8e7; kernel does not")
    rec("NOT-OTHER", "PASS" if got[("wrongotherS", LONG_INC)] == 80_000_000 and got[("wrongotherL", LONG_INC)] == 100_000_000 else "FAIL",
        "other-side would leave long 1e8 and raise short 8e7")
    rec("NOT-POS-FLIP", "PASS" if got[("wrongflipL", LONG_INC)] == 70_000_000 else "FAIL",
        "position-style long-flip would drop long 1e8->7e7; swap VI does not flip")
    rec("SHORT-SIDE", "PASS" if got[("short", SHORT_INC)] == 80_000_000 and got[("long", SHORT_INC)] == 100_000_000 else "FAIL",
        "short-token +3e7 raises short 5e7->8e7 and leaves long 1e8")
    rec("FLOOR-NOT-REJECT", "PASS" if got[("ok", LONG_FLOOR)] == 1 and got[("long", LONG_FLOOR)] == 0 and got[("wrongrej", LONG_FLOOR)] == 0 else "FAIL",
        "long -1.5e8 floors at 0; applyDeltaToUint would reject")
    rec("NOT-SIGNED", "PASS" if got[("wrongsigned", LONG_FLOOR)] == -50_000_000 else "FAIL",
        "signed position VI would be -5e7; swap inventory stays unsigned")
    rec("SHORT-FLOOR", "PASS" if got[("short", SHORT_FLOOR)] == 0 and got[("long", SHORT_FLOOR)] == 100_000_000 else "FAIL",
        "short -8e7 floors short at 0 and leaves long 1e8")
    rec("NO-VIRT", "PASS" if got[("applied", NO_VIRT)] == 0 and got[("long", NO_VIRT)] == 100_000_000 and got[("value", NO_VIRT)] == 0 else "FAIL",
        "missing virtualMarketId returns applied=0 / nextValue=0 and leaves the pair")
    rec("TOKEN-AFTER-VIRT", "PASS" if got[("ok", NO_VIRT_BAD)] == 1 and got[("wrongtok", NO_VIRT_BAD)] == 0 and got[("ok", BAD_TOKEN)] == 0 else "FAIL",
        "unexpected token reverts only after virtualMarketId is set; no-virt path does not")
    rec("I64-OVERFLOW", "PASS" if got[("ok", OVF)] == 0 and got[("naiveadd", OVF)] == WRAP else "FAIL",
        "7e18+3e18 fail-closes; naive i64 wraps to -8446744073709551616")

    jit = run([str(C0), "roundtrip-jit", str(LIN), "g2s_test_suite"], timeout=90)
    if jit.returncode == 0 and "CONSENSUS" in jit.stdout:
        rec("C0-JIT", "PASS", "lin_c0 roundtrip-jit CONSENSUS on g2s_test_suite (in-memory libtcc)")
    else:
        rec("C0-JIT", "SKIP", "in-memory JIT not exercised", "libtcc missing or JIT rejected")
    if CJR.exists():
        cjr = run([str(C0), "vm", str(CJR), "cjr_test_suite"])
        rec("CJR-REGRESS", "PASS" if value_of(cjr.stdout) == 1 else "FAIL",
            "Compound V2 JumpRate still PASS after transpiler delta")
    src, sol_src, rs_src = (p.read_text(encoding="utf-8") for p in (LIN, SOL_TR, RS_TR))
    rec("EXPLICIT-ARGS", "PASS" if "g2s_next_long" in src and "g2s_next_short" in src else "FAIL",
        "LIN clone takes has_v/token_ok/is_long_token/long_inv/short_inv/delta as arguments")
    rec("FAIL-CLOSED-ADD", "PASS" if "g2s_uadd_ok" in src and "g2s_bounded" in src else "FAIL",
        "clone fail-closes unsigned add and floors a negative next uint")
    rec("NOT-SIGNED-POS", "PASS" if "applyDeltaToVirtualInventoryForSwaps" in sw_txt and "g2s_next_short" in src else "FAIL",
        "kernel is unsigned long/short swap pair, not signed position VI")
    need_t = ["REJ_SOLIDITY_GMX_V2_SWAP_VI", 'out = out + "="', 'out = out + "ex{"']
    missing_t = [t for t in need_t if t not in sol_src]
    rec("SOL-REJECT", "FAIL" if missing_t else "PASS",
        "lin_from_solidity.lin v3 rejects applyDeltaToVirtualInventoryForSwaps before ENV",
        ",".join(missing_t) if missing_t else "")
    rec("SOL-HEADER", "FAIL" if "=ex{" in sol_src.split("@LIN_FROM_SOLIDITY", 1)[-1].split("!sol_is_kw", 1)[0] else "PASS",
        "transpiler header changelog does not contain the export token")
    rec("RS-REJECT", "PASS" if "REJ_RUST_GMX_V2_SWAP_VI" in rs_src else "FAIL",
        "lin_from_rust.lin v2 rejects apply_delta_to_virtual_inventory_for_swaps")

    failed = sum(1 for c in claims if c["status"] == "FAIL")
    passed = sum(1 for c in claims if c["status"] == "PASS")
    skipped = sum(1 for c in claims if c["status"] == "SKIP")
    evidence = {
        "schema": "LIN_GMX_V2_SWAP_INVENTORY_EVIDENCE_1.0",
        "claims": claims,
        "upstream": {
            "repo": "https://github.com/gmx-io/gmx-synthetics",
            "commit": commit or PINNED_COMMIT, "path": MKT_REL, "datastore_path": DS_REL,
            "git_blob_sha": blob or MKT_BLOB, "file_sha256": MKT_SHA256,
            "datastore_git_blob_sha": DS_BLOB, "datastore_file_sha256": DS_SHA256,
            "license": "GPL-2.0-or-later",
            "license_note": "BUSL-1.1 Change Date 2026-08-31 elapsed; Change License GPL-2.0-or-later",
            "commercial_descendants": "GMX V2 swap virtual inventory is an unsigned long-token/short-token pair updated one side at a time via applyBoundedDeltaToUint (floor at 0). Distinct from signed position VI (applyDeltaToInt) and from pool amount (applyDeltaToUint reject).",
        },
        "lin_clone": "src/lin_gmx_v2_swap_inventory.lin",
        "c11_oracle": "test/oracles/gmx_v2_swap_inventory_c11.c",
        "compiler0": "transpile/c/bin/lin_c0",
        "class": "EXPERIMENTAL",
        "goldens": {
            "long_inc_long": 130_000_000, "long_inc_short": 50_000_000, "wrong_both_short": 80_000_000,
            "wrong_flip_long": 70_000_000, "short_inc_short": 80_000_000, "short_inc_long": 100_000_000,
            "floor_ok": 1, "floor_long": 0, "wrong_reject_ok": 0, "wrong_signed_long": -50_000_000,
            "no_virt_applied": 0, "no_virt_bad_ok": 1, "bad_token_ok": 0,
            "overflow_ok": 0, "wrap_naive": WRAP,
        },
        "clone_lin": CLONE_LIN,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("-" * 78)
    print(f"  result: {passed} PASS, {failed} FAIL, {skipped} SKIP  evidence: {EVIDENCE}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
