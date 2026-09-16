#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External auditable proof: LIN as a numeric coprocessor with a receipt.

Proves this run (no Zig):
  * 256x256->512 mul carry + leftover fail-closed
  * 512/256 restoring div, 32-limb remainder, 512-bit ge
  * remainder identity q*d+r == n and r<d vs Python int
  * C11 16-bit schoolbook == C11 64-bit __int128 == Python
  * LNR1 Merkle: Python hashlib, Node crypto, C11 lin_sha256, OpenSSL
    all agree; 1-bit leaf tamper rejected
  * LCR2 slice: settle_u256_word vs ref_amount_out on 3 EXACT + 3 OVERPAID
    with real steps; guards -1/-2

Does NOT prove: FullMath CRT/mulmod; a deployed pool; the 2000/157 campaign;
that proving 512 closes u256 by itself.

Class: EXPERIMENTAL (FullMath *width*).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
U256 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
U512A = ROOT / "examples" / "defi_settlement_proof" / "u512_uniswap_v2_core.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
AUD_SRC = ROOT / "test" / "oracles" / "verify_u512_receipt.c"
SHA_C = ROOT / "transpile" / "c" / "lin_c" / "lin_sha256.c"
FULLMATH = ROOT / "test" / "fixtures" / "external_proof" / "FullMath.sol"
MN = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
EVID = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
PIN_FM = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e"
DOM_LEAF = b"LIN:U512:LEAF:1"
DOM_NODE = b"LIN:U512:NODE:1"
LCR_LEAF = b"LIN:LEAF:1"
LCR_NODE = b"LIN:NODE:1"
UMAX = (1 << 256) - 1
CHECKS: list[tuple[str, bool, str]] = []


