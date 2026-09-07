#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark de throughput — 10.000 liquidações u256 na LinVM (via lin_bc1_run).

Mesma rota do test_live_ethereum_batch_50.py (5 chamadas por swap:
status + 4 palavras de 64 bits). Vetores sintéticos determinísticos com
magnitudes realistas de DeFi (1..10^24), todos válidos (sem overflow), para
medir o custo de EXECUÇÃO por swap independentemente da fonte dos dados.

Uso:
    python3 test/pilot_harness/bench_10k_synthetic.py [N]
"""

from __future__ import annotations

import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIN_BC1_RUN = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
U256_BC1 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.linbc"


def to_signed_words(x: int) -> list[str]:
    res = []
    for _ in range(4):
        w = x & 0xFFFFFFFFFFFFFFFF
        if w >= (1 << 63):
            w -= (1 << 64)
        res.append(str(w))
        x >>= 64
    return res


def run_swap(ain: int, rin: int, rout: int) -> None:
    args_base = to_signed_words(ain) + to_signed_words(rin) + to_signed_words(rout)
    for widx in (-1, 0, 1, 2, 3):
        subprocess.run(
            [str(LIN_BC1_RUN), str(U256_BC1), "settle_u256_word"] + args_base + [str(widx)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    rng = random.Random(20260904)

    # warmup (5 swaps)
    for _ in range(5):
        run_swap(rng.randint(1, 10**21), rng.randint(10**18, 10**24), rng.randint(10**18, 10**24))

    t0 = time.perf_counter()
    for _ in range(n):
        ain = rng.randint(1, 10**21)
        rin = rng.randint(10**18, 10**24)
        rout = rng.randint(10**18, 10**24)
        run_swap(ain, rin, rout)
    dt = time.perf_counter() - t0

    per_swap = dt / n
    print("=" * 78)
    print(f"  THROUGHPUT LINVM (u256, 5 chamadas/swap, subprocess C11)")
    print("=" * 78)
    print(f"  Swaps executados : {n:,}")
    print(f"  Tempo total      : {dt:.2f} s")
    print(f"  Por swap         : {per_swap * 1000:.2f} ms")
    print(f"  Projeção 10.000  : {per_swap * 10_000:.1f} s (~{per_swap * 10_000 / 60:.1f} min)")
    print(f"  Chamadas de VM   : {n * 5:,}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
