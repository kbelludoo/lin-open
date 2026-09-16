#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External proof: LIN u512 numeric coprocessor vs Python bigint + C11 oracles.

Proves (this run): 256x256->512 mul, 512-bit ge, 512/256 restoring div with
q*d+r == n, fail-closed -1/-2, LNR1 receipt an auditor recomputes without LIN.

Does not prove: FullMath.sol CRT/mulmod assembly, replacing Uniswap/EVM,
full 2000/157 mainnet campaign, zk soundness of Merkle (tamper-evidence only).
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
U256_LIN = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
BC1 = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
HOST_SRC = ROOT / "test" / "oracles" / "u512_lin_host.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
HOST_BIN = ROOT / "test" / "oracles" / "u512_lin_host"
EVIDENCE = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
UNFILTERED = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
PIN_FULLMATH = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"

DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
LCR2_LEAF = b"LIN:LEAF:1"
LCR2_NODE = b"LIN:NODE:1"
OP_MUL, OP_GE, OP_DIV, OP_MULDIV = 1, 2, 3, 4
U256 = (1 << 256) - 1


def run(cmd, timeout=120, inp=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=inp, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def words4(x: int) -> list[int]:
    out = []
    for i in range(4):
        w = (x >> (64 * i)) & ((1 << 64) - 1)
        out.append(w - (1 << 64) if w >= (1 << 63) else w)
    return out


def words8(x: int) -> list[int]:
    return words4(x & U256) + words4(x >> 256)


def py_muldiv(a, b, d):
    if d == 0:
        return -1, 0, 0
    n = a * b
    q, r = divmod(n, d)
    if q >= (1 << 256):
        return -2, 0, 0
    return 1, q, r


def pack_lnr1(img: bytes, vid: int, op: int, a: int, b: int, d: int, q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, vid)
    struct.pack_into("<Q", raw, 48, op)
    raw[56:88] = (a & U256).to_bytes(32, "little")
    raw[88:120] = (b & U256).to_bytes(32, "little")
    raw[120:152] = (d & U256).to_bytes(32, "little")
    raw[152:184] = (q & U256).to_bytes(32, "little")
    raw[184:216] = (r & U256).to_bytes(32, "little")
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle(leaves: list[bytes], leaf_d: bytes, node_d: bytes) -> str:
    nodes = list(leaves)
    if not nodes:
        return "00" * 32
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(node_d + nodes[i] + nodes[i + 1]).digest() for i in range(0, len(nodes), 2)]
    return nodes[0].hex()


