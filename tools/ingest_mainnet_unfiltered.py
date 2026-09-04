#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestor Mainnet SEM FILTRO — Uniswap V2 (R5: no overclaim).

Diferença crucial em relação a test/pilot_harness/ingest_real_mainnet_*.py:
aqueles scripts descartavam silenciosamente todo swap cujo amount_out NÃO
batia com getAmountOut (`if (num // den) != expected_out: continue`). Um
dataset assim torna "100% de paridade" uma tautologia.

Este ingestor grava TODOS os eventos Swap de uma janela contínua de blocos,
sem descartar nada, e classifica cada um:

  EXACT_INPUT      amount_out == getAmountOut(amount_in, r_in, r_out)
  EXACT_OUTPUT     amount_in  == getAmountIn(amount_out, r_in, r_out)
                   (usuário fixou a saída; entrada tem +1 wei de arredondamento)
  OVERPAID_INPUT   amount_out <  getAmountOut (entrada excedente / poeira de
                   roteador / fee-on-transfer / agregador). O invariante K
                   ainda se sustenta.
  BOTH_DIRECTIONS  amount0In>0 e amount1In>0 (ou ambos out>0) — swap atípico.
  K_VIOLATION      (r_in*1000 - a_in*3)*(r_out) > r_in_post*r_out_post*1000
                   ajustado — não deveria ocorrer em um pair V2 legítimo.
  UNCLASSIFIED     nenhum dos anteriores.

Ordem de decisão: K_VIOLATION > EXACT_INPUT > EXACT_OUTPUT > OVERPAID_INPUT.
Ambiguidade declarada: em tokens de poucos decimais (USDC/USDT), um pequeno
excesso de entrada pode satisfazer `amount_in == getAmountIn(amount_out)` e
será rotulado EXACT_OUTPUT — as duas hipóteses são indistinguíveis só pelos logs.

Também registra quantos logs foram vistos, quantos receipts falharam, etc.
O relatório final é a distribuição real, não um número forçado.

Uso:
  python3 tools/ingest_mainnet_unfiltered.py --blocks 200 --out test/pilot_harness/mainnet_unfiltered.json
  python3 tools/ingest_mainnet_unfiltered.py --from-block 25891842 --to-block 25892042 --rpc https://...

Requer acesso a um JSON-RPC Ethereum (eth_getLogs + eth_getTransactionReceipt).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RPCS = [
    "https://gateway.tenderly.co/public/mainnet",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://cloudflare-eth.com",
]

POOLS = {
    "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc": ("USDC/WETH", "USDC", "WETH"),
    "0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852": ("USDT/WETH", "USDT", "WETH"),
    "0xa478c2975ab1ea89e8196811f51a7b7ade33eb11": ("DAI/WETH", "DAI", "WETH"),
    "0xbb2b8038a1640196fbe3e38816f3e67cba72d940": ("WBTC/WETH", "WBTC", "WETH"),
    "0xd3d2e2692501a5c9ca623199d38826e513033a17": ("UNI/WETH", "UNI", "WETH"),
}

SYNC_TOPIC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"
SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"


def get_amount_out(a_in: int, r_in: int, r_out: int) -> int:
    fee = a_in * 997
    return (fee * r_out) // (r_in * 1000 + fee)


def get_amount_in(a_out: int, r_in: int, r_out: int) -> int | None:
    if a_out >= r_out:
        return None
    return (r_in * a_out * 1000) // ((r_out - a_out) * 997) + 1


class Rpc:
    def __init__(self, endpoints: list[str]):
        self.endpoints = endpoints
        self.idx = 0
        self.calls = 0
        self.failures = 0

    def call(self, method: str, params: list, retries: int = 6):
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
        last = None
        for attempt in range(retries):
            url = self.endpoints[self.idx % len(self.endpoints)]
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json", "User-Agent": "lin-ingest/1.0"})
            self.calls += 1
            try:
                data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
                if "result" in data:
                    return data["result"]
                last = data.get("error")
            except Exception as e:  # noqa: BLE001 — registrado e reportado
                last = repr(e)
            self.failures += 1
            self.idx += 1
            time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"RPC {method} falhou após {retries} tentativas: {last}")


