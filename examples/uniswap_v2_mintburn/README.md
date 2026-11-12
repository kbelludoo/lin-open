# Uniswap V2 mint/burn — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V2
`Pair.mint` / `Pair.burn` LP-share math. The LIN kernel is
`src/lin_uniswap_v2_mintburn.lin` in lin-open. The full clone-lin copy lives in a
separate repository:

- **clone-lin:** https://github.com/kbelludoo/clone-lin-uniswap-v2-mintburn
- **Upstream:** [Uniswap/v2-core](https://github.com/Uniswap/v2-core) tag `v1.0.1`
  commit `4dd59067c76dea4a0e8e4bfdda41877a6b16dedc` (GPL-3.0-or-later).
  Solidity is **not vendored** (hash-only pin).
- **C11 oracle:** `test/oracles/uniswap_v2_mintburn_c11.c`
- **Harness:** `python3 test/prove_uniswap_v2_mintburn_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V2_MINTBURN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Uniswap V2's LP mint and burn formulas:

1. First mint: `sqrt(amount0 * amount1) - MINIMUM_LIQUIDITY` (`MINIMUM_LIQUIDITY=1000`).
2. Subsequent mint: `min(amount0 * supply / reserve0, amount1 * supply / reserve1)`.
3. Burn: `amount = liquidity * balance / totalSupply` (pro-rata, both tokens).

Real deltas versus the Solidity pair in this profile:

- IERC20 `balanceOf`, `getReserves`, `totalSupply`, `_mint`, `_burn`, `lock`, and
  events are function arguments / out of scope.
- `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in the
  C11 oracle). If the quotient does not fit in uint64 the clone fail-closes to 0.
- First-mint underflow (`sqrt < 1000`) fail-closes instead of SafeMath revert.
- `Math.min` is unsigned (`uv2_u_min`), matching uint64 order.

## What is not claimed

- Solidity **uint256** / **uint112** / mainnet pair parity
- LIN replacing Uniswap, the EVM, or LP token accounting
- TVL or dollar savings
- Computational soundness of Merkle / zk
- Protocol-fee `_mintFee` (see `clone-lin-uniswap-v2-mintfee`)

Named goldens: first `10000/10000` → **9000** LP; subsequent `1000/1000` vs
reserves `10000` supply `9000` → **900**; unbalanced `2000/1000` → **900** (the
`min`); burn `1000` of `10000` → **1000**; first mint `1000/1000` → **0**.

Machine-written evidence for a given run is in `uniswap_v2_mintburn_evidence.json`
(produced by the harness; do not hand-edit).
