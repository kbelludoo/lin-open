# GMX V2 usdToMarketTokenAmount — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`usdToMarketTokenAmount` / `marketTokenAmountToUsd`. The LIN clone itself is
`src/lin_gmx_v2_market_token.lin` in lin-open. A copy of the clone lives in a
separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-market-token](https://github.com/kbelludoo/clone-lin-gmx-v2-market-token)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_market_token.lin`](../../src/lin_gmx_v2_market_token.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/UsdToMarketTokenAmount.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_market_token_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_market_token_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_MARKET_TOKEN_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **market-token mint**:
empty `supply` **and** empty `poolValue` uses `floatToWei(usd)`; empty supply
with leftover `poolValue` uses `floatToWei(pool+usd)` so the post-mint price
is 1 USD; otherwise floor `mulDiv(supply, usd, pool)`. Inverse
`marketTokenAmountToUsd` reverts `EmptyMarketTokenSupply`. The real deltas
versus the Solidity market in this profile are:

1. `usd`, `pool`, and `supply` are function arguments, not hidden DataStore.
2. DIV is **1e6**, not GMX `FLOAT_TO_WEI_DIVISOR` 1e12 / FLOAT 1e30.
3. Leftover `pool+usd` overflow, subsequent `supply*usd` overflow, empty-supply
   inverse, and `pool=0` with `supply>0` fail-close instead of wrapping.

Named goldens (uint64-scale, DIV'=1e6): first deposit **100** vs Lido/Rocket
1:1 **100000000**; leftover pool 2e7 **120** vs Lido **0** vs ignore-pool
**100** vs forgot-wei **120000000**; subsequent **25000000** vs always-wei
**50**; inverse **50000000** vs empty-supply 1:1 **100**; `supply>0 pool=0`
ok=0 vs Lido **50000000** vs OR-empty wei **50**; remainder 3*4/5 **2** vs
ceil **3**; dust **0**; leftover usd=0 **20**; 7e18+3e18 **ok=0** vs naive
wrap **-8446744073709551616**; 7e9*2e9 **ok=0** vs wrap
**-4446744073709551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity / FLOAT **1e30**
- LIN replacing GMX, Lido, Rocket Pool, or the EVM
- This kernel is Lido `getSharesByPooledEth`, Rocket `getRethValue`, a 1:1
  empty-pool mint, or `supply==0 || poolValue==0`
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_market_token_evidence.json` (produced by the harness; do not
hand-edit).
