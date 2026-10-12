# GMX V1 getNextFundingRate — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`Vault.getNextFundingRate`. The standalone LIN copy lives in a
separate clone-lin repository; lin-open keeps proofs, the kernel, and the
transpiler delta.

- **Upstream:** [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts) `contracts/core/Vault.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_gmx_nextrate.lin`](../../src/lin_gmx_nextrate.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-nextrate
- **Pinned fixture:** `test/fixtures/external_proof/Vault.sol`
- **C11 oracle:** `test/oracles/gmx_nextrate_c11.c`
- **Harness:** `python3 test/prove_gmx_nextrate_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_NEXTRATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V1 **time-sliced utilization
funding increment**:
`factor * reserved * intervals / poolAmount` with
`intervals = (now - last) / fundingInterval` (default 8 hours = 28800).
If `last + interval > now` the increment is 0. Class: EXPERIMENTAL
(real published algorithm, deliberately reduced operand width).

Real deltas versus the Solidity Vault in this profile:

1. `now` / `last` / `interval` / `reserved` / `pool` / `vol_factor` /
   `stable_factor` are explicit LIN arguments (no `block.timestamp`, no
   `lastFundingTimes` / `poolAmounts` / `reservedAmounts` storage).
2. `((factor * reserved) * intervals) / pool` uses a 128-bit product.
   Naive i64 wrap is named and rejected.
3. Uninitialized `last=0` is a named footgun (`getNextFundingRate` does
   **not** special-case last==0; `updateCumulativeFundingRate` does).
4. Companion `getUtilisation` is `reserved * 1e6 / pool`. Confusing the
   two is a named 10000× misread.

Named commercial contrast on a 50% reserved/pool, factor=100, 8h interval:

- 1 interval: nextRate **50**
- elapsed 20000 < 28800: **0** vs ignore-interval **50**
- 24h: intervals=3 rate **150** vs raw elapsed seconds **4320000** (28800×)
- stable factor=10: **5** vs volatile **50** (10×)
- `getUtilisation`: **500000** vs nextRate **50** (10000×)
- confused `getFundingFee` `reserved*factor/1e6`: **5000** vs **50** (100×)
- uninit last=0 at now=1700000000: **2951350** vs initialized **0**
- naive i64 `(4e9*3e9)/2e9` wraps to **-3223372036**; 128-bit = **6000000000**

This is **not** a retread of GMX `getFundingFee` (size × delta-rate / 1e6),
GMX `getFeeBasisPoints` (USDG tax/rebate), Uniswap V2 `xy`, Solidly
`x³y+y³x`, Saddle/Curve `getD`/`getY`, or Maker `rpow`.

## What is not claimed

- Solidity **uint256** / mainnet GMX Vault or GLP parity
- LIN replacing GMX, GLP, or the EVM
- Wall-clock superiority vs solc
- That this clone is a production perps DEX

Machine-written evidence for a given run is in `gmx_nextrate_evidence.json`
(produced by the harness; do not hand-edit).
