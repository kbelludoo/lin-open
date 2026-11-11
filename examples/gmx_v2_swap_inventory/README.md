# GMX V2 applyDeltaToVirtualInventoryForSwaps — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`applyDeltaToVirtualInventoryForSwaps`. The LIN clone itself is
`src/lin_gmx_v2_swap_inventory.lin` in lin-open. A copy of the clone lives in a
separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-swap-inventory](https://github.com/kbelludoo/clone-lin-gmx-v2-swap-inventory)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_swap_inventory.lin`](../../src/lin_gmx_v2_swap_inventory.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/ApplyDeltaToVirtualInventoryForSwaps.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_swap_inventory_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_swap_inventory_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_SWAP_INVENTORY_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **unsigned long-token /
short-token swap virtual inventory**. The real deltas versus the Solidity
market in this profile are:

1. DataStore / EventEmitter / market address are function arguments, not
   hidden contract storage.
2. Two unsigned inventories are tracked. Only the matching token side is
   updated (`isLongToken`). The sibling is left unchanged.
3. `applyBoundedDeltaToUint` floors a negative next uint at 0. Missing
   `virtualMarketId` returns `(false, 0)` **before** `getIsLongToken`, so an
   unexpected token does not revert on that path.
4. Unsigned i64 add of the selected inventory fail-closes instead of wrapping.

Named goldens (uint64-scale, long=1e8 short=5e7): long-token +3e7 → long
**130000000** / short **50000000** vs both-sides short **80000000** vs
position-style flip **70000000**; short-token +3e7 → short **80000000**;
long -1.5e8 **floors 0** vs reject-uint **ok=0** vs signed **-50000000**;
missing virtual market leaves the pair and returns nextValue **0**; unexpected
token with no virtual market **ok=1** vs token-first **ok=0**; 7e18+3e18
fail-closes vs naive i64 wrap **-8446744073709551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is `applyDeltaToVirtualInventoryForPositions` (signed single) or
  `applyDeltaToOpenInterest` (unsigned OI + signed long-flipped VI)
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_swap_inventory_evidence.json` (produced by the harness; do not
hand-edit).
