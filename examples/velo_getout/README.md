# Velodrome / Aerodrome `getAmountOut` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Velodrome V2
`Pool.getAmountOut` (Solidly-style volatile `x*y` and stable `x³y+y³x` Newton).
The LIN kernel lives in a **separate** repository:

**Clone-LIN:** https://github.com/kbelludoo/clone-lin-velo-getout (`3fb05fb2`)

- **Upstream (hash-pin only, not vendored):** [velodrome-finance/contracts](https://github.com/velodrome-finance/contracts) `contracts/Pool.sol` (GPL-3.0-or-later) commit `b3065d8b6702b14b094f9f6046b752cc9f78c43b`
  - sha256 `32d040ff419fa9b1f9113f7e10d587b332a2ab9c6b6099851025cc16a4e986bb`
  - git blob `91412c378bba4d8076271cee52e1397b1520b709`
- **LIN clone (this tree, results copy):** [`src/lin_velo_getout.lin`](../../src/lin_velo_getout.lin)
- **C11 oracle:** `test/oracles/velo_getout_c11.c`
- **Harness:** `python3 test/prove_velo_getout_external.py` / `make velo-getout-proof`
- **Event receipt:** `docs/events/EVENT_VELODROME_GETAMOUNTOUT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE=1e9`) reproduction of Velodrome's quote
formulas. Real deltas versus the Solidity pool in this profile:

1. Storage (`reserve0/1`, `stable`, `factory.getFee`, `token0`, `decimals0/1`)
   becomes explicit function arguments. Caller already orients `reserveA/B`.
2. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit signed i64 the clone
   fail-closes to 0 instead of wrapping.
3. `_get_y` non-convergence, `dx=0`, and `fee>10000` fail-close to 0
   (Solidity reverts `!y`).

Named goldens (equal `1e9` reserves): volatile +10% fee 0 → **90909090**;
fee 5 → **90867766**; fee 30 (Uniswap-0.3% match) → **90661089**; stable +10%
fee 0 → **99950051**; fee 1 → **99940071**.

## What is not claimed

- Solidity **uint256** / **1e18** / token-decimals / Optimism or Base mainnet parity
- LIN replacing Velodrome, Aerodrome, Uniswap, or the EVM
- TVL or dollar savings
- Cubic `k` alone (already cloned as `clone-lin-solidly-k`)

Machine-written evidence for a given run is in `velo_getout_evidence.json`
(produced by the harness; do not hand-edit).
