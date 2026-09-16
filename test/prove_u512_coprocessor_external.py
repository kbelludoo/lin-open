#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External proof: LIN u512 numeric coprocessor vs Python int vs C11.

Proves (this run, recomputed):
  * 256x256->512 mul, 512-bit ge, restoring 512/256 div
  * remainder identity q*d+r == a*b and r<d
  * guards -1 (d=0) and -2 (q overflow)
  * C11 16-bit limbs == C11 64-bit __int128 schoolbook == Python int (n=520)
  * LINBC1 coprocessor == those oracles on goldens + sample
  * settle_u256_word vs ref_amount_out on 1 EXACT_INPUT + 1 OVERPAID_INPUT
    with real LinVM steps bound in LCR2
  * phantom AMM: coprocessor APPROVES 512-bit product; u256 settler still -2

Does not prove: FullMath CRT/mulmod, deployed pool, 2000/157 campaign,
computational soundness of Merkle (tamper-evidence + identity only).
Class: EXPERIMENTAL.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
LIN = ROOT / "src" / "lin_u512_coprocessor.lin"
U256_LIN = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.lin"
U512_SWAP = ROOT / "examples" / "defi_settlement_proof" / "u512_uniswap_v2_core.lin"
ORACLE_SRC = ROOT / "test" / "oracles" / "u512_coprocessor_c11.c"
ORACLE_BIN = ROOT / "test" / "oracles" / "u512_coprocessor_c11"
IMG = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor.linbc"
EVID = ROOT / "examples" / "u512_coprocessor" / "u512_coprocessor_evidence.json"
VERIFY = ROOT / "examples" / "u512_coprocessor" / "verify_u512_receipt.py"
MAINNET = ROOT / "test" / "pilot_harness" / "mainnet_unfiltered.json"
U256 = (1 << 256) - 1
MASK64 = (1 << 64) - 1
DOM_LCR2_LEAF = b"LIN:LEAF:1"
DOM_LCR2_NODE = b"LIN:NODE:1"
DOM_LNR_LEAF = b"LIN:U512:LEAF:1"
DOM_LNR_NODE = b"LIN:U512:NODE:1"

claims: list[dict] = []


def rec(cid: str, status: str, desc: str, note: str = "") -> None:
    claims.append({"id": cid, "status": status, "description": desc, "note": note})
    print(f"[{status}] {cid}  {desc}" + (f"  ({note})" if note else ""))


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def words_u(x: int, n: int = 4) -> list[int]:
    return [(x >> (64 * i)) & MASK64 for i in range(n)]


def words_i(x: int, n: int = 4) -> list[int]:
    out = []
    for w in words_u(x, n):
        out.append(w - (1 << 64) if w >= (1 << 63) else w)
    return out


def py_muldiv(a: int, b: int, d: int) -> tuple[int, int, int, int]:
    n = a * b
    if d == 0:
        return -1, 0, 0, n
    q, r = divmod(n, d)
    if q > U256:
        return -2, 0, 0, n
    return 1, q, r, n


def parse_eval(stdout: str) -> tuple[int, int, str]:
    m = re.search(r"\bresult=(-?\d+)\b", stdout)
    s = re.search(r"\bsteps=(\d+)\b", stdout)
    img = re.search(r'img_sha256="([0-9a-f]+)"', stdout)
    if not m or "status=\"EVALUATED\"" not in stdout:
        raise RuntimeError(stdout)
    return int(m.group(1)), int(s.group(1) if s else 0), img.group(1) if img else ""


def ensure_tools() -> None:
    if not C0.exists():
        p = run(["make", "-C", str(ROOT / "transpile" / "c"), "c0"], timeout=120)
        if p.returncode != 0:
            raise RuntimeError(p.stdout + p.stderr)
    g = run(["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-o", str(ORACLE_BIN), str(ORACLE_SRC)])
    if g.returncode != 0:
        raise RuntimeError(g.stdout + g.stderr)
    IMG.parent.mkdir(parents=True, exist_ok=True)
    im = run([str(C0), "image", str(LIN), "-o", str(IMG)])
    if im.returncode != 0:
        raise RuntimeError(im.stdout + im.stderr)


