# GMX V2 getUsageFactor — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`getUsageFactor`. The LIN clone itself is `src/lin_gmx_v2_usage_factor.lin` in
lin-open. A copy of the clone lives in a separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-usage-factor](https://github.com/kbelludoo/clone-lin-gmx-v2-usage-factor)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_usage_factor.lin`](../../src/lin_gmx_v2_usage_factor.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/GetUsageFactor.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_usage_factor_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_usage_factor_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_USAGE_FACTOR_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **usage factor**:
`toFactor(reservedUsd, applyFactor(poolUsd, reserveFactor))`.
`isLong` selects the `openInterestReserveFactor` storage key; it does not
flip the math. The real deltas versus the Solidity market in this profile
are:

1. `reserved`, `pool`, and `reserveFactor` are function arguments, not
   hidden DataStore / market storage.
2. FLOAT is **1e6**, not GMX `FLOAT_PRECISION` 1e30.
3. `pool * reserveFactor` overflow, `reserved * FLOAT` overflow, and
   `maxReserved == 0` with `reserved > 0` fail-close instead of wrapping
   or reverting with a host exception.

Named goldens (uint64-scale, FLOAT'=1e6): reserved 4e7 pool 1e8
reserveFactor 5e5 (50% cap) usage **800000** vs reserved/pool **400000** vs
Compound-style reserved/(pool+reserved) **285714** vs applyFactor-only
**50000000** vs fused FLOAT^2 at this scale **ok=0**; remainder vector
reserved 400 pool 1001 factor 5e5 nested **800000** vs fused **799200**;
dust 1/3 floor **333333** vs ceil **333334**; reserved=0 even with
maxReserved=0 **0/ok=1**; reserved>0 maxReserved=0 **ok=0**; over-reserve
6e7/5e7 **1200000** vs cap-at-FLOAT **1000000**; full max **1000000**;
getBorrowingFees applyFactor trap **50000000**; 7e9*2e9 **ok=0** vs naive
i64 wrap **-4446744073709551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity / FLOAT **1e30**
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is reserved/pool utilization, Compound `utilizationRate`,
  fused `reserved*FLOAT^2/(pool*factor)`, or `getBorrowingFees`
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_usage_factor_evidence.json` (produced by the harness; do not
hand-edit).
