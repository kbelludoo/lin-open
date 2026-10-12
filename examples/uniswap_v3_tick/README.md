# Uniswap V3 TickMath.getSqrtRatioAtTick — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V3's
tick-to-sqrtPrice bit table. The LIN kernel is `src/lin_uniswap_v3_tick.lin`
in lin-open. The full kernel copy lives in a separate clone-lin repository.

- **Upstream:** [Uniswap/v3-core](https://github.com/Uniswap/v3-core) tag `v1.0.0` `contracts/libraries/TickMath.sol` (GPL-2.0-or-later after BUSL Change Date 2023-04-01)
- **LIN clone (this tree):** [`src/lin_uniswap_v3_tick.lin`](../../src/lin_uniswap_v3_tick.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v3-tick
- **Pinned fixture:** `test/fixtures/external_proof/TickMath.sol`
- **C11 oracle:** `test/oracles/uniswap_v3_tick_c11.c`
- **Harness:** `python3 test/prove_uniswap_v3_tick_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V3_TICK_CLONE_LIN.rulel`

## What is claimed

Experimental, Q32-scale reproduction of Uniswap V3 `getSqrtRatioAtTick`:
`sqrt(1.0001^tick)` as a 14-bit bit-shift table (`|tick| <= 16383`). Real
deltas versus the Solidity library in this profile:

1. Q128 magics / `>> 128` / `uint160` / `type(uint256).max` are rejected by
   `lin_from_solidity.lin` (`REJ_SOLIDITY_TICK_SQRT` and friends). The LIN
   kernel is a reduced Q32 table, not an emit of the Solidity body.
2. Positive-tick invert uses 128-bit `muldiv(Q32, Q32, ratio)`. Naive signed
   i64 `(Q32*Q32)/ratio` wraps to **0** and hides the swap price.
3. First-order linear `Q32 + (Q32*tick)/20000` matches tick 0 and is close at
   tick 1, but at tick 8192 the bit table is **6469012455** vs linear
   **6054185900** (delta 414826555). Linearizing ticks misprices concentrated
   liquidity.

## What is not claimed

- Solidity **Q64.96** / **uint160** / `|tick| <= 887272` mainnet parity
- LIN replacing Uniswap V3 pools, SwapRouter, or NFTs
- `getNextSqrtPriceFromInput` (that is clone-lin-uniswap-v3-next-sqrt)
- `getAmount0Delta` / `getAmount1Delta` (that is clone-lin-uniswap-v3-sqrt)
- `getTickAtSqrtRatio` inverse (assembly MSB path; `REJ_SOLIDITY_INLINE_ASM`)
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `uniswap_v3_tick_evidence.json`
(produced by the harness; do not hand-edit).
