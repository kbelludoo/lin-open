# GMX V2 capPositiveImpactUsdByMaxPositionImpact — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2
`capPositiveImpactUsdByMaxPositionImpact`. The LIN sources live in lin-open; a full
clone-lin copy is in a **separate** repository.

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **Pinned commit:** `a85ea3491c19c93bb4b5a002d9b358fb769b7849`
- **LIN clone (this tree):** [`src/lin_gmx_v2_pos_impact.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-4ebc/src/lin_gmx_v2_pos_impact.lin)
- **Separate clone-lin repo:** [https://github.com/kbelludoo/clone-lin-gmx-v2-pos-impact](https://github.com/kbelludoo/clone-lin-gmx-v2-pos-impact)
- **Pinned excerpts:** `test/fixtures/external_proof/CapPositiveImpactUsdByMaxPositionImpact.excerpt.sol` and factors / Precision siblings
- **C11 oracle:** `test/oracles/gmx_v2_pos_impact_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_pos_impact_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_POS_IMPACT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's one-sided positive
price-impact cap (FLOAT' = 1e6). Real deltas versus the Solidity kernel in
this profile:

1. DataStore parameters are function arguments.
2. `(a*b)/d` uses a 128-bit product. Naive signed i64 `7e9*2e9/1e6` wraps.
3. Negative impact passes through. A symmetric abs cap would clip `-2e8` to `-1e8`.
4. The cap is `applyFactor(sizeDelta, factor)`, not `applyFactor(pool, maxPnlFactor)`.
5. Stored positive factor is clamped down to the negative factor before apply.
6. Factor 0 clips a positive rebate to 0 (not a "no-cap / trader stays" path).

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 **FLOAT=1e30** parity
- LIN replacing GMX, Uniswap, or the EVM
- A full port of `getCappedPnl` or `capPositiveImpactUsdByPositionImpactPool`

Machine-written evidence for a given run is in `gmx_v2_pos_impact_evidence.json`
(produced by the harness; do not hand-edit).
