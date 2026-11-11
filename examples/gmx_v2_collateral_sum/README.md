# GMX V2 applyDeltaToCollateralSum — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`applyDeltaToCollateralSum`. The LIN clone itself is
`src/lin_gmx_v2_collateral_sum.lin` in lin-open. A copy of the clone lives in a
separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-collateral-sum](https://github.com/kbelludoo/clone-lin-gmx-v2-collateral-sum)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_collateral_sum.lin`](../../src/lin_gmx_v2_collateral_sum.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/ApplyDeltaToCollateralSum.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_collateral_sum_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_collateral_sum_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_COLLATERAL_SUM_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **unsigned collateral sum
with always-on max**. The real deltas versus the Solidity market in this
profile are:

1. DataStore / EventEmitter / market / collateralToken are function arguments,
   not hidden contract storage.
2. `applyDeltaToUint` rejects a negative next uint. `maxCollateralSum` is
   checked **always** after the update, including on decrease (OI checks max
   only when `delta > 0`).
3. `indexToken == 0` still updates collateral. OI would revert
   `OpenInterestCannotBeUpdatedForSwapOnlyMarket`.
4. `getCollateralSum` divides by `divisor`. This kernel returns the undivided
   next uint.
5. Unsigned i64 add of the sum fail-closes instead of wrapping.

Named goldens (uint64-scale, sum=1e8 max=2e8 unless noted): long +3e7 →
**130000000** (short side is the same; `isLong` is a key, not a sign flip) vs
position-style flip **70000000**; 1e8+3e7 vs max 1.2e8 **ok=0** vs no-max
**130000000**; decrease 1.5e8-2e7 still over max 1.2e8 **ok=0** vs OI-style
max-on-inc **130000000**; 1e8-1.5e8 **ok=0** vs bounded floor **0/ok=1** vs
signed **-50000000**; max=0 disables any positive next; swap-only index=0
**ok=1** vs OI reject **ok=0**; getter /2 **65000000**; 7e18+3e18 fail-closes vs
naive i64 wrap **-8446744073709551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is `applyDeltaToOpenInterest` (max-on-increase + swap-only +
  signed VI) or `applyDeltaToVirtualInventoryForSwaps` (unsigned pair, floor)
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_collateral_sum_evidence.json` (produced by the harness; do not
hand-edit).
