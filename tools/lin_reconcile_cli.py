#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lin-Audit CLI: Ferramenta Comercial de Conciliação Verificável de Operações DeFi
Executa a imagem determinística LinVM (reconciler_engine.linbc) contra relatórios internos
de bots de swap e eventos confirmados na blockchain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIN_BC1_RUN = ROOT / "transpile/c/bin/lin_bc1_run"
RECONCILER_BC1 = ROOT / "examples/defi_reconciliation_pilot/reconciler_engine.linbc"

DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"

STATUS_LABELS = {
    1: "CONCILIATED (Bit-Exact Match)",
    -1: "ERR_AMOUNT_MISMATCH (Output divergence)",
    -2: "ERR_ON_CHAIN_REVERTED (Transaction reverted on-chain)",
    -3: "ERR_SLIPPAGE_BREACH (Executed below min_out)",
    -4: "ERR_POOL_MISATTRIBUTION (Wrong pool address)",
    -5: "ERR_DECIMALS_SCALE (Decimals order of magnitude error)",
    -6: "ERR_GAS_DISCREPANCY (Gas budget exceeded)"
}

def run_lin_classify(
    is_tx_success: int,
    bot_reported_success: int,
    pool_match: int,
    reported_out: int,
    actual_out: int,
    min_out: int,
    gas_used: int,
    gas_budget: int
) -> int:
    # Normalizar valores que excedam 62 bits para comparação proporcional em uint256
    scale_shift = 0
    max_val = max(reported_out, actual_out, min_out)
    while (max_val >> scale_shift) > 0x3FFFFFFFFFFFFFFF:
        scale_shift += 1

    rep_w = (reported_out >> scale_shift) & 0x7FFFFFFFFFFFFFFF
    act_w = (actual_out >> scale_shift) & 0x7FFFFFFFFFFFFFFF
    min_w = (min_out >> scale_shift) & 0x7FFFFFFFFFFFFFFF

    # Se a truncagem por shift igualou valores onde antes act < min, preservar guarda
    if actual_out < min_out and act_w >= min_w and min_w > 0:
        act_w = min_w - 1

    cmd = [
        str(LIN_BC1_RUN), str(RECONCILER_BC1), "classify_reconciliation",
        str(is_tx_success),
        str(bot_reported_success),
        str(pool_match),
        str(rep_w),
        str(act_w),
        str(min_w),
        str(gas_used),
        str(gas_budget)
    ]
    out = subprocess.check_output(cmd, text=True)
    for token in out.split():
        if token.startswith("result="):
            return int(token.split("=")[1])
    raise RuntimeError("Falha ao executar LinVM")

def pack_leaf_lcr4(
    chain_id: int,
    block_hash_bytes: bytes,
    tx_hash_bytes: bytes,
    pool_addr_bytes: bytes,
    log_index: int,
    reported_out: int,
    actual_out: int,
    delta: int,
    status_code: int,
    image_digest: bytes
) -> bytes:
    raw = bytearray(248)
    raw[0:4] = b"LCR4"
    raw[4] = 1; raw[5] = 1
    raw[8:40] = image_digest
    struct.pack_into("<Q", raw, 40, chain_id)
    raw[48:80] = block_hash_bytes
    raw[80:112] = tx_hash_bytes
    raw[112:132] = pool_addr_bytes
    struct.pack_into("<I", raw, 132, log_index)
    raw[136:168] = reported_out.to_bytes(32, "big")
    raw[168:200] = actual_out.to_bytes(32, "big")
    delta_bytes = (delta & ((1 << 256) - 1)).to_bytes(32, "big")
    raw[200:232] = delta_bytes
    struct.pack_into("<q", raw, 232, status_code)
    return bytes(raw)

def build_merkle_root(leaves: list[bytes]) -> bytes:
    curr = list(leaves)
    while len(curr) > 1:
        next_level = []
        for i in range(0, len(curr), 2):
            left = curr[i]
            right = curr[i+1] if (i+1 < len(curr)) else curr[i]
            h = hashlib.sha256(DOM_NODE + left + right).digest()
            next_level.append(h)
        curr = next_level
    return curr[0]

