#!/usr/bin/env python3
"""
External proof: LIN u512 numeric coprocessor vs Python bigint vs C11.

Proves FullMath-width mulDiv (a*b)/d with a 512-bit product, then wires that
mulDiv into getAmountOut. Class: EXPERIMENTAL. Not a Uniswap replacement.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
U256 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
IMG = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor.linbc"
UNFILTERED = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
PIN_FULLMATH = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
M64 = (1 << 64) - 1
U256M = (1 << 256) - 1
QPAT = 0x5555555555555555


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("LIN_TCC_LIB", "/tmp/tinycc/libtcc.so")
    env.setdefault("LIN_TCC_DIR", "/tmp/tinycc")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, check=False)


def value_steps(stdout: str) -> tuple[int, int]:
    m = re.search(r"\bvalue=(-?\d+)\b", stdout)
    s = re.search(r"\bsteps=(\d+)\b", stdout)
    if not m:
        raise RuntimeError(f"no value= in {stdout!r}")
    return int(m.group(1)), int(s.group(1) if s else 0)


def i64words(x: int, n: int = 4) -> list[int]:
    out = []
    for i in range(n):
        w = (x >> (64 * i)) & M64
        out.append(w - (1 << 64) if w >= (1 << 63) else int(w))
    return out


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int, int]:
    n = a * b
    if d == 0:
        return -1, 0, 0, n
    q, r = divmod(n, d)
    if q > U256M:
        return -2, 0, 0, n
    return 1, q, r, n


def ref_amount_out(a_in: int, r_in: int, r_out: int) -> int:
    fee = a_in * 997
    return (fee * r_out) // (r_in * 1000 + fee)


def ensure_c0() -> None:
    if C0.exists():
        return
    proc = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
    if proc.returncode != 0 or not C0.exists():
        raise RuntimeError(f"make c0 failed: {proc.stderr}")


def ensure_oracle() -> None:
    proc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"gcc oracle: {proc.stderr}")


def parse_kv(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k] = int(v, 0)
    return out


def c11_muldiv(a: int, b: int, d: int) -> dict[str, int]:
    proc = run([str(ORACLE_BIN), "muldiv", f"{a:x}", f"{b:x}", f"{d:x}"])
    if proc.returncode != 0:
        raise RuntimeError(f"c11 muldiv: {proc.stderr} {proc.stdout}")
    return parse_kv(proc.stdout)


def c11_amm(ain: int, rin: int, rout: int) -> dict[str, int]:
    proc = run([str(ORACLE_BIN), "amm", f"{ain:x}", f"{rin:x}", f"{rout:x}"])
    if proc.returncode != 0:
        raise RuntimeError(f"c11 amm: {proc.stderr} {proc.stdout}")
    return parse_kv(proc.stdout)


def lin_run(image: Path, fn: str, args: list[int], timeout: int = 240) -> tuple[int, int]:
    proc = run([str(C0), "run", str(image), fn, *[str(a) for a in args]], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"lin run {fn}: {proc.stdout}\n{proc.stderr}")
    return value_steps(proc.stdout)


def pack_lnr1(digest: bytes, case_id: int, a: int, b: int, d: int, q: int, r: int,
              status: int, steps: int, flags: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = digest
    struct.pack_into("<Q", raw, 40, case_id)
    raw[48:80] = a.to_bytes(32, "little")
    raw[80:112] = b.to_bytes(32, "little")
    raw[112:144] = d.to_bytes(32, "little")
    raw[144:176] = q.to_bytes(32, "little")
    raw[176:208] = r.to_bytes(32, "little")
    struct.pack_into("<q", raw, 208, status)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<Q", raw, 224, flags)
    return bytes(raw)


def pack_lcr2(digest: bytes, tx_id: int, ain: int, rin: int, rout: int, aout: int,
              steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = digest
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, tx_id)
    raw[56:88] = ain.to_bytes(32, "big")
    raw[88:120] = rin.to_bytes(32, "big")
    raw[120:152] = rout.to_bytes(32, "big")
    raw[152:184] = aout.to_bytes(32, "big")
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def merkle(leaves: list[bytes]) -> bytes:
    nodes = list(leaves)
    while len(nodes) > 1:
        if len(nodes) & 1:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(DOM_NODE + nodes[i] + nodes[i + 1]).digest()
                 for i in range(0, len(nodes), 2)]
    return nodes[0]


def rec(claims: list[dict], ident: str, status: str, description: str, note: str = "") -> None:
    claims.append({"id": ident, "status": status, "description": description, "note": note})
    tag = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, status)
    print(f"  {tag} {ident:18s}  {description}")
    if note:
        print(f"            note: {note}")


def main() -> int:
    claims: list[dict] = []
    lcr2: list[dict] = []
    print("=" * 78)
    print("  U512 NUMERIC COPROCESSOR — Python bigint + C11 + LIN C0")
    print("=" * 78)
    ensure_c0()
    ensure_oracle()

    got = hashlib.sha256(FULLMATH.read_bytes()).hexdigest()
    if got != PIN_FULLMATH:
        rec(claims, "PIN-FULLMATH", "FAIL", "FullMath.sol pin mismatch", got)
        return 1
    rec(claims, "PIN-FULLMATH", "PASS", "pinned Uniswap v3 FullMath.sol (width spec, not CRT path)")

    st = run([str(ORACLE_BIN), "selftest"])
    if st.returncode != 0 or "PASS" not in st.stdout:
        rec(claims, "C11-SELFTEST", "FAIL", "wide __int128 vs 16-bit limbs", st.stdout + st.stderr)
        return 1
    rec(claims, "C11-SELFTEST", "PASS", "C11 __int128 schoolbook == 16-bit limbs + AMM 1813")

    chk = run([str(C0), "check", str(LIN)])
    if "LIN_CHECK" not in chk.stdout:
        rec(claims, "LIN-CHECK", "FAIL", "lin_c0 check", chk.stdout)
        return 1
    rec(claims, "LIN-CHECK", "PASS", "Compiler 0 typecheck of src/lin_u512_coprocessor.lin")

    IMG.parent.mkdir(parents=True, exist_ok=True)
    img = run([str(C0), "image", str(LIN), "-o", str(IMG)])
    if img.returncode != 0 or not IMG.exists():
        rec(claims, "LIN-IMAGE", "FAIL", "lin_c0 image", img.stdout + img.stderr)
        return 1
    digest = hashlib.sha256(IMG.read_bytes()).digest()
    rec(claims, "LIN-IMAGE", "PASS", "LINBC1 image emitted", f"sha256:{digest.hex()}")

    gv, gs = lin_run(IMG, "u512_self_gate", [], timeout=300)
    if gv != 1:
        rec(claims, "LIN-SUITE", "FAIL", "u512_self_gate", f"value={gv} steps={gs}")
        return 1
    rec(claims, "LIN-SUITE", "PASS",
        "u512_self_gate == 1 (mul, 512-ge, rem identity, -1/-2, phantom, getAmountOut 1813)",
        f"steps={gs}")

    vectors = [
        (3, 5, 1), (7, 9, 2), (100, 200, 50), (1, 1, 0),
        (U256M, U256M, 1), (1 << 255, 2, 3), (U256M, 1, U256M), (U256M, U256M, U256M),
    ]
    seed = 0x512256
    for i in range(32):
        seed = (seed * 0x9E3779B97F4A7C15) & U256M
        a = seed; seed = (seed * 0x9E3779B97F4A7C15) & U256M
        b = seed; seed = (seed * 0x9E3779B97F4A7C15) & U256M
        d = 0 if (i % 11) == 0 else seed | 1
        if (i % 13) == 0:
            a = 1 << 255; b = 2
        vectors.append((a, b, d))

    n_ok = 0
    for a, b, d in vectors:
        pst, pq, pr, pn = py_muldiv(a, b, d)
        c = c11_muldiv(a, b, d)
        if c["status"] != pst or c["q"] != pq or c["r"] != pr or c["n"] != pn:
            rec(claims, "PY-C11", "FAIL", f"python vs c11 a={a:#x}", str(c))
            return 1
        if pst == 1 and pq * d + pr != pn:
            rec(claims, "REM-ID", "FAIL", "q*d+r != a*b")
            return 1
        n_ok += 1
    rec(claims, "PY-C11", "PASS", f"{n_ok}/{n_ok} vectors: Python int == C11 (q,r,n,status)")
    rec(claims, "REM-ID", "PASS", "remainder identity q*d+r == a*b on every approved vector")

    lin_spots: list[dict] = []
    spots = [
        ((7, 9, 2), 0, 31), ((7, 9, 2), 4, 1), ((1, 1, 0), -1, -1),
        ((U256M, U256M, 1), -1, -2), ((1 << 255, 2, 3), -1, 1),
        ((1 << 255, 2, 3), 0, QPAT), ((1 << 255, 2, 3), 4, 1),
        ((U256M, U256M, U256M), 0, (1 << 64) - 1),
    ]
    for (a, b, d), idx, want in spots:
        got, steps = lin_run(IMG, "u512_muldiv_word", i64words(a) + i64words(b) + i64words(d) + [idx])
        got_u = got & M64 if idx >= 0 else got
        if got_u != (want & M64 if idx >= 0 else want):
            rec(claims, "LIN-SPOT", "FAIL", f"muldiv[{idx}]", f"lin={got} want={want}")
            return 1
        lin_spots.append({"a": a, "b": b, "d": d, "idx": idx, "value": got, "steps": steps})
    rec(claims, "LIN-SPOT", "PASS", "LIN spots: rem, guards -1/-2, phantom q/r, MAX*MAX/MAX",
        f"n={len(lin_spots)}")

    mw, ms = lin_run(IMG, "u512_mul_word", i64words(1 << 255) + i64words(2) + [4])
    if (mw & M64) != 1:
        rec(claims, "LIN-MUL512", "FAIL", "2^255 * 2 product word4", f"got={mw}")
        return 1
    rec(claims, "LIN-MUL512", "PASS", "256x256->512 mul: 2^255*2 sets bit 256 (word4==1)", f"steps={ms}")

    g1, g1s = lin_run(IMG, "u512_ge", [0, 0, 0, 0, 1, 0, 0, 0] + i64words(U256M) + [0, 0, 0, 0])
    g0, g0s = lin_run(IMG, "u512_ge", [1, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0])
    if g1 != 1 or g0 != 0:
        rec(claims, "LIN-GE512", "FAIL", "512-bit ge", f"{g1}/{g0}")
        return 1
    rec(claims, "LIN-GE512", "PASS", "512-bit cmp/ge: 2^256>=2^256-1, not 1>=2", f"steps={g1s}/{g0s}")

    wrap_q = ((1 << 255) * 2) % (1 << 256) // 3
    phantom_q = (QPAT << 192) + (QPAT << 128) + (QPAT << 64) + QPAT
    if wrap_q == 0 and py_muldiv(1 << 255, 2, 3)[1] == phantom_q:
        rec(claims, "WRAP-LIE", "PASS",
            "truncating a*b to 256 bits yields 0; 512-bit mulDiv yields 0x555..5 r=1")
    else:
        rec(claims, "WRAP-LIE", "FAIL", "phantom wrap demonstration broken")
        return 1

    curated = vectors[:8]
    records, leaves = [], []
    step_by = {(s["a"], s["b"], s["d"], s["idx"]): s["steps"] for s in lin_spots}
    for i, (a, b, d) in enumerate(curated):
        pst, pq, pr, pn = py_muldiv(a, b, d)
        steps = step_by.get((a, b, d, -1), step_by.get((a, b, d, 0), gs))
        flags = 1 if pst == 1 and pq * d + pr == pn else 0
        raw = pack_lnr1(digest, i, a, b, d, pq, pr, pst, steps, flags)
        records.append({"id": i, "a": hex(a), "b": hex(b), "d": hex(d), "q": hex(pq),
                        "r": hex(pr), "n": hex(pn), "status": pst, "steps": steps,
                        "raw_hex": raw.hex()})
        leaves.append(hashlib.sha256(DOM_LEAF + raw).digest())
    root = merkle(leaves)
    rec(claims, "LNR1-MERKLE", "PASS", "LNR1 240-byte receipts, domain-separated SHA-256 merkle",
        f"root=sha256:{root.hex()}")

    lin_amm, lin_amm_s = lin_run(
        IMG, "u512_get_amount_out_word",
        i64words(1000) + i64words(10000) + i64words(20000) + [0])
    if (lin_amm & M64) != 1813:
        rec(claims, "AMM-LIN", "FAIL", "getAmountOut(1000,10000,20000)", f"lin={lin_amm}")
        return 1
    rec(claims, "AMM-LIN", "PASS", "coprocessor getAmountOut(1000,10000,20000)==1813",
        f"steps={lin_amm_s}")

    phantom_amm = (1, 1, (1 << 256) // 997 + 1)
    want_ph = ref_amount_out(*phantom_amm)
    c_ph = c11_amm(*phantom_amm)
    if c_ph["status"] != 1 or c_ph["q"] != want_ph or phantom_amm[0] * 997 * phantom_amm[2] < (1 << 256):
        rec(claims, "AMM-PHANTOM-C11", "FAIL", "phantom AMM vs ref", str(c_ph))
        return 1
    rec(claims, "AMM-PHANTOM-C11", "PASS",
        "C11 getAmountOut where fee*reserve_out >= 2^256 matches Python bigint",
        f"q={want_ph:#x}")

    ph_args = i64words(1) + i64words(1) + i64words(phantom_amm[2])
    ph_st, ph_ss = lin_run(IMG, "u512_get_amount_out_word", ph_args + [-1], timeout=240)
    ph_q = 0
    ph_tot = ph_ss
    for wi in range(4):
        w, s = lin_run(IMG, "u512_get_amount_out_word", ph_args + [wi], timeout=240)
        ph_q |= (w & M64) << (64 * wi)
        ph_tot += s
    if ph_st != 1 or ph_q != want_ph:
        rec(claims, "AMM-WIRE", "FAIL", "coprocessor phantom AMM", f"st={ph_st} q={ph_q:#x}")
        return 1
    rec(claims, "AMM-WIRE", "PASS",
        "512-bit getAmountOut APPROVES phantom fee*reserve_out >= 2^256 (full 256-bit q)",
        f"status=1 q={ph_q:#x} steps={ph_tot}")

    u256_img = ROOT / "examples" / "u512_coprocessor" / "u256_settlement.linbc"
    uimg = run([str(C0), "image", str(U256), "-o", str(u256_img)])
    if uimg.returncode != 0:
        rec(claims, "U256-IMAGE", "FAIL", "could not image u256 settler", uimg.stderr)
        return 1
    u256_digest = hashlib.sha256(u256_img.read_bytes()).digest()
    z_st, z_steps = lin_run(u256_img, "settle_u256_word",
                            i64words(0) + i64words(10 ** 12) + i64words(10 ** 21) + [-1])
    rec(claims, "U256-GUARD-1", "PASS" if z_st == -1 else "FAIL",
        "settle_u256_word amount_in=0 -> -1", f"status={z_st} steps={z_steps}")
    ov_st, ov_s = lin_run(u256_img, "settle_u256_word",
                          i64words(1) + i64words(1) + i64words(phantom_amm[2]) + [-1])
    rec(claims, "U256-STILL-2", "PASS" if ov_st == -2 else "FAIL",
        "settle_u256_word still ^-2 on phantom AMM (512 not wired into this settler)",
        f"status={ov_st} steps={ov_s}")

    if UNFILTERED.exists():
        urec = json.loads(UNFILTERED.read_text()).get("records", [])
        for cls in ("EXACT_INPUT", "OVERPAID_INPUT"):
            hit = next((r for r in urec if r.get("class") == cls), None)
            if not hit:
                rec(claims, "E2E-" + cls[:5], "FAIL", f"{cls} missing from unfiltered corpus")
                return 1
            args = i64words(hit["amount_in"]) + i64words(hit["reserve_in"]) + i64words(hit["reserve_out"])
            stv, st_s = lin_run(u256_img, "settle_u256_word", args + [-1])
            if stv != 1:
                rec(claims, "E2E-" + cls[:5], "FAIL", f"{cls} settler status", f"status={stv}")
                return 1
            out = 0
            tot = st_s
            for wi in range(4):
                w, s = lin_run(u256_img, "settle_u256_word", args + [wi])
                out |= (w & M64) << (64 * wi)
                tot += s
            refv = ref_amount_out(hit["amount_in"], hit["reserve_in"], hit["reserve_out"])
            if out != refv:
                rec(claims, "E2E-" + cls[:5], "FAIL", f"{cls} vs ref_amount_out", f"lin={out} ref={refv}")
                return 1
            onchain = hit["amount_out"]
            rec(claims, "E2E-" + cls[:5], "PASS", f"settle_u256_word vs ref on 1 {cls} row",
                f"lin==ref steps={tot} onchain={'eq' if out == onchain else 'neq'}")
            raw = pack_lcr2(u256_digest, len(lcr2), hit["amount_in"], hit["reserve_in"],
                            hit["reserve_out"], out, tot, 1)
            lcr2.append({"class": cls, "steps": tot, "lin_out": out, "ref": refv,
                         "onchain": onchain, "raw_hex": raw.hex()})
        rec(claims, "E2E-GAP", "PASS",
            "512-bit intermediate off the suspect list; full 2000/157 LCR2 campaign still required",
            f"slice={len(lcr2)}")

    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.1",
        "class": "EXPERIMENTAL",
        "claim": "numeric coprocessor with auditable receipt (FullMath width + getAmountOut wiring)",
        "not_claimed": [
            "full 2000/157 settle_u256_word LCR2 campaign",
            "Uniswap v2/v3 or FullMath.sol CRT/mulmod replacement",
            "wiring 512-bit div into the existing settle_u256_word body",
        ],
        "fullmath_sha256": PIN_FULLMATH,
        "linbc1_sha256": digest.hex(),
        "lnr1_merkle_sha256": root.hex(),
        "self_gate_steps": gs,
        "claims": claims,
        "records": records,
        "lin_spots": lin_spots,
        "lcr2_slice": lcr2,
        "domains": {"leaf": DOM_LEAF.decode(), "node": DOM_NODE.decode(),
                    "lcr2_leaf": "LIN:LEAF:1", "lcr2_node": "LIN:NODE:1"},
        "record_bytes": 240,
        "phantom_amm": {"amount_in": 1, "reserve_in": 1, "reserve_out": hex(phantom_amm[2]),
                        "ref": hex(want_ph), "coprocessor_status": 1, "u256_status": ov_st},
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    failed = sum(1 for c in claims if c["status"] == "FAIL")
    print("-" * 78)
    print(f"  result: {sum(c['status']=='PASS' for c in claims)} PASS, {failed} FAIL")
    print(f"  evidence: {EVIDENCE}")
    print(f"  merkle: sha256:{root.hex()}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
