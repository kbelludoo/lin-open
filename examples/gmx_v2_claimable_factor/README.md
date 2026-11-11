# GMX V2 _getClaimableFactor — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`_getClaimableFactor` (and the `claimCollateral` applyFactor-minus-claimed
path). The LIN clone itself is `src/lin_gmx_v2_claimable_factor.lin` in
lin-open. A copy of the clone lives in a separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-claimable-factor](https://github.com/kbelludoo/clone-lin-gmx-v2-claimable-factor)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_claimable_factor.lin`](../../src/lin_gmx_v2_claimable_factor.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/GetClaimableFactor.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_claimable_factor_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_claimable_factor_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_CLAIMABLE_FACTOR_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **claimable-collateral
factor**: max of the time-key factor and the account factor, default to 100%
FLOAT only after `CLAIMABLE_COLLATERAL_DELAY` when both factors and the
reduction are zero, then subtract the reduction (floor at 0). The real deltas
versus the Solidity market in this profile are:

1. DataStore / `Chain.currentTimestamp` are function arguments, not hidden
   environment or contract storage.
2. FLOAT is **1e6**, not GMX `Precision.FLOAT_PRECISION` 1e30 (which does not
   fit signed i64).
3. `timeKey * divisor` overflow and `now - prod` underflow fail-close instead
   of wrapping or reverting with a host exception.
4. `claimCollateral` rejects `factor > FLOAT`, then pays
   `applyFactor(amount, factor) - claimed`.

Named goldens (uint64-scale, divisor=3600 delay=86400 timeKey=1000 unless
noted): max(time 4e5, account 6e5) → **600000** vs min **400000** vs time-only
**400000**; both-zero after delay+1 → **1000000** vs no-default **0** vs exact
delay **0** vs `>= delay` **1000000**; 8e5-3e5 → **500000** vs ignore
**800000** vs add **1100000**; over-reduction 3e5-5e5 → **0** vs signed
**-200000**; reduction blocks delay-default **0** vs default-then-reduce
**800000**; factor 2e6 **ok=0** vs cap **1000000**; now < timeKey*divisor
**ok=0**; 7e9*2e9 **ok=0** vs naive i64 wrap **-4446744073709551616**; amount
1e8 * 5e5 / 1e6 claimed 0 → **50000000**, claimed 1e7 → **40000000**,
claimed==adjusted **ok=0**; impact-pool rate*duration **500000** vs
delay-default **1000000**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity / FLOAT **1e30**
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is `applyDeltaToCollateralSum` (always-max unsigned sum) or a
  working i64 port of `getPendingPositionImpactPoolDistributionAmount`
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_claimable_factor_evidence.json` (produced by the harness; do not
hand-edit).