def ensure_bins():
    if not C0.exists():
        r = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if r.returncode:
            raise SystemExit(r.stderr)
    if not BC1.exists():
        r = run(["make", "-C", str(ROOT / "transpile" / "c"), "bin/lin_bc1_run"], timeout=120)
        if r.returncode:
            raise SystemExit(r.stderr)
    cc = ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror"]
    r = run(cc + ["-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if r.returncode:
        raise SystemExit("oracle gcc: " + r.stderr)
    linc = ROOT / "transpile/c/lin_c"
    srcs = [str(HOST_SRC)] + [str(linc / n) for n in
        "lin_common.c lin_token.c lin_ast.c lin_parse.c lin_vm.c lin_sha256.c lin_region.c lin_abi.c lin_str.c lin_linbc1.c".split()]
    r = run(cc + ["-I", str(linc), "-o", str(HOST_BIN)] + srcs)
    if r.returncode:
        raise SystemExit("host gcc: " + r.stderr)


def host(img: Path, args: list[str], timeout=180) -> str:
    p = run([str(HOST_BIN), str(img), *args], timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout


def parse_qr(out: str):
    steps = int(re.search(r"steps=(\d+)", out).group(1))
    st_m = re.search(r"status=(-?\d+)", out)
    ge_m = re.search(r"\bge=(-?\d+)", out)
    q_m = re.search(r"\bq=([0-9a-f]+)", out)
    r_m = re.search(r"\br=([0-9a-f]+)", out)
    p_m = re.search(r"\bp=([0-9a-f]+)", out)
    st = int(st_m.group(1)) if st_m else 1
    return (
        st,
        steps,
        int(q_m.group(1), 16) if q_m else 0,
        int(r_m.group(1), 16) if r_m else 0,
        int(p_m.group(1), 16) if p_m else 0,
        int(ge_m.group(1)) if ge_m else None,
    )


def rec(claims, ident, status, desc, note=""):
    claims.append({"id": ident, "status": status, "description": desc, "note": note})
    print(f"  [{status:4s}] {ident:16s} {desc}" + (f"\n            {note}" if note else ""))


def pack_lcr2(img: bytes, tx: int, ain, rin, rout, aout, steps, status) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, tx)
    raw[56:88] = ain.to_bytes(32, "big")
    raw[88:120] = rin.to_bytes(32, "big")
    raw[120:152] = rout.to_bytes(32, "big")
    raw[152:184] = aout.to_bytes(32, "big")
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def u256_settle(img: Path, ain, rin, rout):
    args = [*map(str, words4(ain) + words4(rin) + words4(rout))]
    st_out = run([str(BC1), str(img), "settle_u256_word", *args, "-1"], timeout=60)
    m = re.search(r"result=(-?\d+).*steps=(\d+)", st_out.stdout.replace("\n", " "))
    if not m:
        raise RuntimeError(st_out.stdout)
    st, steps = int(m.group(1)), int(m.group(2))
    if st != 1:
        return st, None, steps
    out = 0
    for i in range(4):
        w = run([str(BC1), str(img), "settle_u256_word", *args, str(i)], timeout=60)
        mw = re.search(r"result=(-?\d+)", w.stdout)
        out |= (int(mw.group(1)) & ((1 << 64) - 1)) << (64 * i)
    return 1, out, steps


def main() -> int:
    claims = []
    print("=" * 78)
    print("  U512 NUMERIC COPROCESSOR — external LIN proof (EXPERIMENTAL width)")
    print("=" * 78)
    if not FULLMATH.exists() or sha256_file(FULLMATH) != PIN_FULLMATH:
        rec(claims, "PIN-FULLMATH", "FAIL", "FullMath.sol pin mismatch")
        return 1
    rec(claims, "PIN-FULLMATH", "PASS", "pinned FullMath.sol sha256 (WIDTH spec, not CRT)")

    ensure_bins()
    st = run([str(ORACLE_BIN), "selftest"])
    rec(claims, "C11-SELFTEST", "PASS" if st.returncode == 0 and "PASS" in st.stdout else "FAIL",
        "16-bit limbs == 64-bit __int128", st.stdout.strip())
    if claims[-1]["status"] != "PASS":
        return 1

    rnd = run([str(ORACLE_BIN), "random", "10000", "0xc0ffee"])
    rec(claims, "C11-RANDOM-10K", "PASS" if rnd.returncode == 0 and "PASS" in rnd.stdout else "FAIL",
        "10k full-range 16-bit==64-bit", rnd.stdout.strip())
    if claims[-1]["status"] != "PASS":
        return 1

    # Python bigint vs C11 batch (full-range)
    import random
    rng = random.Random(20260916)
    vecs = [(7, 9, 2), (0, 5, 3), (U256, U256, U256), (U256, U256, 1), (1 << 255, 2, 3),
            (1, 1, 0), (997, ((1 << 256) + 996) // 997, 1997)]
    for _ in range(2500):
        vecs.append((rng.randrange(1 << 256), rng.randrange(1 << 256), rng.randrange(1, 1 << 256)))
    blob = "\n".join(f"{a:064x} {b:064x} {d:064x}" for a, b, d in vecs)
    bat = run([str(ORACLE_BIN), "batch"], inp=blob, timeout=60)
    if bat.returncode:
        rec(claims, "PY-C11-BATCH", "FAIL", "c11 batch", bat.stderr)
        return 1
    lines = [ln for ln in bat.stdout.splitlines() if ln.strip()]
    diverg = 0
    for (a, b, d), ln in zip(vecs, lines):
        parts = ln.split()
        st_, qh, rh = int(parts[0]), int(parts[1], 16), int(parts[2], 16)
        exp = py_muldiv(a, b, d)
        if (st_, qh if exp[0] == 1 else 0, rh if exp[0] == 1 else 0) != (exp[0], exp[1], exp[2]) and not (
            exp[0] != 1 and st_ == exp[0]
        ):
            diverg += 1
        elif exp[0] == 1 and (qh != exp[1] or rh != exp[2]):
            diverg += 1
        elif exp[0] != 1 and st_ != exp[0]:
            diverg += 1
    rec(claims, "PY-BIGINT-C11", "PASS" if diverg == 0 else "FAIL",
        f"Python int vs C11 muldiv n={len(vecs)} divergences={diverg}")
    if diverg:
        return 1

    img_path = Path("/tmp/u512_coprocessor.linbc")
    im = run([str(C0), "image", str(LIN), "-o", str(img_path)])
    if im.returncode:
        rec(claims, "LIN-IMAGE", "FAIL", "lin_c0 image", im.stderr)
        return 1
    ver = run([str(BC1), str(img_path), "--verify"])
    mdig = re.search(r'img_sha256="([0-9a-f]+)"', ver.stdout)
    loader = mdig.group(1) if mdig else ""
    rec(claims, "LIN-IMAGE", "PASS" if ver.returncode == 0 else "FAIL",
        "LINBC1 loader digest", f"sha256:{loader} file={sha256_file(img_path)}")
    img_b = bytes.fromhex(loader)

    gate = host(img_path, ["gate"])
    gst, gsteps, *_rest = parse_qr(gate)
    rec(claims, "LIN-SELF-GATE", "PASS" if gst == 1 else "FAIL", "u512_self_gate==1", f"steps={gsteps}")
    if gst != 1:
        return 1

    records = []
    vid = 0

    def add_muldiv(a, b, d):
        nonlocal vid
        out = host(img_path, ["muldiv", *map(str, words4(a) + words4(b) + words4(d))])
        st_, steps, q, r, _, _ = parse_qr(out)
        exp = py_muldiv(a, b, d)
        ok = st_ == exp[0] and (st_ != 1 or (q == exp[1] and r == exp[2] and q * d + r == a * b))
        raw = pack_lnr1(img_b, vid, OP_MULDIV, a, b, d, q if st_ == 1 else 0, r if st_ == 1 else 0, steps, st_)
        records.append({"id": vid, "op": "muldiv", "raw_hex": raw.hex(), "a": hex(a), "b": hex(b), "d": hex(d),
                        "q": hex(q), "r": hex(r), "status": st_, "steps": steps, "py": list(exp)})
        vid += 1
        return ok, st_, q, r, steps

    def add_mul(a, b):
        nonlocal vid
        out = host(img_path, ["mul", *map(str, words4(a) + words4(b))])
        st_, steps, _, _, prod, _ = parse_qr(out)
        ok = st_ == 1 and prod == a * b
        raw = pack_lnr1(img_b, vid, OP_MUL, a, b, 0, prod & U256, prod >> 256, steps, 1)
        records.append({"id": vid, "op": "mul", "raw_hex": raw.hex(), "a": hex(a), "b": hex(b),
                        "q": hex(prod & U256), "r": hex(prod >> 256), "status": 1, "steps": steps})
        vid += 1
        return ok, prod, steps

    def add_ge(A, B):
        nonlocal vid
        alo, ahi, blo, bhi = A & U256, A >> 256, B & U256, B >> 256
        out = host(img_path, ["ge", *map(str, words4(alo) + words4(ahi) + words4(blo) + words4(bhi))])
        st_, steps, _, _, _, ge = parse_qr(out)
        exp = int(A >= B)
        ok = ge == exp
        raw = pack_lnr1(img_b, vid, OP_GE, alo, blo, ahi, bhi, ge if ge is not None else 0, steps, 1)
        records.append({"id": vid, "op": "ge", "raw_hex": raw.hex(), "status": 1, "r": hex(exp), "steps": steps})
        vid += 1
        return ok, ge, steps

    def add_div(n, d):
        nonlocal vid
        out = host(img_path, ["div", *map(str, words8(n) + words4(d))])
        st_, steps, q, r, _, _ = parse_qr(out)
        if d == 0:
            exp = (-1, 0, 0)
        else:
            qq, rr = divmod(n, d)
            exp = (-2, 0, 0) if qq >= (1 << 256) else (1, qq, rr)
        ok = st_ == exp[0] and (st_ != 1 or (q == exp[1] and r == exp[2] and q * d + r == n))
        raw = pack_lnr1(img_b, vid, OP_DIV, n & U256, n >> 256, d, q if st_ == 1 else 0, r if st_ == 1 else 0, steps, st_)
        records.append({"id": vid, "op": "div", "raw_hex": raw.hex(), "status": st_, "steps": steps,
                        "q": hex(q), "r": hex(r)})
        vid += 1
        return ok, st_, q, r, steps

    ok_all = True
    o, st7, q7, r7, s7 = add_muldiv(7, 9, 2)
    ok_all &= o
    rec(claims, "LIN-7x9/2", "PASS" if o and q7 == 31 and r7 == 1 else "FAIL", "7*9/2=31 r=1", f"steps={s7}")
    o, _, _, _, s0 = add_muldiv(1, 1, 0)
    ok_all &= o
    rec(claims, "LIN-DIV0", "PASS" if o else "FAIL", "d=0 -> -1", f"steps={s0}")
    o, _, _, _, sov = add_muldiv(U256, U256, 1)
    ok_all &= o
    rec(claims, "LIN-QOV", "PASS" if o else "FAIL", "(2^256-1)^2/1 -> -2", f"steps={sov}")
    o, stw, qw, rw, sw = add_muldiv(1 << 255, 2, 3)
    ok_all &= o and qw == (1 << 256) // 3 and rw == 1
    rec(claims, "LIN-2^255*2/3", "PASS" if ok_all else "FAIL", "full-range q=0x5555.. r=1", f"steps={sw}")
    o, _, _, _, smx = add_muldiv(U256, U256, U256)
    ok_all &= o
    rec(claims, "LIN-MAX/MAX", "PASS" if o else "FAIL", "(2^256-1)^2/(2^256-1)", f"steps={smx}")
    ph_r = ((1 << 256) + 996) // 997
    o, stp, qp, rp, sp = add_muldiv(997, ph_r, 1997)
    ok_all &= o and stp == 1
    rec(claims, "LIN-PHANTOM", "PASS" if o and stp == 1 else "FAIL",
        "mulDiv(997, ceil(2^256/997), 1997) APPROVES", f"steps={sp} q={hex(qp)}")
    o, prod, smul = add_mul(1 << 128, 1 << 128)
    ok_all &= o and prod == (1 << 256)
    rec(claims, "LIN-MUL-2^128", "PASS" if o else "FAIL", "2^128*2^128=2^256", f"steps={smul}")
    o, g1, sg1 = add_ge(1 << 256, 1)
    o2, g0, sg0 = add_ge(1, 2)
    ok_all &= o and o2 and g1 == 1 and g0 == 0
    rec(claims, "LIN-GE-512", "PASS" if o and o2 else "FAIL", "512-bit ge 2^256>=1 and 1>=2", f"steps={sg1}/{sg0}")
    o, _, _, _, sdv = add_div((1 << 256) - 1, 1)
    ok_all &= o
    rec(claims, "LIN-DIV-512", "PASS" if o else "FAIL", "(2^256-1)/1 remainder identity", f"steps={sdv}")
    if not ok_all:
        return 1

    # e2e slice: settle_u256_word vs ref_amount_out + LCR2 real steps
    u256_img = Path("/tmp/u256_settle.linbc")
    run([str(C0), "image", str(U256_LIN), "-o", str(u256_img)])
    uver = run([str(BC1), str(u256_img), "--verify"])
    udig = re.search(r'img_sha256="([0-9a-f]+)"', uver.stdout).group(1)
    data = json.loads(UNFILTERED.read_text())
    exact = next(r for r in data["records"] if r.get("class") == "EXACT_INPUT")
    over = next(r for r in data["records"] if r.get("class") == "OVERPAID_INPUT")

    def ref(a, ri, ro):
        fee = a * 997
        return (fee * ro) // (ri * 1000 + fee)

    e2e = []
    lcr2_raw = []
    for recs, label in ((exact, "EXACT_INPUT"), (over, "OVERPAID_INPUT")):
        ain, rin, rout, onchain = recs["amount_in"], recs["reserve_in"], recs["reserve_out"], recs["amount_out"]
        py = ref(ain, rin, rout)
        st_, out, steps = u256_settle(u256_img, ain, rin, rout)
        ok = st_ == 1 and out == py
        note = f"lin={out} ref={py} onchain={onchain} steps={steps}"
        rec(claims, f"E2E-{label}", "PASS" if ok else "FAIL", f"settle_u256_word vs ref_amount_out ({label})", note)
        e2e.append({"class": label, "lin": out, "ref": py, "onchain": onchain, "steps": steps, "status": st_})
        lcr2_raw.append(pack_lcr2(bytes.fromhex(udig), recs.get("log_index", 0), ain, rin, rout, out or 0, steps, st_))
        if not ok:
            return 1
    if e2e[0]["lin"] != e2e[0]["onchain"]:
        rec(claims, "E2E-EXACT-CHAIN", "FAIL", "EXACT lin==onchain")
        return 1
    rec(claims, "E2E-EXACT-CHAIN", "PASS", "EXACT_INPUT lin==ref==onchain", f"out={e2e[0]['lin']}")
    rec(claims, "E2E-OVER-NEQ", "PASS" if e2e[1]["onchain"] != e2e[1]["ref"] else "SKIP",
        "OVERPAID onchain may neq ref (router overpay)", f"onchain={e2e[1]['onchain']} ref={e2e[1]['ref']}")
    lcr2_root = merkle([hashlib.sha256(LCR2_LEAF + r).digest() for r in lcr2_raw], LCR2_LEAF, LCR2_NODE)

    pst, _, psteps = u256_settle(u256_img, 1, 1, ph_r)
    rec(claims, "U256-PHANTOM-OV", "PASS" if pst == -2 else "FAIL",
        "settle_u256_word phantom still -2 (SafeMath width)", f"status={pst} steps={psteps}")
    if pst != -2:
        return 1

    leaves = [hashlib.sha256(DOM_LEAF + bytes.fromhex(r["raw_hex"])).digest() for r in records]
    root = merkle(leaves, DOM_LEAF, DOM_NODE)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "class_definition": "real FullMath *width* (256x256->512 /256), not CRT/mulmod, not a deployed pool",
        "image_loader_digest": loader,
        "image_file_sha256": sha256_file(img_path),
        "image_bytes": img_path.stat().st_size,
        "self_gate_steps": gsteps,
        "fullmath_sol_sha256": PIN_FULLMATH,
        "lnr1": {
            "record_bytes": 240,
            "dom_leaf": DOM_LEAF.decode(),
            "dom_node": DOM_NODE.decode(),
            "merkle_root": root,
            "image_loader_digest": loader,
            "records": records,
        },
        "records": records,
        "e2e_lcr2": {
            "image_loader_digest": udig,
            "merkle_root": lcr2_root,
            "steps_bound": True,
            "swaps": e2e,
            "note": "1 EXACT + 1 OVERPAID slice; full 2000/157 campaign still required",
        },
        "claims": claims,
        "not_proved": [
            "FullMath.sol CRT/mulmod assembly parity",
            "LIN replaces Uniswap, FullMath, or the EVM",
            "full unfiltered 157 / prefiltered 2000 campaign",
            "computational soundness of Merkle (tamper-evidence + independent identity only)",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    v = run([sys.executable, str(VERIFY), str(EVIDENCE), "--self-test"])
    rec(claims, "AUDITOR-LNR1", "PASS" if v.returncode == 0 else "FAIL",
        "stdlib auditor recomputes Merkle + identity; tamper rejected", v.stdout.strip())
    evidence["claims"] = claims
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    if v.returncode:
        print(v.stdout, v.stderr)
        return 1
    print("=" * 78)
    print(f"  LNR1 merkle=sha256:{root}")
    print(f"  LCR2 e2e merkle=sha256:{lcr2_root}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