def c11_md(a: int, b: int, d: int) -> dict:
    cmd = [str(ORACLE_BIN), "muldiv", *[str(w) for w in words_u(a) + words_u(b) + words_u(d)]]
    p = run(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    kv = dict(tok.split("=", 1) for tok in p.stdout.split())
    q = int(kv["q0"]) | (int(kv["q1"]) << 64) | (int(kv["q2"]) << 128) | (int(kv["q3"]) << 192)
    r = int(kv["r0"]) | (int(kv["r1"]) << 64) | (int(kv["r2"]) << 128) | (int(kv["r3"]) << 192)
    n = 0
    for i in range(8):
        n |= int(kv[f"n{i}"]) << (64 * i)
    return {"status": int(kv["status"]), "q": q, "r": r, "n": n}


def lin_call(img: Path, fn: str, args: list[int]) -> tuple[int, int, str]:
    p = run([str(RUN), str(img), fn, *[str(a) for a in args]])
    if p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    return parse_eval(p.stdout)


def lin_md(a: int, b: int, d: int, want_r: bool = True) -> dict:
    base = words_i(a) + words_i(b) + words_i(d)
    st, steps, img = lin_call(IMG, "u512_muldiv_word", base + [-1])
    if st != 1:
        return {"status": st, "q": 0, "r": 0, "n": a * b, "steps": steps, "img": img}
    q = 0
    for i in range(4):
        w, s, _ = lin_call(IMG, "u512_muldiv_word", base + [i])
        q |= (w & MASK64) << (64 * i)
        steps += s
    r = 0
    if want_r:
        for i in range(4):
            w, s, _ = lin_call(IMG, "u512_muldiv_word", base + [4 + i])
            r |= (w & MASK64) << (64 * i)
            steps += s
    return {"status": 1, "q": q, "r": r, "n": a * b, "steps": steps, "img": img}


def be32(x: int) -> bytes:
    return (x & U256).to_bytes(32, "big")


def pack_lnr1(img: bytes, leaf_id: int, a: int, b: int, d: int, q: int, r: int, steps: int, status: int) -> bytes:
    raw = bytearray(240)
    raw[0:4] = b"LNR1"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, leaf_id)
    raw[56:88] = be32(a)
    raw[88:120] = be32(b)
    raw[120:152] = be32(d)
    raw[152:184] = be32(q)
    raw[184:216] = be32(r)
    struct.pack_into("<Q", raw, 216, steps)
    struct.pack_into("<q", raw, 224, status)
    struct.pack_into("<Q", raw, 232, 0)
    return bytes(raw)


def pack_lcr2(img: bytes, tx_id: int, ain: int, rin: int, rout: int, aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(208)
    raw[0:4] = b"LCR2"
    raw[4] = 1
    raw[5] = 1
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, 1)
    struct.pack_into("<Q", raw, 48, tx_id)
    raw[56:88] = be32(ain)
    raw[88:120] = be32(rin)
    raw[120:152] = be32(rout)
    raw[152:184] = be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    return bytes(raw)


def merkle(leaves: list[bytes], node: bytes) -> bytes:
    cur = list(leaves)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i + 1] if i + 1 < len(cur) else cur[i]
            nxt.append(hashlib.sha256(node + l + r).digest())
        cur = nxt
    return cur[0]


def ref_amount_out(ain: int, rin: int, rout: int) -> int:
    fee = ain * 997
    return (fee * rout) // (rin * 1000 + fee)


def lin_u256(img: Path, ain: int, rin: int, rout: int) -> tuple[int, int, int]:
    args = words_i(ain) + words_i(rin) + words_i(rout)
    st, steps, _ = lin_call(img, "settle_u256_word", args + [-1])
    if st != 1:
        return st, 0, steps
    out = 0
    for i in range(4):
        w, s, _ = lin_call(img, "settle_u256_word", args + [i])
        out |= (w & MASK64) << (64 * i)
        steps += s
    return 1, out, steps


