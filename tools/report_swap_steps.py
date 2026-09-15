#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publish VM steps for the i64 TOY Uniswap helper vs the canonical u256 limb engine.

The toy (`src/lin_uniswap_v2_library.lin`) is grammar/parity only: 18-decimal
Mainnet reserves overflow i64. Nobody should ship it. This report exists so
the step counts cannot be confused.

  make swap-steps
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
BC1 = ROOT / "transpile" / "c" / "bin" / "lin_bc1_run"
TOY = ROOT / "src" / "lin_uniswap_v2_library.lin"
U256 = ROOT / "examples" / "defi_settlement_proof" / "u256_settlement_engine.linbc"

# Canonical UniswapV2Library vector (fits in i64).
AIN, RIN, ROUT, WANT = 10000, 50000, 100000, 16624
TOY_STEPS_PINNED = 36
U256_STATUS_STEPS_PINNED = 233670
U256_WORD_STEPS_PINNED = 233706


def parse_result(stdout: str) -> tuple[int | None, int | None]:
    val = steps = None
    for tok in stdout.replace("{", " ").replace("}", " ").split():
        if tok.startswith("value="):
            val = int(tok.split("=", 1)[1])
        elif tok.startswith("result="):
            val = int(tok.split("=", 1)[1])
        elif tok.startswith("steps="):
            steps = int(tok.split("=", 1)[1])
    return val, steps


def to_signed_words(x: int) -> list[str]:
    out = []
    for _ in range(4):
        w = x & 0xFFFFFFFFFFFFFFFF
        if w >= (1 << 63):
            w -= 1 << 64
        out.append(str(w))
        x >>= 64
    return out


def main() -> int:
    for p in (C0, BC1, TOY, U256):
        if not p.exists():
            print(f"FAIL: missing {p} (run make -C transpile/c all)", file=sys.stderr)
            return 3

    toy = subprocess.run(
        [str(C0), "vm", str(TOY), "get_amount_out", str(AIN), str(RIN), str(ROUT)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if toy.returncode != 0:
        print(toy.stderr or toy.stdout, file=sys.stderr)
        return toy.returncode
    toy_val, toy_steps = parse_result(toy.stdout)
    if toy_val != WANT or toy_steps != TOY_STEPS_PINNED:
        print(f"FAIL: toy expected value={WANT} steps={TOY_STEPS_PINNED}, "
              f"got value={toy_val} steps={toy_steps}\n{toy.stdout}")
        return 1

    args = to_signed_words(AIN) + to_signed_words(RIN) + to_signed_words(ROUT)
    word_steps = []
    words = []
    for idx in (-1, 0, 1, 2, 3):
        p = subprocess.run(
            [str(BC1), str(U256), "settle_u256_word", *args, str(idx)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if p.returncode != 0:
            print(p.stderr or p.stdout, file=sys.stderr)
            return p.returncode
        val, steps = parse_result(p.stdout)
        if val is None or steps is None:
            print(f"FAIL: cannot parse u256 idx={idx}: {p.stdout}")
            return 1
        word_steps.append(steps)
        if idx >= 0:
            words.append(val & 0xFFFFFFFFFFFFFFFF)

    status_steps = word_steps[0]
    per_word = word_steps[1:]
    full = words[0] | (words[1] << 64) | (words[2] << 128) | (words[3] << 192)
    sum_steps = sum(word_steps)

    print("LIN SWAP STEPS (canonical vector 10000,50000,100000 -> 16624)")
    print(f"  toy_i64   file=src/lin_uniswap_v2_library.lin  class=TOY")
    print(f"            value={toy_val}  steps={toy_steps}  (single get_amount_out)")
    print(f"            NOT FOR MAINNET 18-decimal reserves (i64 overflow)")
    print(f"  u256      file=u256_settlement_engine.linbc  class=EXPERIMENTAL_PILOT")
    print(f"            value={full}  status_call_steps={status_steps}")
    print(f"            per_word_steps={per_word}  sum_5_calls={sum_steps}")
    print(f"            ABI is settle_u256_word (status + 4 limbs); not a single i64 return")
    print(f"  steps_bound=false on LCR2 batch receipts (make audit); do not mix toy steps into receipts")
    if full != WANT:
        print(f"FAIL: u256 value {full} != {WANT}")
        return 1
    if status_steps != U256_STATUS_STEPS_PINNED or any(s != U256_WORD_STEPS_PINNED for s in per_word):
        print(f"FAIL: u256 steps drifted (status={status_steps} want {U256_STATUS_STEPS_PINNED}, "
              f"words={per_word} want {U256_WORD_STEPS_PINNED})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
