#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/emit_batch_receipt.py — Emite receipt LCR2 real do lote (Merkle amarrado).

Formato canonico LCR2 208 bytes (mesmo de benchmarks/audit_cost_benchmark.py):
  [0:4]=b"LCR2" [4]=1 schema [5]=1 profile [6:8]=0
  [8:40]=img_digest(32B) [40:48]=run_id u64LE [48:56]=tx_id u64LE
  [56:88]=ain BE32 [88:120]=rin BE32 [120:152]=rout BE32 [152:184]=aout BE32
  [184:192]=steps u64LE [192:200]=status i64LE [200:208]=0 pad

Folha = SHA256(DOM_LEAF + record), no = SHA256(DOM_NODE + l + r),
DOM_LEAF=b"LIN:LEAF:1" DOM_NODE=b"LIN:NODE:1".
Arvore com duplicacao do ultimo quando impar (mesmo de test_lin_verifier.py).

LIMITACAO HONESTA DOCUMENTADA:
  steps=0 (steps_bound=false). O receipt amarra (img, inputs, outputs do
  oraculo, status) mas NAO amarra contagem de passos da VM por swap.
  Para custo de auditoria ver benchmarks/audit_cost_benchmark.py.
  aout e do ORACULO big-int (matematica correta), nao necessariamente o
  amount_out on-chain (overpaid/roteador diverge — ver DATASETS.md).

Uso:
  python3 tools/emit_batch_receipt.py --dataset test/pilot_harness/mainnet_real_swaps_2000.json \
    --out-manifest /tmp/batch_receipt.json --out-bin /tmp/batch_records.bin
"""
from __future__ import annotations
import argparse, hashlib, json, struct, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN_BC1_RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
U256_BC1 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.linbc"

DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
RECORD_BYTES = 208

def u256_oracle(ain, rin, rout):
    if ain <= 0 or rin <= 0 or rout <= 0:
        return -1, 0
    in_fee = ain * 997
    num = in_fee * rout
    den = rin * 1000 + in_fee
    if in_fee > (1 << 256) - 1 or num > (1 << 256) - 1 or den > (1 << 256) - 1:
        return -2, 0
    return 1, num // den

def int_to_be32(x: int) -> bytes:
    return (x & ((1 << 256) - 1)).to_bytes(32, "big")

def build_record(img: bytes, run_id: int, tx_id: int, ain: int, rin: int, rout: int, aout: int, steps: int, status: int) -> bytes:
    raw = bytearray(RECORD_BYTES)
    raw[0:4] = b"LCR2"
    raw[4] = 1; raw[5] = 1
    raw[6:8] = b"\x00\x00"
    raw[8:40] = img
    struct.pack_into("<Q", raw, 40, run_id)
    struct.pack_into("<Q", raw, 48, tx_id)
    raw[56:88] = int_to_be32(ain)
    raw[88:120] = int_to_be32(rin)
    raw[120:152] = int_to_be32(rout)
    raw[152:184] = int_to_be32(aout)
    struct.pack_into("<Q", raw, 184, steps)
    struct.pack_into("<q", raw, 192, status)
    raw[200:208] = b"\x00" * 8
    return bytes(raw)

def leaf_hash(rec: bytes) -> bytes:
    return hashlib.sha256(DOM_LEAF + rec).digest()

def parent_hash(l: bytes, r: bytes) -> bytes:
    return hashlib.sha256(DOM_NODE + l + r).digest()

def merkle_root(leaves: list[bytes]) -> bytes:
    cur = leaves
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i+1] if i+1 < len(cur) else cur[i]
            nxt.append(parent_hash(l, r))
        cur = nxt
    return cur[0]

def load_swaps(path: Path):
    d = json.loads(path.read_text())
    if isinstance(d, list):
        out = []
        for i, s in enumerate(d):
            out.append({
                "tx_id": i + 1,
                "amount_in": int(s.get("amount_in", 0)),
                "reserve_in": int(s.get("reserve_in", 0)),
                "reserve_out": int(s.get("reserve_out", 0)),
                "tx_hash": s.get("tx_hash", ""),
            })
        return out, "list-2000-prefiltered-arithmetic-corpus"
    recs = d.get("records", [])
    out = []
    for i, s in enumerate(recs):
        out.append({
            "tx_id": i + 1,
            "amount_in": int(s.get("amount_in", 0)),
            "reserve_in": int(s.get("reserve_in", 0)),
            "reserve_out": int(s.get("reserve_out", 0)),
            "tx_hash": s.get("tx_hash", ""),
            "class": s.get("class", ""),
        })
    filt = d.get("filter_policy", "")
    return out, f"unfiltered({filt})" if filt else "dict-records"

def get_img_digest() -> bytes:
    if not LIN_BC1_RUN.exists() or not U256_BC1.exists():
        print("ERRO: rode make -C transpile/c all primeiro", file=sys.stderr)
        sys.exit(3)
    p = subprocess.run([str(LIN_BC1_RUN), str(U256_BC1), "--verify"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for tok in p.stdout.split():
        if tok.startswith("img_sha256="):
            return bytes.fromhex(tok.split("=")[1].strip('"'))
    print("ERRO: img_sha256 ausente", file=sys.stderr)
    sys.exit(3)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out-manifest", required=True)
    ap.add_argument("--out-bin", required=True)
    ap.add_argument("--run-id", type=int, default=1)
    a = ap.parse_args()
    swaps, kind = load_swaps(Path(a.dataset))
    img = get_img_digest()
    records = []
    tx_hashes = []
    for s in swaps:
        st, aout = u256_oracle(s["amount_in"], s["reserve_in"], s["reserve_out"])
        records.append(build_record(img, a.run_id, s["tx_id"], s["amount_in"],
                                    s["reserve_in"], s["reserve_out"], aout, 0, st))
        tx_hashes.append(s.get("tx_hash", ""))
    leaves = [leaf_hash(r) for r in records]
    root = merkle_root(leaves)
    blob = b"".join(records)
    Path(a.out_bin).write_bytes(blob)
    manifest = {
        "schema": "LIN-BATCH-RECEIPT/1",
        "dataset": str(a.dataset),
        "dataset_kind": kind,
        "count": len(records),
        "run_id": a.run_id,
        "img_digest": img.hex(),
        "merkle_root": root.hex(),
        "domains": {"leaf": DOM_LEAF.decode(), "node": DOM_NODE.decode()},
        "record_bytes": RECORD_BYTES,
        "records_sha256": hashlib.sha256(blob).hexdigest(),
        "steps_bound": False,
        "steps_note": "steps=0 para todos os records; receipt amarra (img,inputs,outputs-oraculo,status), nao passos VM",
        "aout_note": "aout e do oraculo big-int (matematica correta); overpaid on-chain diverge — ver DATASETS.md",
        "tx_hashes": tx_hashes,
    }
    Path(a.out_manifest).write_text(json.dumps(manifest, indent=2))
    print(f"records: {len(records)} kind={kind}")
    print(f"img: {img.hex()}")
    print(f"root: {root.hex()}")
    print(f"bin: {a.out_bin} ({len(blob)} B) sha256={manifest['records_sha256']}")
    print(f"manifest: {a.out_manifest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