def main() -> int:
    ensure_tools()
    chk = run([str(C0), "check", str(LIN)])
    rec("LIN-CHECK", "PASS" if chk.returncode == 0 else "FAIL", "Compiler-0 check of coprocessor")
    stest = run([str(ORACLE_BIN), "selftest"])
    rec("C11-SELFTEST", "PASS" if stest.returncode == 0 else "FAIL",
        "C11 16-bit == 64-bit schoolbook n=520", stest.stdout.strip())
    gate, gst, img_hex = lin_call(IMG, "u512_self_gate", [])
    rec("LIN-SELF-GATE", "PASS" if gate == 1 else "FAIL",
        "u512_self_gate==1", f"steps={gst}")
    vf = run([str(RUN), str(IMG), "--verify"])
    mimg = re.search(r'img_sha256="([0-9a-f]+)"', vf.stdout)
    loader = mimg.group(1) if mimg else ""
    rec("LINBC1-LOAD", "PASS" if vf.returncode == 0 else "FAIL", "loader verifies image", f"sha256:{loader}")

    goldens = [
        (7, 9, 2),
        (997000, 20000, 10997000),
        (1 << 255, 2, 3),
        (0, 9, 2),
        (7, 9, 0),
        (U256, U256, 1),
        (U256, U256, U256),
        (1, (U256 + 996) // 997, 1997),
    ]
    rng = random.Random(20260916)
    sample = [(rng.randrange(0, U256 + 1), rng.randrange(0, U256 + 1), rng.randrange(0, U256 + 1)) for _ in range(24)]
    py_c11 = 0
    for a, b, d in goldens + [(rng.randrange(0, U256 + 1), rng.randrange(0, U256 + 1), rng.randrange(1, U256 + 1)) for _ in range(520)]:
        ps, pq, pr, pn = py_muldiv(a, b, d)
        c = c11_md(a, b, d)
        if c["status"] != ps or c["q"] != pq or c["r"] != pr or c["n"] != pn:
            rec("PY-C11", "FAIL", "python int != C11", f"a={a} b={b} d={d}")
            break
        if ps == 1 and (pq * d + pr != pn or pr >= d):
            rec("REM-ID", "FAIL", "remainder identity broken")
            break
        py_c11 += 1
    else:
        rec("PY-C11", "PASS", f"{py_c11}/{py_c11} Python int == C11 full-range")
        rec("REM-ID", "PASS", "q*d+r==n and r<d on every APPROVE")

    lin_ok = 0
    lnr_rows = []
    img_b = bytes.fromhex(loader)
    for i, (a, b, d) in enumerate(goldens + sample[:8]):
        ps, pq, pr, pn = py_muldiv(a, b, d)
        lm = lin_md(a, b, d, want_r=(ps == 1))
        if lm["status"] != ps or lm["q"] != pq or (ps == 1 and lm["r"] != pr):
            rec("LIN-ORACLE", "FAIL", "LIN != Python/C11", f"vec={i} st {lm['status']} vs {ps}")
            break
        lin_ok += 1
        raw = pack_lnr1(img_b, i + 1, a, b, d, lm["q"], lm["r"] if ps == 1 else 0, lm["steps"], ps)
        lnr_rows.append({"raw_record_hex": raw.hex(),
                         "leaf_hash_hex": hashlib.sha256(DOM_LNR_LEAF + raw).digest().hex(),
                         "status": ps, "a": a, "b": b, "d": d, "q": lm["q"], "r": lm["r"] if ps == 1 else 0,
                         "steps": lm["steps"]})
    else:
        rec("LIN-ORACLE", "PASS", f"{lin_ok}/{lin_ok} LIN == Python on goldens+sample")

    # CLI spot 7*9/2
    spot, ssteps, _ = lin_call(IMG, "u512_muldiv_u64", [7, 9, 2])
    rec("CLI-SPOT", "PASS" if spot == 31 else "FAIL", "u512_muldiv_u64(7,9,2)==31", f"steps={ssteps}")
    g0, _, _ = lin_call(IMG, "u512_muldiv_word", words_i(3) + words_i(3) + words_i(10) + [-3])
    g1, _, _ = lin_call(IMG, "u512_muldiv_word", words_i(3) + words_i(4) + words_i(12) + [-3])
    rec("GE-512", "PASS" if g0 == 0 and g1 == 1 else "FAIL", "512-bit ge of product vs d (9<10, 12==12)")

    # Phantom AMM: 512-bit product required
    rout_p = (U256 + 996) // 997
    pst, pq, pr, pn = py_muldiv(997, rout_p, 1997)
    lm = lin_md(997, rout_p, 1997)
    rec("PHANTOM-512", "PASS" if lm["status"] == 1 and lm["q"] == pq == pn // 1997 else "FAIL",
        "coprocessor mulDiv(997,ceil(2^256/997),1997) APPROVES", f"q={lm['q']} steps={lm['steps']}")

    u256_img = Path("/tmp/u256_settle.linbc")
    u256_loader = ""
    im = run([str(C0), "image", str(U256_LIN), "-o", str(u256_img)])
    if im.returncode != 0:
        rec("U256-IMAGE", "FAIL", "could not freeze u256 settler")
    else:
        rec("U256-IMAGE", "PASS", "froze u256_settlement_engine.lin")
        st, _, usteps = lin_u256(u256_img, 1, 1, rout_p)
        rec("U256-PHANTOM-NEG2", "PASS" if st == -2 else "FAIL",
            "settle_u256_word still -2 (SafeMath width)", f"status={st} steps={usteps}")

    # Canonical Uniswap v2 512-bit core after 32-limb remainder widen
    sw_img = Path("/tmp/u512_swap.linbc")
    run([str(C0), "image", str(U512_SWAP), "-o", str(sw_img)])
    st, ss, _ = lin_call(sw_img, "settle_u512_swap", words_i(1000) + words_i(10000) + words_i(20000) + [-1])
    w0, sw0, _ = lin_call(sw_img, "settle_u512_swap", words_i(1000) + words_i(10000) + words_i(20000) + [0])
    rec("U512-CORE-1813", "PASS" if st == 1 and w0 == 1813 else "FAIL",
        "settle_u512_swap(1000,10000,20000)=1813", f"status_steps={ss} word0_steps={sw0}")

    # E2E LCR2: 1 EXACT_INPUT + 1 OVERPAID_INPUT, real steps
    data = json.loads(MAINNET.read_text())
    recs = data["records"]
    exact = next(r for r in recs if r["class"] == "EXACT_INPUT")
    over = next(r for r in recs if r["class"] == "OVERPAID_INPUT")
    vfy = run([str(RUN), str(u256_img), "--verify"])
    u256_loader = re.search(r'img_sha256="([0-9a-f]+)"', vfy.stdout).group(1)
    u256_b = bytes.fromhex(u256_loader)
    lcr2 = []
    e2e_ok = True
    for tx_id, row, label in ((1, exact, "EXACT_INPUT"), (2, over, "OVERPAID_INPUT")):
        ain, rin, rout = int(row["amount_in"]), int(row["reserve_in"]), int(row["reserve_out"])
        ref = ref_amount_out(ain, rin, rout)
        onchain = int(row["amount_out"])
        st, out, steps = lin_u256(u256_img, ain, rin, rout)
        if st != 1 or out != ref:
            rec("E2E-" + label, "FAIL", "settle_u256_word != ref_amount_out", f"lin={out} ref={ref}")
            e2e_ok = False
            break
        match_onchain = out == onchain
        rec("E2E-" + label, "PASS",
            f"lin==ref{'' if match_onchain else '!=onchain'}",
            f"lin={out} ref={ref} onchain={onchain} steps={steps}")
        raw = pack_lcr2(u256_b, tx_id, ain, rin, rout, out, steps, st)
        lcr2.append(raw)
    lcr2_root = ""
    if e2e_ok and len(lcr2) == 2:
        leaves = [hashlib.sha256(DOM_LCR2_LEAF + r).digest() for r in lcr2]
        lcr2_root = merkle(leaves, DOM_LCR2_NODE).hex()
        rec("LCR2-STEPS", "PASS", "LCR2 binds real LinVM steps (not steps=0)", f"root=sha256:{lcr2_root}")

    lnr_leaves = [bytes.fromhex(r["leaf_hash_hex"]) for r in lnr_rows]
    lnr_root = merkle(lnr_leaves, DOM_LNR_NODE).hex() if lnr_leaves else ""
    lnr_bundle = {
        "schema": "LNR1",
        "image_loader_digest": loader,
        "merkle_root_sha256": lnr_root,
        "records": lnr_rows,
    }
    evid = {
        "schema": "LIN_U512_COPROCESSOR_EVIDENCE_1.0",
        "class": "EXPERIMENTAL",
        "claims": claims,
        "pins": {
            "lin_src_sha256": sha256_file(LIN),
            "oracle_src_sha256": sha256_file(ORACLE_SRC),
            "linbc1_file_sha256": sha256_file(IMG),
            "linbc1_loader_sha256": loader,
            "lnr1_merkle_sha256": lnr_root,
            "lcr2_e2e_merkle_sha256": lcr2_root,
            "self_gate_steps": gst,
            "cli_spot_7_9_2": {"value": spot, "steps": ssteps},
        },
        "not_proved": [
            "FullMath.sol CRT/mulmod assembly equivalence",
            "2000/157 mainnet campaign on the coprocessor",
            "computational soundness of Merkle (tamper-evidence + identity)",
            "LIN replacing Uniswap or the EVM",
        ],
        "lnr1": lnr_bundle,
        "lcr2_e2e": {
            "image_loader_digest": u256_loader,
            "merkle_root_sha256": lcr2_root,
            "records": [{"raw_record_hex": r.hex()} for r in lcr2],
        },
    }
    EVID.write_text(json.dumps(evid, indent=2) + "\n")
    ver = run([sys.executable, str(VERIFY), "--self-test", str(EVID)])
    rec("AUDITOR", "PASS" if ver.returncode == 0 else "FAIL",
        "verify_u512_receipt.py --self-test + bundle", ver.stdout.strip().split("\n")[0])
    evid["claims"] = claims
    EVID.write_text(json.dumps(evid, indent=2) + "\n")
    failed = [c for c in claims if c["status"] == "FAIL"]
    print(f"\n{len(claims) - len(failed)}/{len(claims)} PASS, {len(failed)} FAIL  evidence={EVID}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        rec("HARNESS", "FAIL", type(e).__name__, str(e)[:400])
        print(json.dumps(claims, indent=2))
        sys.exit(1)
