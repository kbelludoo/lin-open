# GMX V2 capPositiveImpactUsdByPositionImpactPool — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2
`capPositiveImpactUsdByPositionImpactPool` / `getMaxLendableUsdAvailable`.
The LIN sources live in lin-open; a full clone-lin copy is in a **separate**
repository.

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **Pinned commit:** `a85ea3491c19c93bb4b5a002d9b358fb769b7849`
- **LIN clone (this tree):** [`src/lin_gmx_v2_impact_pool.lin`](../../src/lin_gmx_v2_impact_pool.lin)
- **Separate clone-lin repo:** [https://github.com/kbelludoo/clone-lin-gmx-v2-impact-pool](https://github.com/kbelludoo/clone-lin-gmx-v2-impact-pool)
- **Pinned excerpts:** `test/fixtures/external_proof/CapPositiveImpactUsdByPositionImpactPool.excerpt.sol` and lendable / Precision siblings
- **C11 oracle:** `test/oracles/gmx_v2_impact_pool_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_impact_pool_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_IMPACT_POOL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's impact-pool plus lendable
positive price-impact cap (FLOAT' = 1e6). Real deltas versus the Solidity
kernel in this profile:

1. DataStore parameters are function arguments.
2. `(a*b)/d` uses a 128-bit product. Naive signed i64 `7e9*2e9/1e6` wraps.
3. Positive impact above the pool is lent up to `min(applyFactor(poolUsd, factor), config) - lent`.
4. The cap is **not** `applyFactor(sizeDelta, factor)` (that is `capPositiveImpactUsdByMaxPositionImpact`).
5. Config USD and already-lent USD both shrink headroom; over-lent returns 0.
6. Negative impact (`<= 0`) passes through.

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 **FLOAT=1e30** parity
- LIN replacing GMX, Uniswap, or the EVM
- A full port of `capPositiveImpactUsdByMaxPositionImpact` or `getCappedPnl`

Machine-written evidence for a given run is in `gmx_v2_impact_pool_evidence.json`
(produced by the harness; do not hand-edit).
