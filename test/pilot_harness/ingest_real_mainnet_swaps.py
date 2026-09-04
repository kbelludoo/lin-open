#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestor On-Chain — Extração Factual de Swaps Reais da Mainnet do Ethereum
Sem simulações:
  - Consulta nós RPC públicos do Ethereum.
  - Localiza eventos Swap e Sync contíguos no pool USDC/WETH (0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc).
  - Reconstrói com exatidão matemática as reservas antes do swap.
  - Salva o dataset puro com hashes e valores para auditoria.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = ROOT / "test/pilot_harness/mainnet_real_swaps_100.json"

RPC_ENDPOINTS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://nodes.mewapi.io/rpc/eth",
    "https://rpc.flashbots.net"
]

POOL_USDC_WETH = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

def rpc_call(method: str, params: list, ep_idx: int = 0):
    for offset in range(len(RPC_ENDPOINTS)):
        ep = RPC_ENDPOINTS[(ep_idx + offset) % len(RPC_ENDPOINTS)]
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
        req = urllib.request.Request(ep, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            res = urllib.request.urlopen(req, timeout=10)
            data = json.loads(res.read().decode("utf-8"))
            if "result" in data and data["result"] is not None:
                return data["result"]
        except Exception:
            time.sleep(0.5)
            continue
    raise RuntimeError(f"Falha em todos os RPCs para método {method}")


_BLOCK_HASH_CACHE: dict[int, str] = {}


def resolve_block_hash(blk: int) -> str:
    """Busca o hash real do bloco (0x-prefixed) via eth_getBlockByNumber, com cache."""
    if blk in _BLOCK_HASH_CACHE:
        return _BLOCK_HASH_CACHE[blk]
    block = rpc_call("eth_getBlockByNumber", [hex(blk), False])
    bh = block.get("hash", "")
    _BLOCK_HASH_CACHE[blk] = bh
    return bh

def main():
    target_count = 50
    print(f"[*] Iniciando ingestão on-chain de {target_count} swaps reais da Mainnet...")
    
    latest_hex = rpc_call("eth_blockNumber", [])
    latest_block = int(latest_hex, 16)
    print(f"[*] Bloco mais recente da rede: {latest_block} ({latest_hex})")
    
    # Buscar logs de Swap dos últimos 300 blocos
    from_block = hex(latest_block - 300)
    print(f"[*] Buscando logs no intervalo de blocos: {from_block} -> {latest_hex}...")
    logs = rpc_call("eth_getLogs", [{
        "address": POOL_USDC_WETH,
        "topics": [SWAP_TOPIC],
        "fromBlock": from_block,
        "toBlock": latest_hex
    }])
    
    print(f"[*] Encontrados {len(logs)} eventos Swap no período.")
    
    # Selecionar transações únicas
    seen_txs = set()
    unique_swap_logs = []
    for l in logs:
        txh = l["transactionHash"]
        if txh not in seen_txs:
            seen_txs.add(txh)
            unique_swap_logs.append(l)
            if len(unique_swap_logs) >= target_count * 2:
                break
                
    print(f"[*] Processando recibos de {len(unique_swap_logs)} transações únicas...")
    
    dataset = []
    for i, swap_log in enumerate(unique_swap_logs):
        txh = swap_log["transactionHash"]
        blk = int(swap_log["blockNumber"], 16)
        log_idx = int(swap_log["logIndex"], 16)
        
        try:
            time.sleep(0.2) # Rate-limit preventivo
            receipt = rpc_call("eth_getTransactionReceipt", [txh])
            all_logs = receipt.get("logs", [])
            
            # Filtrar logs do pool USDC/WETH
            pool_logs = [l for l in all_logs if l["address"].lower() == POOL_USDC_WETH.lower()]
            
            # Encontrar o par Sync e Swap correspondente
            sync_candidate = None
            swap_candidate = None
            for pl in pool_logs:
                if pl.get("topics") and pl["topics"][0] == SYNC_TOPIC:
                    sync_candidate = pl
                elif pl.get("topics") and pl["topics"][0] == SWAP_TOPIC and int(pl["logIndex"], 16) == log_idx:
                    swap_candidate = pl
                    
            if not sync_candidate or not swap_candidate:
                continue
                
            sync_data = bytes.fromhex(sync_candidate["data"][2:])
            r0_post = int.from_bytes(sync_data[0:32], "big")
            r1_post = int.from_bytes(sync_data[32:64], "big")
            
            swap_data = bytes.fromhex(swap_candidate["data"][2:])
            a0_in = int.from_bytes(swap_data[0:32], "big")
            a1_in = int.from_bytes(swap_data[32:64], "big")
            a0_out = int.from_bytes(swap_data[64:96], "big")
            a1_out = int.from_bytes(swap_data[96:128], "big")
            
            # Reconstruir reservas pré-swap: r_pre = r_post - in + out
            r0_pre = r0_post - a0_in + a0_out
            r1_pre = r1_post - a1_in + a1_out
            
            # Determinar direção do swap
            if a0_in > 0 and a1_out > 0:
                amount_in = a0_in
                reserve_in = r0_pre
                reserve_out = r1_pre
                expected_out = a1_out
                token_in_symbol = "USDC"
                token_out_symbol = "WETH"
            elif a1_in > 0 and a0_out > 0:
                amount_in = a1_in
                reserve_in = r1_pre
                reserve_out = r0_pre
                expected_out = a0_out
                token_in_symbol = "WETH"
                token_out_symbol = "USDC"
            else:
                continue
                
            # Validar consistência matemática canônica
            num = amount_in * 997 * reserve_out
            den = reserve_in * 1000 + amount_in * 997
            if den == 0 or (num // den) != expected_out:
                continue
                
            entry = {
                "id": len(dataset) + 1,
                "tx_hash": txh,
                "block": blk,
                "block_hash": resolve_block_hash(blk),
                "log_index": log_idx,
                "pool": POOL_USDC_WETH,
                "direction": f"{token_in_symbol}->{token_out_symbol}",
                "amount_in": amount_in,
                "reserve_in": reserve_in,
                "reserve_out": reserve_out,
                "expected_out_real": expected_out,
                "gas_used": int(receipt.get("gasUsed", "0x0"), 16)
            }
            dataset.append(entry)
            print(f"  [{len(dataset)}/{target_count}] Tx: {txh[:18]}... Bloco {blk} ({entry['direction']}) - OK")
            
            if len(dataset) >= target_count:
                break
                
        except Exception as e:
            print(f"  [AVISO] Erro na tx {txh[:18]}...: {e}")
            continue
            
    print(f"\n[*] Total coletado com paridade matemática comprovada: {len(dataset)} transações.")
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"[*] Dataset salvo com sucesso em: {DATA_PATH}")

if __name__ == "__main__":
    main()