def classify(a0_in, a1_in, a0_out, a1_out, r0_pre, r1_pre, r0_post, r1_post):
    """Retorna (classe, detalhes)."""
    if (a0_in > 0 and a1_in > 0) or (a0_out > 0 and a1_out > 0):
        return "BOTH_DIRECTIONS", {}
    if a0_in > 0 and a1_out > 0:
        a_in, a_out, r_in, r_out = a0_in, a1_out, r0_pre, r1_pre
        direction = "token0->token1"
    elif a1_in > 0 and a0_out > 0:
        a_in, a_out, r_in, r_out = a1_in, a0_out, r1_pre, r0_pre
        direction = "token1->token0"
    else:
        return "UNCLASSIFIED", {"reason": "sem par (in,out) positivo"}

    if r_in <= 0 or r_out <= 0:
        return "UNCLASSIFIED", {"reason": "reserva pré-swap não positiva", "direction": direction}

    det = {"direction": direction, "amount_in": a_in, "amount_out": a_out,
           "reserve_in": r_in, "reserve_out": r_out}
    exp_out = get_amount_out(a_in, r_in, r_out)
    det["get_amount_out"] = exp_out
    exp_in = get_amount_in(a_out, r_in, r_out)
    det["get_amount_in"] = exp_in

    # Invariante K com taxa (UniswapV2Pair.swap): balance0Adjusted*balance1Adjusted >= r0*r1*1000^2
    b0adj = r0_post * 1000 - a0_in * 3
    b1adj = r1_post * 1000 - a1_in * 3
    k_ok = b0adj * b1adj >= r0_pre * r1_pre * 1_000_000
    det["k_invariant_ok"] = k_ok
    if not k_ok:
        return "K_VIOLATION", det
    if a_out == exp_out:
        return "EXACT_INPUT", det
    if exp_in is not None and a_in == exp_in:
        return "EXACT_OUTPUT", det
    if a_out < exp_out:
        det["shortfall_wei"] = exp_out - a_out
        return "OVERPAID_INPUT", det
    return "UNCLASSIFIED", det


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", action="append", help="endpoint JSON-RPC (repetível)")
    ap.add_argument("--blocks", type=int, default=200, help="janela de blocos a partir do head")
    ap.add_argument("--from-block", type=int)
    ap.add_argument("--to-block", type=int)
    ap.add_argument("--chunk", type=int, default=50, help="blocos por eth_getLogs")
    ap.add_argument("--out", default=str(ROOT / "test/pilot_harness/mainnet_unfiltered.json"))
    ap.add_argument("--sleep", type=float, default=0.06)
    args = ap.parse_args()

    rpc = Rpc(args.rpc or DEFAULT_RPCS)
    if args.from_block and args.to_block:
        lo, hi = args.from_block, args.to_block
    else:
        head = int(rpc.call("eth_blockNumber", []), 16)
        hi = head - 6  # margem de reorg
        lo = hi - args.blocks + 1
    print(f"[*] Janela contínua: blocos {lo}..{hi} ({hi - lo + 1} blocos), {len(POOLS)} pools")

    stats = Counter()
    records = []
    receipt_cache: dict[str, dict] = {}

    for start in range(lo, hi + 1, args.chunk):
        end = min(start + args.chunk - 1, hi)
        logs = rpc.call("eth_getLogs", [{
            "fromBlock": hex(start), "toBlock": hex(end),
            "address": list(POOLS.keys()), "topics": [SWAP_TOPIC]}])
        stats["swap_logs_seen"] += len(logs)
        for lg in logs:
            txh = lg["transactionHash"]
            paddr = lg["address"].lower()
            pname, t0, t1 = POOLS[paddr]
            log_idx = int(lg["logIndex"], 16)
            try:
                if txh not in receipt_cache:
                    time.sleep(args.sleep)
                    receipt_cache[txh] = rpc.call("eth_getTransactionReceipt", [txh])
                rc = receipt_cache[txh]
            except RuntimeError as e:
                stats["receipt_failed"] += 1
                records.append({"tx_hash": txh, "log_index": log_idx, "pool": paddr, "pool_name": pname,
                                "block": int(lg["blockNumber"], 16), "class": "RECEIPT_UNAVAILABLE",
                                "error": str(e)})
                continue

            # O Sync do MESMO pool imediatamente anterior (logIndex menor mais próximo) ao Swap
            pool_logs = sorted((l for l in rc["logs"] if l["address"].lower() == paddr),
                               key=lambda l: int(l["logIndex"], 16))
            sync = None
            for pl in pool_logs:
                if int(pl["logIndex"], 16) < log_idx and pl["topics"][0] == SYNC_TOPIC:
                    sync = pl
            if sync is None:
                stats["no_sync_before_swap"] += 1
                records.append({"tx_hash": txh, "log_index": log_idx, "pool": paddr, "pool_name": pname,
                                "block": int(lg["blockNumber"], 16), "class": "NO_SYNC_LOG"})
                continue

            sd = bytes.fromhex(sync["data"][2:])
            r0_post, r1_post = int.from_bytes(sd[0:32], "big"), int.from_bytes(sd[32:64], "big")
            wd = bytes.fromhex(lg["data"][2:])
            a0_in, a1_in, a0_out, a1_out = (int.from_bytes(wd[i:i + 32], "big") for i in range(0, 128, 32))
            # Reservas pré-swap (Sync é emitido após _update com os saldos pós-swap).
            # Nota: se o router enviou tokens excedentes, r_post inclui esse excedente —
            # isso é exatamente o que classificamos como OVERPAID_INPUT.
            r0_pre, r1_pre = r0_post - a0_in + a0_out, r1_post - a1_in + a1_out

            cls, det = classify(a0_in, a1_in, a0_out, a1_out, r0_pre, r1_pre, r0_post, r1_post)
            stats[cls] += 1
            rec = {"tx_hash": txh, "log_index": log_idx, "block": int(lg["blockNumber"], 16),
                   "pool": paddr, "pool_name": pname, "token0": t0, "token1": t1,
                   "amount0In": a0_in, "amount1In": a1_in, "amount0Out": a0_out, "amount1Out": a1_out,
                   "reserve0_pre": r0_pre, "reserve1_pre": r1_pre,
                   "reserve0_post": r0_post, "reserve1_post": r1_post,
                   "tx_status": int(rc.get("status", "0x1"), 16),
                   "gas_used": int(rc.get("gasUsed", "0x0"), 16),
                   "class": cls, **det}
            records.append(rec)
        print(f"    blocos {start}-{end}: logs={stats['swap_logs_seen']} "
              f"EXACT_INPUT={stats['EXACT_INPUT']} EXACT_OUTPUT={stats['EXACT_OUTPUT']} "
              f"OVERPAID={stats['OVERPAID_INPUT']} outros={sum(v for k, v in stats.items() if k not in ('swap_logs_seen','EXACT_INPUT','EXACT_OUTPUT','OVERPAID_INPUT'))}")

    total = sum(1 for r in records)
    manifest = {
        "schema": "lin.uniswap_v2.unfiltered_ingest.v1",
        "chain_id": 1,
        "block_range": [lo, hi],
        "pools": {k: v[0] for k, v in POOLS.items()},
        "rpc_endpoints": rpc.endpoints,
        "rpc_calls": rpc.calls,
        "rpc_failures": rpc.failures,
        "filter_policy": "NONE — todos os eventos Swap da janela são gravados e classificados",
        "counts": dict(stats),
        "total_records": total,
        "records": records,
    }
    Path(args.out).write_text(json.dumps(manifest, indent=1))

    print("\n=== DISTRIBUIÇÃO REAL (sem filtro) ===")
    for k in ["EXACT_INPUT", "EXACT_OUTPUT", "OVERPAID_INPUT", "BOTH_DIRECTIONS",
              "K_VIOLATION", "UNCLASSIFIED", "NO_SYNC_LOG", "RECEIPT_UNAVAILABLE"]:
        n = stats.get(k, 0)
        if total:
            print(f"  {k:<20} {n:>6}  ({100.0 * n / total:6.2f}%)")
    print(f"  {'TOTAL':<20} {total:>6}")
    print(f"[*] gravado em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
