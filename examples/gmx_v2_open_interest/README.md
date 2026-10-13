# GMX V2 applyDeltaToOpenInterest — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`applyDeltaToOpenInterest`. The LIN clone itself is
`src/lin_gmx_v2_open_interest.lin` in lin-open. A copy of the clone lives in a
separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-open-interest](https://github.com/kbelludoo/clone-lin-gmx-v2-open-interest)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_open_interest.lin`](../../src/lin_gmx_v2_open_interest.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/ApplyDeltaToOpenInterest.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_open_interest_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_open_interest_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_OPEN_INTEREST_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's unsigned open-interest
update paired with signed virtual inventory. The real deltas versus the
Solidity market in this profile are:

1. DataStore / EventEmitter / market address are function arguments, not
   hidden contract storage.
2. Unsigned OI rejects a next value below zero (`applyDeltaToUint`). Virtual
   inventory is signed (`applyDeltaToInt`) and **long-flipped** (`isLong ?
   -delta : delta`). The USD path skips VI when `useOpenInterestInTokens` is
   set.
3. Signed i64 add of VI and unsigned add of OI fail-close instead of wrapping.

Named goldens (uint64-scale, oi=1e8 vi=5e7): long +3e7 → oi **130000000** / vi
**20000000** vs no-flip **80000000**; short +3e7 → vi **80000000** vs
always-flip **20000000**; neg OI -1.5e8 **rejects** vs naive **-50000000** vs
bounded floor **0**; tokens flag leaves vi **50000000** vs tokens-sibling
**20000000**; long +5e7 on vi 2e7 is signed **-30000000** vs unsigned floor
**0**; 7e18+3e18 fail-closes vs naive i64 wrap **-8446744073709551616**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is `applyDeltaToPositionImpactPool` (pool/lent) or
  `applyDeltaToOpenInterestInTokens` (tokens VI, inverse flag)
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_open_interest_evidence.json` (produced by the harness; do not
hand-edit).