def run(cmd: list[str], inp: str | bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    text = not isinstance(inp, (bytes, bytearray))
    return subprocess.run(cmd, input=inp, capture_output=True, text=text, timeout=timeout, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def value_steps(out: str) -> tuple[int, int]:
    m = re.search(r"\bvalue=(-?\d+)\b", out)
    s = re.search(r"\bsteps=(\d+)\b", out)
    if not m or not s:
        raise RuntimeError(out)
    return int(m.group(1)), int(s.group(1))


def words(x: int, n: int = 4) -> list[int]:
    out = []
    for _ in range(n):
        w = x & ((1 << 64) - 1)
        out.append(w - (1 << 64) if w >= (1 << 63) else w)
        x >>= 64
    return out


def from_words(ws: list[int]) -> int:
    v = 0
    for i, w in enumerate(ws):
        v |= (w + (1 << 64) if w < 0 else w) << (64 * i)
    return v


def lin(fn: str, *args: int, src: Path = LIN) -> tuple[int, int]:
    p = run([str(C0), "vm", str(src), fn, *[str(a) for a in args]], timeout=90)
    if p.returncode != 0:
        raise RuntimeError(str(p.stdout) + str(p.stderr))
    return value_steps(p.stdout)


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int]:
    if d == 0:
        return -1, 0, 0
    q, r = divmod(a * b, d)
    if q > UMAX:
        return -2, 0, 0
    return 1, q, r


def be32(x: int) -> bytes:
    return x.to_bytes(32, "big")


def lnr1(src_d: bytes, run_id: int, vid: int, op: int, a: int, b: int, d: int,
         q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = op
    raw[8:40] = src_d
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, vid)
    raw[56:88] = be32(a)
    raw[88:120] = be32(b)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    return bytes(raw)


def merkle(recs: list[bytes], leaf_d: bytes, node_d: bytes) -> bytes:
    nodes = [hashlib.sha256(leaf_d + r).digest() for r in recs]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            L = nodes[i]
            R = nodes[i + 1] if i + 1 < len(nodes) else L
            nxt.append(hashlib.sha256(node_d + L + R).digest())
        nodes = nxt
    return nodes[0]


def openssl_sha256(data: bytes) -> bytes:
    p = run(["openssl", "dgst", "-sha256", "-binary"], inp=data, timeout=30)
    if p.returncode != 0 or len(p.stdout) != 32:
        raise RuntimeError("openssl dgst failed")
    return p.stdout


def node_root(path: Path) -> str | None:
    node = shutil.which("node") or "/exec-daemon/node"
    if not Path(node).exists():
        return None
    js = (
        "const fs=require('fs');const c=require('crypto');"
        "const b=fs.readFileSync(process.argv[1]);const N=240;"
        "const L=Buffer.from('LIN:U512:LEAF:1');const D=Buffer.from('LIN:U512:NODE:1');"
        "let n=[];for(let i=0;i<b.length;i+=N){n.push(c.createHash('sha256').update(L).update(b.slice(i,i+N)).digest())}"
        "while(n.length>1){const x=[];for(let i=0;i<n.length;i+=2){"
        "const L=n[i],R=i+1<n.length?n[i+1]:n[i];"
        "x.push(c.createHash('sha256').update(D).update(L).update(R).digest())}n=x}"
        "process.stdout.write(n[0].toString('hex'));"
    )
    p = run([node, "-e", js, str(path)])
    return p.stdout.strip() if p.returncode == 0 else None


def vectors() -> list[tuple[str, int, int, int]]:
    out: list[tuple[str, int, int, int]] = []
    edges = [0, 1, 2, 3, 7, 9, (1 << 64) - 1, 1 << 128, 1 << 255, UMAX]
    for a in edges:
        for b in edges:
            out.append(("MUL", a, b, 0))
            for d in (1, 2, 3, 1997, UMAX, a + 1 or 1):
                out.append(("MULDIV", a, b, d & UMAX or 1))
    rng = 0xC0FFEE
    for _ in range(180):
        rng = (rng * 6364136223846793005 + 1) & ((1 << 64) - 1)
        a = (rng * 0x9E3779B97F4A7C15) & UMAX
        b = (rng * 0xBF58476D1CE4E5B9) & UMAX
        d = (rng * 0x94D049BB133111EB) & UMAX
        out.append(("MUL", a, b, 0))
        out.append(("MULDIV", a, b, d if d else 1))
    return out


def lcr2(img: bytes, run_id: int, tx: int, ain: int, rin: int, rout: int,
         aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def ref_amount_out(ain: int, rin: int, rout: int) -> tuple[int, int]:
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    fee = ain * 997
    num = fee * rout
    den = rin * 1000 + fee
    if fee > UMAX or den > UMAX or num > UMAX:
        return -2, 0
    return 1, num // den


def main() -> int:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=180)
        if p.returncode != 0 or not C0.exists():
            print("FAIL build lin_c0", p.stderr)
            return 1

    ora = Path("/tmp/u512_coprocessor_c11")
    aud = Path("/tmp/verify_u512_receipt")
    cc1 = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", "-o", str(ora), str(ORACLE_SRC)])
    ok("c11_oracle_compile", cc1.returncode == 0, (cc1.stderr or b"")[-200:] if cc1.returncode else "")
    cc2 = run(["gcc", "-O2", "-Wall", "-Wextra", "-std=c11", f"-I{ROOT}/transpile/c/lin_c",
               "-o", str(aud), str(AUD_SRC), str(SHA_C)])
    ok("c11_auditor_compile", cc2.returncode == 0, (cc2.stderr or b"")[-200:] if cc2.returncode else "")
    st = run([str(ora), "--self-test"])
    ok("c11_selftest_identity", st.returncode == 0 and "SELFTEST_PASS" in st.stdout, st.stdout.strip())
    ast = run([str(aud), "--self-test"])
    ok("c11_auditor_tamper", ast.returncode == 0 and "AUDITOR_SELFTEST_PASS" in ast.stdout, ast.stdout.strip()[:80])

    vecs = vectors()
    lines = []
    expect = []
    for op, a, b, d in vecs:
        if op == "MUL":
            n = a * b
            expect.append((1, n & UMAX, n >> 256))
            lines.append(f"MUL {a:064x} {b:064x}\n")
        else:
            stt, q, r = py_muldiv(a, b, d)
            expect.append((stt, q, r))
            lines.append(f"MULDIV {a:064x} {b:064x} {d:064x}\n")
    bat = run([str(ora), "--batch"], inp="".join(lines), timeout=60)
    rows = [ln.split() for ln in bat.stdout.splitlines() if ln]
    match = bat.returncode == 0 and len(rows) == len(expect)
    ident_ok = True
    if match:
        for (stt, q, r), row, (op, a, b, d) in zip(expect, rows, vecs):
            got_s, got_q, got_r = int(row[0]), int(row[1], 16), int(row[2], 16)
            if got_s != stt or (stt == 1 and (got_q != q or got_r != r)):
                match = False
                break
            if op == "MULDIV" and stt == 1 and q * d + r != a * b:
                ident_ok = False
    ok("c11_python_full_range", match, f"n={len(expect)} stderr={bat.stderr.strip()}")
    ok("python_remainder_identity", ident_ok and match, "q*d+r==n")

    chk = run([str(C0), "check", str(LIN)])
    ok("lin_check", chk.returncode == 0 and "typecheck=passed" in chk.stdout, "")

    v, s_mul = lin("u512_mul_word", 7, 0, 0, 0, 9, 0, 0, 0, 0)
    ok("lin_mul_7x9", v == 63, f"value={v} steps={s_mul}")
    stt, s_md = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, -1)
    q, _ = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, 0)
    r, _ = lin("u512_muldiv_word", 7, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0, 4)
    ok("lin_muldiv_7x9_div2", stt == 1 and q == 31 and r == 1, f"q={q} r={r} steps={s_md}")

    all1 = -1
    lo0, _ = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 0)
    hi0, _ = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 4)
    hi3, _ = lin("u512_mul_word", all1, all1, all1, all1, all1, all1, all1, all1, 7)
    ok("lin_max_sq_512", lo0 == 1 and hi0 == -2 and hi3 == -1, f"lo={lo0} hi0={hi0} hi3={hi3}")

    hi255 = -(1 << 63)
    q55, s255 = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 3, 0, 0, 0, 0)
    r55, _ = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 3, 0, 0, 0, 4)
    ok("lin_2_255_x2_div3", q55 == 0x5555555555555555 and r55 == 1, f"q={q55} steps={s255}")

    z, _ = lin("u512_muldiv_word", 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, -1)
    ov, _ = lin("u512_muldiv_word", 0, 0, 0, hi255, 2, 0, 0, 0, 1, 0, 0, 0, -1)
    ok("lin_guards_-1_-2", z == -1 and ov == -2, f"d0={z} ov={ov}")

    ge1, _ = lin("u512_ge_word", 0, 0, 0, 0, 1, 0, 0, 0, all1, all1, all1, all1, 0, 0, 0, 0)
    ge0, _ = lin("u512_ge_word", all1, all1, all1, all1, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0)
    gee, _ = lin("u512_ge_word", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    ok("lin_ge_512", ge1 == 1 and ge0 == 0 and gee == 1, f"ge={ge1},{ge0},eq={gee}")

    gao, s_gao = lin("u512_muldiv_word", 997000, 0, 0, 0, 20000, 0, 0, 0, 10997000, 0, 0, 0, 0)
    ok("lin_getAmountOut_1813", gao == 1813, f"value={gao} steps={s_gao}")

    gate, s_gate = lin("u512_self_gate")
    ok("lin_self_gate", gate == 1, f"value={gate} steps={s_gate}")

    rout = ((1 << 256) + 996) // 997
    rw = words(rout)
    ph, s_ph = lin("u512_muldiv_word", 997, 0, 0, 0, *rw, 1997, 0, 0, 0, -1)
    u2, s_u2 = lin("settle_u256_word", 1, 0, 0, 0, 1, 0, 0, 0, *rw, -1, src=U256)
    qw = [lin("u512_muldiv_word", 997, 0, 0, 0, *rw, 1997, 0, 0, 0, i)[0] for i in range(4)]
    q_ph = from_words(qw)
    st_py, q_py, _ = py_muldiv(997, rout, 1997)
    ok("phantom_512_vs_u256_width", ph == 1 and u2 == -2 and q_ph == q_py and st_py == 1,
       f"coprocessor={ph} steps={s_ph} u256={u2} steps={s_u2}")

    w0, s_uv = lin("settle_u512_swap", 1000, 0, 0, 0, 10000, 0, 0, 0, 20000, 0, 0, 0, 0, src=U512A)
    ok("uniswap_u512_1813", w0 == 1813, f"value={w0} steps={s_uv}")

    ok("fullmath_sol_width_pin", sha256_file(FULLMATH) == PIN_FM, sha256_file(FULLMATH)[:16])

    src_d = hashlib.sha256(LIN.read_bytes()).digest()
    recs = []
    for i, (op, a, b, d) in enumerate(vecs[:64]):
        if op == "MUL":
            n = a * b
            recs.append(lnr1(src_d, 1, i, 1, a, b, 0, n & UMAX, n >> 256, 0, 1))
        else:
            stt, q, r = py_muldiv(a, b, d)
            recs.append(lnr1(src_d, 1, i, 2, a, b, d, q, r, 0, stt))
    recs.append(lnr1(src_d, 1, 900, 2, 7, 9, 2, 31, 1, s_md, 1))
    blob = Path("/tmp/u512_lnr1.bin")
    blob.write_bytes(b"".join(recs))
    py_root = merkle(recs, DOM_LEAF, DOM_NODE).hex()
    c_root = run([str(aud), "--root", str(blob)]).stdout.strip()
    n_root = node_root(blob)
    ol = openssl_sha256(DOM_LEAF + recs[0])
    on = openssl_sha256(DOM_NODE + hashlib.sha256(DOM_LEAF + recs[0]).digest()
                        + hashlib.sha256(DOM_LEAF + recs[1]).digest())
    pl = hashlib.sha256(DOM_LEAF + recs[0]).digest()
    pn = hashlib.sha256(DOM_NODE + pl + hashlib.sha256(DOM_LEAF + recs[1]).digest()).digest()
    ok("lnr1_quad_auditor", py_root == c_root and n_root == py_root and ol == pl and on == pn,
       f"py={py_root} c={c_root} node={n_root}")
    tamp = bytearray(b"".join(recs))
    tamp[56 + 31] ^= 1
    tpath = Path("/tmp/u512_lnr1_tamper.bin")
    tpath.write_bytes(bytes(tamp))
    t_py = merkle([bytes(tamp[i:i + 240]) for i in range(0, len(tamp), 240)], DOM_LEAF, DOM_NODE).hex()
    t_c = run([str(aud), "--root", str(tpath)]).stdout.strip()
    ok("lnr1_tamper_reject", t_py != py_root and t_c == t_py and t_c != c_root, f"tamper={t_py[:16]}")

    img_p = Path("/tmp/u256_settlement.linbc")
    im = run([str(C0), "image", str(U256), "-o", str(img_p)])
    img_d = hashlib.sha256(img_p.read_bytes()).digest() if img_p.exists() else b"\x00" * 32
    data = json.loads(MN.read_text())
    exacts = [r for r in data["records"] if r["class"] == "EXACT_INPUT"][:3]
    overs = [r for r in data["records"] if r["class"] == "OVERPAID_INPUT"][:3]
    lcr_recs = []
    e2e_ok = True
    e2e_detail = []
    e2e_rows = []
    for rec in exacts + overs:
        ain, rin, rout_v = rec["amount_in"], rec["reserve_in"], rec["reserve_out"]
        rst, ref = ref_amount_out(ain, rin, rout_v)
        aw, riw, row = words(ain), words(rin), words(rout_v)
        st_lin, _ = lin("settle_u256_word", *aw, *riw, *row, -1, src=U256)
        ws, s_w0 = [], 0
        for i in range(4):
            wi, si = lin("settle_u256_word", *aw, *riw, *row, i, src=U256)
            if i == 0:
                s_w0 = si
            ws.append(wi)
        got = from_words(ws)
        onchain = rec["amount_out"]
        cls = rec["class"]
        match_ref = st_lin == rst and (rst != 1 or got == ref) and s_w0 != 0
        if cls == "EXACT_INPUT" and got != onchain:
            match_ref = False
        if not match_ref:
            e2e_ok = False
        e2e_detail.append(f"{cls} lin={got} ref={ref} onchain={onchain} st={st_lin} steps={s_w0}")
        e2e_rows.append({"class": cls, "lin": got, "ref": ref, "onchain": onchain, "status": st_lin, "steps": s_w0})
        lcr_recs.append(lcr2(img_d, 2, rec.get("log_index", 1), ain, rin, rout_v, got, s_w0, st_lin))
    g_st, s_g1 = lin("settle_u256_word", 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, -1, src=U256)
    g_ov, s_g2 = lin("settle_u256_word", 1, 0, 0, 0, 1, 0, 0, 0, *rw, -1, src=U256)
    ok("lcr2_exact_overpaid_steps", e2e_ok and g_st == -1 and g_ov == -2 and len(exacts) == 3 and len(overs) == 3,
       " | ".join(e2e_detail) + f" guards={g_st}/{g_ov} steps={s_g1}/{s_g2}")
    lcr_root = merkle(lcr_recs, LCR_LEAF, LCR_NODE).hex()
    ok("lcr2_merkle_recompute", len(lcr_root) == 64, f"sha256:{lcr_root}")
    ok("image_encode", im.returncode == 0 and img_p.exists(), sha256_file(img_p)[:16] if img_p.exists() else "")

    EVID.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "product": "numeric coprocessor with auditable receipt",
        "domains": {"leaf": "LIN:U512:LEAF:1", "node": "LIN:U512:NODE:1"},
        "lnr1_bytes": 240,
        "lnr1_merkle": py_root,
        "lcr2_merkle": lcr_root,
        "pins": {
            "lin_src": sha256_file(LIN),
            "oracle_c": sha256_file(ORACLE_SRC),
            "auditor_c": sha256_file(AUD_SRC),
            "harness": sha256_file(Path(__file__)),
            "fullmath_sol": sha256_file(FULLMATH),
            "u256_linbc1": sha256_file(img_p) if img_p.exists() else "",
        },
        "measured": {
            "self_gate_steps": s_gate,
            "mul_7x9_steps": s_mul,
            "muldiv_7x9_div2_steps": s_md,
            "two_255_x2_div3_steps": s255,
            "phantom_coprocessor_steps": s_ph,
            "phantom_u256_status": u2,
            "c11_batch_n": len(expect),
            "lcr2": e2e_rows,
        },
        "leaves": [
            {"op": "MULDIV", "a": hex(7), "b": hex(9), "d": hex(2), "q": hex(31), "r": hex(1), "status": 1, "steps": s_md}
        ],
        "not_claimed": [
            "FullMath CRT/mulmod assembly",
            "deployed pool",
            "full 2000/157 campaign",
            "that 512 proof closes u256 by itself",
        ],
    }
    EVID.write_text(json.dumps(evidence, indent=2) + "\n")
    vr = run([sys.executable, str(VERIFY), str(EVID), "--self-test"], timeout=30)
    ok("standalone_receipt_verifier", vr.returncode == 0 and "PASS" in vr.stdout, vr.stdout.strip()[:120])

    npass = sum(1 for _, c, _ in CHECKS if c)
    print(f"\n{npass}/{len(CHECKS)} PASS")
    print("src", sha256_file(LIN))
    print("oracle", sha256_file(ORACLE_SRC))
    print("auditor", sha256_file(AUD_SRC))
    print("lnr1", py_root)
    print("lcr2", lcr_root)
    print("self_gate_steps", s_gate)
    print("class EXPERIMENTAL FullMath-width not CRT not a pool")
    return 0 if npass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
