#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: 512-bit numeric coprocessor (FullMath *width*) vs LIN C0.

PASS claims are recomputed this run against:
  * Python arbitrary-precision int (remainder identity q*d+r == a*b)
  * C11 64-bit schoolbook + restoring div (test/oracles/u512_coprocessor_c11.c)
  * Compiler 0 image of src/lin_u512_coprocessor.lin
  * pinned Uniswap v3 FullMath.sol bytes (width only; not CRT/mulmod)

NOT claimed: Uniswap replacement, CRT/mulmod parity, full 2000/157 campaign,
computational soundness of Merkle (tamper-evidence only).

Class: EXPERIMENTAL.
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
U256_LIN = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
HOST_SRC = ROOT / "test" / "oracles" / "u512_lin_host.c"
HOST_BIN = ROOT / "test" / "oracles" / "u512_lin_host"
IMG = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor.linbc"
U256_IMG = ROOT / "examples" / "u512_coprocessor" / "u256_settlement_engine.linbc"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
LNR1_BIN = ROOT / "examples" / "u512_coprocessor" / "u512_lnr1.bin"
LCR2_BIN = ROOT / "examples" / "u512_coprocessor" / "u256_lcr2_e2e.bin"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
UNFILTERED = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
PIN_FULLMATH = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"

U256 = (1 << 256) - 1
U512 = (1 << 512) - 1
MASK64 = (1 << 64) - 1
DOM_LNR1_LEAF = b"LIN:U512:LEAF:1"
DOM_LNR1_NODE = b"LIN:U512:NODE:1"
DOM_LCR2_LEAF = b"LIN:LEAF:1"
DOM_LCR2_NODE = b"LIN:NODE:1"
OP_MUL, OP_GE, OP_DIV, OP_MULDIV, OP_AMM = 1, 2, 3, 4, 5


def run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def i64(w: int) -> int:
    w &= MASK64
    return w - (1 << 64) if w >= (1 << 63) else w


def w4(n: int) -> list[int]:
    return [(n >> (64 * i)) & MASK64 for i in range(4)]


def w8(n: int) -> list[int]:
    return [(n >> (64 * i)) & MASK64 for i in range(8)]


def from_ws(ws: list[int]) -> int:
    v = 0
    for i, w in enumerate(ws):
        v |= (w & MASK64) << (64 * i)
    return v


def py_mul(a: int, b: int) -> int:
    return (a & U256) * (b & U256)


def py_ge(a: int, b: int) -> int:
    return 1 if (a & U512) >= (b & U512) else 0


