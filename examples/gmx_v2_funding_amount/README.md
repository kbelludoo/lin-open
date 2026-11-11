# GMX V2 getFundingAmount — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2's
`getFundingAmount` (and the `getFundingFees` round-up charge / round-down
claim path). The LIN clone itself is `src/lin_gmx_v2_funding_amount.lin` in
lin-open. A copy of the clone lives in a separate repository:

- **Clone-lin repo:** [kbelludoo/clone-lin-gmx-v2-funding-amount](https://github.com/kbelludoo/clone-lin-gmx-v2-funding-amount)
- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **LIN clone (this tree):** [`src/lin_gmx_v2_funding_amount.lin`](../../src/lin_gmx_v2_funding_amount.lin)
- **Pinned excerpts:** `test/fixtures/external_proof/GetFundingAmount.excerpt.sol`
- **C11 oracle:** `test/oracles/gmx_v2_funding_amount_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_funding_amount_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_FUNDING_AMOUNT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2's **funding amount**:
`mulDiv(size, latest - entry, FLOAT * FLOAT_SQRT, roundUpMagnitude)`.
`getFundingFees` charges with `roundUpMagnitude = true` so a trader cannot
dodge dust by updating the position before the fee is chargeable, and claims
with `roundUpMagnitude = false`. The real deltas versus the Solidity market
in this profile are:

1. `latest`, `entry`, `size`, and `round_up` are function arguments, not
   hidden position / DataStore storage.
2. FLOAT is **1e6** and SQRT is **1e3** (denom **1e9**), not GMX
   `FLOAT_PRECISION` 1e30 times `FLOAT_PRECISION_SQRT` 1e15.
3. `latest < entry` underflow and `size * diff` overflow fail-close instead
   of wrapping or reverting with a host exception.

Named goldens (uint64-scale): size 1e8 latest 5000123 entry 4000000 charges
**100013** vs claims **100012** vs V1/applyFactor (no SQRT) **100012300** vs
always-floor charge **100012** vs always-ceil claim **100013**; dust size 100
charges **1** vs claim **0**; remainder 0 yields **100000** both ways;
latest==entry **0**; latest < entry **ok=0** vs signed **-1000000**; 7e9*2e9
**ok=0** vs naive i64 wrap **-4446744073709551616**; inverse per-size-delta
100012*1e9/1e8 **1000120**.

## What is not claimed

- Solidity **uint256** / Arbitrum **GMX V2** mainnet parity / FLOAT **1e30**
- LIN replacing GMX, Uniswap, or the EVM
- This kernel is GMX V1 `getFundingFee` (no SQRT) or
  `getFundingAmountPerSizeDelta` (inverse mulDiv)
- Wall-clock superiority vs solc/EVM

Machine-written evidence for a given run is in
`gmx_v2_funding_amount_evidence.json` (produced by the harness; do not
hand-edit).