def main():
    parser = argparse.ArgumentParser(description="Lin-Audit: CLI Verificável de Conciliação DeFi")
    parser.add_argument("--dataset", required=True, help="Caminho para arquivo JSON de swaps on-chain")
    parser.add_argument("--out-report", default="reconciliation_report.json", help="Arquivo de saída do laudo pericial")
    parser.add_argument("--slippage-tol-bps", type=int, default=50, help="Tolerância de slippage em BPS (padrão: 50 = 0.5 percent)")
    parser.add_argument("--gas-budget", type=int, default=0, help="Teto de gás tolerado (0 = desativar checagem de orçamento de gás)")
    args = parser.parse_args()

    data_file = Path(args.dataset)
    if not data_file.exists():
        print(f"Erro: Arquivo {data_file} não encontrado.")
        sys.exit(1)

    items = json.loads(data_file.read_text())
    img_bytes = RECONCILER_BC1.read_bytes()
    img_digest = hashlib.sha256(img_bytes).digest()

    print("=" * 80)
    print("  LIN-AUDIT CLI: CONCILIAÇÃO VERIFICÁVEL DE OPERAÇÕES DE SWAP")
    print(f"  Regras LinVM Digest: {img_digest.hex()[:32]}...")
    print(f"  Total de operações para auditoria: {len(items)}")
    print("=" * 80)

    leaves = []
    audit_results = []
    counts = {k: 0 for k in STATUS_LABELS}

    t0 = time.perf_counter()
    for item in items:
        actual_out = item["expected_out_real"]
        reported_out = item.get("reported_out", actual_out)
        min_out = item.get("min_out", int(actual_out * (10000 - args.slippage_tol_bps) / 10000))
        gas_used = item.get("gas_used", 150000)
        gas_budget = item.get("gas_budget", args.gas_budget)
        pool_match = 1 if item.get("pool_match", True) else 0
        tx_success = item.get("status_on_chain", 1)
        bot_success = item.get("bot_reported_success", 1)

        st = run_lin_classify(
            is_tx_success=tx_success,
            bot_reported_success=bot_success,
            pool_match=pool_match,
            reported_out=reported_out,
            actual_out=actual_out,
            min_out=min_out,
            gas_used=gas_used,
            gas_budget=gas_budget
        )

        counts[st] = counts.get(st, 0) + 1
        delta = reported_out - actual_out

        leaf = hashlib.sha256(DOM_LEAF + pack_leaf_lcr4(
            chain_id=1,
            block_hash_bytes=b"\x00" * 32,
            tx_hash_bytes=bytes.fromhex(item["tx_hash"][2:]),
            pool_addr_bytes=bytes.fromhex(item["pool"][2:]),
            log_index=item.get("log_index", 0),
            reported_out=reported_out,
            actual_out=actual_out,
            delta=delta,
            status_code=st,
            image_digest=img_digest
        )).digest()
        leaves.append(leaf)

        audit_results.append({
            "tx_hash": item["tx_hash"],
            "block": item["block"],
            "status_code": st,
            "status_label": STATUS_LABELS.get(st, f"UNKNOWN({st})"),
            "delta": delta,
            "leaf_sha256": leaf.hex()
        })

    merkle_root = build_merkle_root(leaves)
    elapsed = time.perf_counter() - t0

    report = {
        "metadata": {
            "lin_vm_image_digest": img_digest.hex(),
            "chain_id": 1,
            "total_swaps_audited": len(items),
            "merkle_root_lcr4": merkle_root.hex(),
            "audit_duration_seconds": round(elapsed, 4),
            "generated_at_utc": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())
        },
        "summary": {STATUS_LABELS[k]: v for k, v in counts.items() if v > 0},
        "transactions": audit_results
    }

    out_path = Path(args.out_report)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nRESUMO DO LAUDO AUDITADO:")
    for label, c in report["summary"].items():
        print(f"  • {label}: {c}")
    print("-" * 80)
    print(f"Raiz Merkle Auditável (LCR4): {merkle_root.hex()}")
    print(f"Relatório exportado em: {out_path.resolve()}")
    print("=" * 80)

if __name__ == "__main__":
    main()