def py_div(n: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(n, d)
    if q > U256:
        return -2, 0, 0
    return 1, q, r


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    return py_div(py_mul(a, b), d)


def py_amm(ain: int, rin: int, rout: int) -> tuple[int, int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0, 0
    fee = ain * 997
    den = rin * 1000 + fee
    if fee > U256 or den > U256:
        return -2, 0, 0
    return py_muldiv(fee, rout, den)


def ref_amount_out(ain: int, rin: int, rout: int) -> int:
    fee = ain * 997
    return (fee * rout) // (rin * 1000 + fee)


def u256_safemath(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > U256 or num > U256 or den > U256:
        return -2, 0
    return 1, num // den


def be32(x: int) -> bytes:
    return (x & U256).to_bytes(32, "big")


def lnr1_record(img: bytes, run_id: int, vec_id: int, op: int,
                a: int, b: int, d: int, q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vec_id)
    struct.pack_into("<Q", raw, 56, op)
    raw[64:96] = be32(a)
    raw[96:128] = be32(b)
    raw[128:160] = be32(d)
    raw[160:192] = be32(q)
    raw[192:224] = be32(r)
    struct.pack_into("<Q", raw, 224, steps)
    struct.pack_into("<q", raw, 232, status)
    return bytes(raw)


def lcr2_record(img: bytes, run_id: int, tx_id: int, ain: int, rin: int, rout: int,
                aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx_id)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def merkle(leaves: list[bytes], leaf_dom: bytes, node_dom: bytes) -> bytes:
    cur = [hashlib.sha256(leaf_dom + x).digest() for x in leaves]
    if not cur:
        return hashlib.sha256(node_dom).digest()
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(hashlib.sha256(node_dom + l + r).digest())
        cur = nxt
    return cur[0]


def ensure_tools() -> None:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0 or not C0.exists():
            raise RuntimeError(f"make c0 failed: {p.stderr}")
    cc = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if cc.returncode != 0:
        raise RuntimeError(cc.stderr)
    srcs = [
        "lin_common.c", "lin_token.c", "lin_ast.c", "lin_parse.c", "lin_vm.c",
        "lin_sha256.c", "lin_region.c", "lin_abi.c", "lin_str.c", "lin_linbc1.c",
    ]
    host = ["gcc", "-O2", "-std=c11", "-Wall", f"-I{ROOT}/transpile/c/lin_c",
            "-o", str(HOST_BIN), str(HOST_SRC)]
    host += [str(ROOT / "transpile" / "c" / "lin_c" / s) for s in srcs]
    h = run(host, timeout=60)
    if h.returncode != 0:
        raise RuntimeError(h.stderr)


def c11(args: list[str]) -> str:
    p = run([str(ORACLE_BIN), *args], timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"oracle {args}: {p.stdout}\n{p.stderr}")
    return p.stdout


def parse_qr(stdout: str) -> tuple[int, int, int]:
    st = int(re.search(r"status=(-?\d+)", stdout).group(1))
    q = [int(x) for x in re.search(r"q=([0-9 ]+)", stdout).group(1).split()]
    r = [int(x) for x in re.search(r"r=([0-9 ]+)", stdout).group(1).split()]
    return st, from_ws(q), from_ws(r)


def lin_image(src: Path, dst: Path) -> bytes:
    dst.parent.mkdir(parents=True, exist_ok=True)
    p = run([str(C0), "image", str(src), "-o", str(dst)], timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"image {src}: {p.stdout}\n{p.stderr}")
    digest = hashlib.sha256(dst.read_bytes()).digest()
    m = re.search(r"sha256=([0-9a-f]{64})", p.stdout)
    if m and bytes.fromhex(m.group(1)) != digest:
        # image file includes trailing self-hash; prefer loader digest from host
        pass
    return digest


def lin_scan(img: Path, fn: str, args: list[int], lo: int, hi: int, timeout: int = 180) -> dict:
    cmd = [str(HOST_BIN), str(img), fn, *[str(i64(x)) for x in args], "--scan", str(lo), str(hi)]
    p = run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"host {fn}: {p.stdout}\n{p.stderr}")
    out = {"img": None, "idx": {}, "steps_total": 0}
    m = re.search(r"img_sha256=([0-9a-f]{64})", p.stdout)
    if m:
        out["img"] = bytes.fromhex(m.group(1))
    for mm in re.finditer(r"idx=(-?\d+) value=(-?\d+) steps=(\d+)", p.stdout):
        out["idx"][int(mm.group(1))] = (int(mm.group(2)), int(mm.group(3)))
    tm = re.search(r"steps_total=(\d+)", p.stdout)
    if tm:
        out["steps_total"] = int(tm.group(1))
    return out


def lin_once(img: Path, fn: str, args: list[int], timeout: int = 180) -> tuple[int, int, bytes]:
    cmd = [str(HOST_BIN), str(img), fn, *[str(i64(x)) for x in args]]
    p = run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"host {fn}: {p.stdout}\n{p.stderr}")
    digest = bytes.fromhex(re.search(r"img_sha256=([0-9a-f]{64})", p.stdout).group(1))
    val = int(re.search(r"value=(-?\d+)", p.stdout).group(1))
    steps = int(re.search(r"steps=(\d+)", p.stdout).group(1))
    return val, steps, digest


def assemble(idxmap: dict[int, tuple[int, int]], lo: int, hi: int) -> tuple[int, int]:
    ws = []
    steps = 0
    for i in range(lo, hi + 1):
        v, s = idxmap[i]
        ws.append(v & MASK64)
        steps += s
    return from_ws(ws), steps


def claim(claims: list[dict], cid: str, ok: bool, desc: str, note: str = "") -> None:
    claims.append({"id": cid, "status": "PASS" if ok else "FAIL", "description": desc, "note": note})


def main() -> int:
    claims: list[dict] = []
    vectors: list[dict] = []
    lnr1: list[bytes] = []
    lcr2: list[bytes] = []
    ensure_tools()
    st = run([str(ORACLE_BIN), "selftest"])
    claim(claims, "C11-SELFTEST", st.returncode == 0, "C11 oracle selftest", st.stdout.strip())
    fm = sha256_file(FULLMATH)
    claim(claims, "FULLMATH-PIN", fm == PIN_FULLMATH, "pinned FullMath.sol sha256 (width provenance)", fm)
    chk = run([str(C0), "check", str(LIN)], timeout=60)
    claim(claims, "LIN-CHECK", chk.returncode == 0 and "@RULEL:LIN_CHECK:1.0.0" in chk.stdout,
          "Compiler 0 check of src/lin_u512_coprocessor.lin")
    lin_image(LIN, IMG)
    lin_image(U256_LIN, U256_IMG)

    gval, gsteps, img_d = lin_once(IMG, "u512_self_gate", [], timeout=180)
    claim(claims, "SELF-GATE", gval == 1, "u512_self_gate == 1", f"value={gval} steps={gsteps}")

    phantom_rout = ((1 << 256) + 996) // 997
    mul_vecs = [
        (0, 123), (2, 3), (1 << 64, 1 << 64), (1 << 128, 1 << 128),
        (1 << 255, 2), (U256, U256), (997, phantom_rout),
    ]
    ge_vecs = [
        (0, 0), (1, 0), (0, 1), (1 << 256, (1 << 256) - 1),
        (1 << 511, (1 << 511) - 1), (U512, U512),
    ]
    div_vecs = [
        (6, 3), (7, 3), (1 << 256, 3), (0, 0), (U512, U256),
    ]
    md_vecs = [
        (7, 9, 2), (1 << 255, 2, 3), (U256, U256, U256), (U256, U256, 1),
        (1 << 128, 1 << 128, 2), (0, U256, 5),
    ]
    rng_n = 4
    import random
    rng = random.Random(20260916)
    for _ in range(rng_n):
        md_vecs.append((rng.randrange(0, 1 << 256), rng.randrange(0, 1 << 256), rng.randrange(1, 1 << 256)))
    amm_vecs = [
        (2, 100, 100), (10000, 50000, 100000), (10**18, 5 * 10**18, 10 * 10**18),
        (1, 1, phantom_rout), (0, 100, 100),
    ]

    vec_id = 0
    mul_ok = ge_ok = div_ok = md_ok = amm_ok = 0

    for a, b in mul_vecs:
        exp = py_mul(a, b)
        c_out = c11(["mul", *[str(x) for x in w4(a) + w4(b)]])
        c_p = from_ws([int(x) for x in re.search(r"p=([0-9 ]+)", c_out).group(1).split()])
        scan = lin_scan(IMG, "u512_mul_word", w4(a) + w4(b), 0, 7)
        lin_p, stps = assemble(scan["idx"], 0, 7)
        ok = exp == c_p == lin_p
        mul_ok += int(ok)
        vec_id += 1
        lnr1.append(lnr1_record(img_d, 1, vec_id, OP_MUL, a, b, 0, lin_p & U256, lin_p >> 256, stps, 1 if ok else 0))
        vectors.append({"op": "mul", "a": str(a), "b": str(b), "prod": str(lin_p), "ok": ok, "steps": stps})

    for a, b in ge_vecs:
        exp = py_ge(a, b)
        c_out = c11(["ge", *[str(x) for x in w8(a) + w8(b)]])
        c_g = int(re.search(r"ge=(-?\d+)", c_out).group(1))
        val, stps, _ = lin_once(IMG, "u512_ge", w8(a) + w8(b))
        ok = exp == c_g == val
        ge_ok += int(ok)
        vec_id += 1
        lnr1.append(lnr1_record(img_d, 1, vec_id, OP_GE, a & U256, a >> 256, b & U256, b >> 256, 0, stps, val))
        vectors.append({"op": "ge", "a": str(a), "b": str(b), "ge": val, "ok": ok, "steps": stps})

    for n, d in div_vecs:
        est, eq, er = py_div(n, d)
        cst, cq, cr = parse_qr(c11(["div", *[str(x) for x in w8(n) + w4(d)]]))
        scan = lin_scan(IMG, "u512_div_word", w8(n) + w4(d), -1, 7)
        lst = scan["idx"][-1][0]
        if lst == 1:
            lq, _ = assemble(scan["idx"], 0, 3)
            lr, _ = assemble(scan["idx"], 4, 7)
        else:
            lq = lr = 0
        ident = True if lst != 1 else (lq * d + lr == n and lr < d)
        ok = est == cst == lst and (lst != 1 or (eq == cq == lq and er == cr == lr and ident))
        div_ok += int(ok)
        vec_id += 1
        lnr1.append(lnr1_record(img_d, 1, vec_id, OP_DIV, n & U256, n >> 256, d, lq, lr, scan["steps_total"], lst))
        vectors.append({"op": "div", "n": str(n), "d": str(d), "status": lst, "q": str(lq), "r": str(lr),
                        "ok": ok, "ident": ident, "steps": scan["steps_total"]})

    for a, b, d in md_vecs:
        est, eq, er = py_muldiv(a, b, d)
        cst, cq, cr = parse_qr(c11(["muldiv", *[str(x) for x in w4(a) + w4(b) + w4(d)]]))
        scan = lin_scan(IMG, "u512_muldiv_word", w4(a) + w4(b) + w4(d), -1, 7, timeout=180)
        lst = scan["idx"][-1][0]
        if lst == 1:
            lq, _ = assemble(scan["idx"], 0, 3)
            lr, _ = assemble(scan["idx"], 4, 7)
        else:
            lq = lr = 0
        ident = True if lst != 1 else (lq * d + lr == a * b and lr < d)
        ok = est == cst == lst and (lst != 1 or (eq == cq == lq and er == cr == lr and ident))
        md_ok += int(ok)
        vec_id += 1
        lnr1.append(lnr1_record(img_d, 1, vec_id, OP_MULDIV, a, b, d, lq, lr, scan["steps_total"], lst))
        vectors.append({"op": "muldiv", "a": str(a), "b": str(b), "d": str(d), "status": lst,
                        "q": str(lq), "r": str(lr), "ok": ok, "ident": ident, "steps": scan["steps_total"]})

    phantom_q = None
    for ain, rin, rout in amm_vecs:
        est, eq, er = py_amm(ain, rin, rout)
        cst, cq, cr = parse_qr(c11(["amm", *[str(x) for x in w4(ain) + w4(rin) + w4(rout)]]))
        scan = lin_scan(IMG, "u512_get_amount_out_word", w4(ain) + w4(rin) + w4(rout), -1, 3, timeout=180)
        lst = scan["idx"][-1][0]
        lq = assemble(scan["idx"], 0, 3)[0] if lst == 1 else 0
        ok = est == cst == lst and (lst != 1 or eq == cq == lq)
        amm_ok += int(ok)
        if ain == 1 and rin == 1:
            phantom_q = (lst, lq, scan["steps_total"])
        vec_id += 1
        lnr1.append(lnr1_record(img_d, 1, vec_id, OP_AMM, ain, rin, rout, lq, 0, scan["steps_total"], lst))
        vectors.append({"op": "amm", "ain": str(ain), "rin": str(rin), "rout": str(rout),
                        "status": lst, "q": str(lq), "ok": ok, "steps": scan["steps_total"]})

    claim(claims, "MUL-512", mul_ok == len(mul_vecs), f"mul 256x256->512 LIN==C11==Python {mul_ok}/{len(mul_vecs)}")
    claim(claims, "GE-512", ge_ok == len(ge_vecs), f"512-bit ge LIN==C11==Python {ge_ok}/{len(ge_vecs)}")
    claim(claims, "DIV-512", div_ok == len(div_vecs), f"div 512/256 remainder identity {div_ok}/{len(div_vecs)}")
    claim(claims, "MULDIV", md_ok == len(md_vecs), f"mulDiv FullMath-width {md_ok}/{len(md_vecs)}")
    claim(claims, "AMM-WIDTH", amm_ok == len(amm_vecs), f"getAmountOut via 512 mulDiv {amm_ok}/{len(amm_vecs)}")
    ph_ok = phantom_q is not None and phantom_q[0] == 1 and phantom_q[1] == py_amm(1, 1, phantom_rout)[1]
    claim(claims, "PHANTOM", ph_ok, "ain=1,rin=1,rout=ceil(2^256/997) APPROVES on coprocessor",
          f"status={phantom_q[0] if phantom_q else None} q={phantom_q[1] if phantom_q else None} steps={phantom_q[2] if phantom_q else None}")

    data = json.loads(UNFILTERED.read_text())
    exact = next(r for r in data["records"] if r["class"] == "EXACT_INPUT")
    over = next(r for r in data["records"] if r["class"] == "OVERPAID_INPUT")
    u256_img_d = None
    e2e_ok = True
    e2e_notes = []
    for rec, txid in ((exact, 1), (over, 2)):
        ain, rin, rout = int(rec["amount_in"]), int(rec["reserve_in"]), int(rec["reserve_out"])
        onchain = int(rec["amount_out"])
        ref = ref_amount_out(ain, rin, rout)
        sm_st, sm_q = u256_safemath(ain, rin, rout)
        scan = lin_scan(U256_IMG, "settle_u256_word", w4(ain) + w4(rin) + w4(rout), -1, 3, timeout=120)
        u256_img_d = scan["img"]
        stt = scan["idx"][-1][0]
        out = assemble(scan["idx"], 0, 3)[0] if stt == 1 else 0
        steps = scan["steps_total"]
        match_ref = stt == 1 and out == ref == sm_q
        if rec["class"] == "EXACT_INPUT":
            match_chain = out == onchain
        else:
            match_chain = out != onchain and out == ref
        ok = match_ref and match_chain and steps > 0
        e2e_ok = e2e_ok and ok
        e2e_notes.append(f"{rec['class']} lin={out} ref={ref} onchain={onchain} steps={steps} ok={ok}")
        lcr2.append(lcr2_record(u256_img_d, 1, txid, ain, rin, rout, out if stt == 1 else 0, steps, stt))
        cop = lin_scan(IMG, "u512_get_amount_out_word", w4(ain) + w4(rin) + w4(rout), -1, 3, timeout=180)
        cst = cop["idx"][-1][0]
        cout = assemble(cop["idx"], 0, 3)[0] if cst == 1 else 0
        e2e_ok = e2e_ok and cst == 1 and cout == ref
        e2e_notes.append(f"  coprocessor={cout} steps={cop['steps_total']}")

    g1 = lin_scan(U256_IMG, "settle_u256_word", w4(0) + w4(100) + w4(100), -1, -1)
    g2 = lin_scan(U256_IMG, "settle_u256_word", w4(1 << 200) + w4(1) + w4(1 << 100), -1, -1)
    ph_s = lin_scan(U256_IMG, "settle_u256_word", w4(1) + w4(1) + w4(phantom_rout), -1, -1)
    claim(claims, "E2E-U256-LCR2", e2e_ok, "settle_u256 vs ref_amount_out EXACT/OVERPAID with real LCR2 steps",
          " | ".join(e2e_notes))
    claim(claims, "GUARDS", g1["idx"][-1][0] == -1 and g2["idx"][-1][0] == -2,
          "settle_u256_word guards -1 zero input / -2 256-bit numerator overflow",
          f"zero={g1['idx'][-1][0]} ovf={g2['idx'][-1][0]} phantom_u256={ph_s['idx'][-1][0]}")
    claim(claims, "PHANTOM-U256-STILL-2", ph_s["idx"][-1][0] == -2,
          "settle_u256_word still ^-2 on phantom (SafeMath width); 512 intermediate off the suspect list")

    cli = run([str(C0), "run", str(IMG), "u512_muldiv_word",
               "7", "0", "0", "0", "9", "0", "0", "0", "2", "0", "0", "0", "0"], timeout=180)
    cli_ok = cli.returncode == 0 and "value=31" in cli.stdout
    claim(claims, "CLI-SPOT", cli_ok, "lin_c0 run muldiv 7*9/2 word0 == 31 (stock CLI, no custom host)",
          cli.stdout.strip().replace("\n", " "))

    LNR1_BIN.write_bytes(b"".join(lnr1))
    LCR2_BIN.write_bytes(b"".join(lcr2))
    lnr1_root = merkle(lnr1, DOM_LNR1_LEAF, DOM_LNR1_NODE)
    lcr2_root = merkle(lcr2, DOM_LCR2_LEAF, DOM_LCR2_NODE)
    all_pass = all(c["status"] == "PASS" for c in claims)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "class_definition": "TOY=teaching slice | EXPERIMENTAL=real published width on this host | REAL_WORLD=as deployed",
        "sells_as": "numeric coprocessor with auditable receipt, not a Uniswap replacement",
        "img_sha256": img_d.hex(),
        "u256_img_sha256": (u256_img_d or b"").hex(),
        "lnr1_merkle": lnr1_root.hex(),
        "lcr2_merkle": lcr2_root.hex(),
        "lnr1_count": len(lnr1),
        "lcr2_count": len(lcr2),
        "domains": {"lnr1_leaf": DOM_LNR1_LEAF.decode(), "lnr1_node": DOM_LNR1_NODE.decode(),
                    "lcr2_leaf": DOM_LCR2_LEAF.decode(), "lcr2_node": DOM_LCR2_NODE.decode()},
        "fullmath_sha256": fm,
        "self_gate_steps": gsteps,
        "claims": claims,
        "vectors": vectors,
        "not_claimed": [
            "CRT/mulmod assembly parity with FullMath.sol",
            "LIN replaces Uniswap, Compound, or the EVM",
            "full 2000-swap + 157-unfiltered campaign with coprocessor steps",
            "zk / computational soundness of Merkle (tamper-evidence + independent recompute)",
            "settle_u256_word FullMath width (it remains SafeMath; phantom still ^-2)",
        ],
        "verdict": "PASS" if all_pass else "FAIL",
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"verdict": evidence["verdict"], "claims": [(c["id"], c["status"]) for c in claims],
                      "img": img_d.hex(), "lnr1": lnr1_root.hex(), "lcr2": lcr2_root.hex()}, indent=2))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
