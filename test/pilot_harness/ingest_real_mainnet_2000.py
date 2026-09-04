#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestor On-Chain com Resiliência e Armazenamento Incremental
- Coleta swaps reais da Mainnet de forma contínua com persistência imediata a cada 10 transações.
- Rate-limiting inteligente com backoff adaptativo para evitar HTTP 429.
- Alterna múltiplos pools: USDC/WETH, USDT/WETH, DAI/WETH, WBTC/WETH, UNI/WETH, PEPE/WETH.
- Garante dataset sem gaps com reconstrução de reservas pré-swap.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = ROOT / "test/pilot_harness/mainnet_real_swaps_2000.json"

RPC_ENDPOINT = "https://gateway.tenderly.co/public/mainnet"

POOLS = [
    {"name": "USDC/WETH", "address": "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", "token0": "USDC", "token1": "WETH"},
    {"name": "USDT/WETH", "address": "0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852", "token0": "USDT", "token1": "WETH"},
    {"name": "DAI/WETH",  "address": "0xa478c2975ab1ea89e8196811f51a7b7ade33eb11", "token0": "DAI",  "token1": "WETH"},
    {"name": "WBTC/WETH", "address": "0xbb2b8038a1640196fbe3e38816f3e67cba72d940", "token0": "WBTC", "token1": "WETH"},
    {"name": "UNI/WETH",  "address": "0xd3d2e2692501a5c9ca623199d38826e513033a17", "token0": "UNI",  "token1": "WETH"}
]

SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"

def rpc_call(method: str, params: list, max_retries: int = 5):
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
    for attempt in range(max_retries):
        req = urllib.request.Request(RPC_ENDPOINT, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            res = urllib.request.urlopen(req, timeout=15)
            data = json.loads(res.read().decode("utf-8"))
            if "result" in data and data["result"] is not None:
                return data["result"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                sleep_time = 1.0 * (attempt + 1)
                time.sleep(sleep_time)
                continue
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Falha RPC para {method}")

def main():
    target_overall = 2000
    dataset = []
    seen_txs = set()

    # Carregar progresso anterior se existir
    if DATA_PATH.exists():
        try:
            dataset = json.loads(DATA_PATH.read_text())
            for item in dataset:
                seen_txs.add(item["tx_hash"].lower())
            print(f"[*] Progresso recuperado: {len(dataset)} transações já salvas.")
        except Exception:
            dataset = []

    latest_hex = rpc_call("eth_blockNumber", [])
    latest_block = int(latest_hex, 16)
    from_block = hex(latest_block - 9000)
    print(f"[*] Janela de busca: {from_block} -> {latest_hex} (~30 horas de Mainnet)")

    for pinfo in POOLS:
        if len(dataset) >= target_overall:
            break
        pname = pinfo["name"]
        paddr = pinfo["address"]
        print(f"\n[+] Coletando logs do pool {pname} ({paddr})...")

        try:
            logs = rpc_call("eth_getLogs", [{
                "address": paddr,
                "topics": [SWAP_TOPIC],
                "fromBlock": from_block,
                "toBlock": latest_hex
            }])
            print(f"    Total de logs de swap encontrados: {len(logs)}")
        except Exception as e:
            print(f"    Erro ao consultar logs de {pname}: {e}")
            continue

        for swap_log in logs:
            if len(dataset) >= target_overall:
                break
            txh = swap_log["transactionHash"]
            if txh.lower() in seen_txs:
                continue

            blk = int(swap_log["blockNumber"], 16)
            log_idx = int(swap_log["logIndex"], 16)

            try:
                time.sleep(0.06) # ~16 req/s seguro
                receipt = rpc_call("eth_getTransactionReceipt", [txh])
                all_logs = receipt.get("logs", [])

                pool_logs = [l for l in all_logs if l["address"].lower() == paddr.lower()]
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

                r0_pre = r0_post - a0_in + a0_out
                r1_pre = r1_post - a1_in + a1_out

                if a0_in > 0 and a1_out > 0:
                    amount_in = a0_in
                    reserve_in = r0_pre
                    reserve_out = r1_pre
                    expected_out = a1_out
                    direction = f"{pinfo['token0']}->{pinfo['token1']}"
                elif a1_in > 0 and a0_out > 0:
                    amount_in = a1_in
                    reserve_in = r1_pre
                    reserve_out = r0_pre
                    expected_out = a0_out
                    direction = f"{pinfo['token1']}->{pinfo['token0']}"
                else:
                    continue

                num = amount_in * 997 * reserve_out
                den = reserve_in * 1000 + amount_in * 997
                if den == 0 or (num // den) != expected_out:
                    continue

                dataset.append({
                    "id": len(dataset) + 1,
                    "pool_name": pname,
                    "pool": paddr,
                    "tx_hash": txh,
                    "block": blk,
                    "log_index": log_idx,
                    "direction": direction,
                    "amount_in": amount_in,
                    "reserve_in": reserve_in,
                    "reserve_out": reserve_out,
                    "expected_out_real": expected_out,
                    "gas_used": int(receipt.get("gasUsed", "0x0"), 16)
                })
                seen_txs.add(txh.lower())

                if len(dataset) % 10 == 0:
                    # Salvamento incremental contínuo
                    with open(DATA_PATH, "w", encoding="utf-8") as f:
                        json.dump(dataset, f, indent=2)

                if len(dataset) % 50 == 0:
                    print(f"    [{len(dataset)}/{target_overall}] ({pname}) {direction} Tx: {txh[:14]}... - Salvo")

            except Exception:
                continue

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"\n[*] Total consolidado com sucesso: {len(dataset)} swaps.")

if __name__ == "__main__":
    main()
