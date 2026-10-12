# GMX V1 getFundingFee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`VaultUtils.getFundingFee`. The standalone LIN copy lives in a
separate clone-lin repository; lin-open keeps proofs, the kernel, and the
transpiler delta.

- **Upstream:** [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts) `contracts/core/VaultUtils.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_gmx_funding.lin`](../../src/lin_gmx_funding.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-funding
- **Pinned fixture:** `test/fixtures/external_proof/VaultUtils.sol`
- **C11 oracle:** `test/oracles/gmx_funding_c11.c`
- **Harness:** `python3 test/prove_gmx_funding_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_FUNDING_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V1 **perpetual funding**:
`size * (cumulativeFundingRate - entryFundingRate) / 1e6`. Class:
EXPERIMENTAL (real published algorithm, deliberately reduced operand width).

Real deltas versus the Solidity Vault in this profile:

1. `size` / `cumulative` / `entry` are explicit LIN arguments (no
   `vault.cumulativeFundingRates`, no position storage, no token address).
2. `(size * rate) / 1e6` uses a 128-bit product. Naive i64 wrap is named and rejected.
3. `entry > cumulative` fail-closes to 0 (Solidity 0.6 SafeMath.sub reverts).
4. Companion `getPositionFee` uses `/10000`. Confusing the two denominators
   is a named 100× overcharge.

Named commercial contrast on a 1e6 size / 1000 rate: **funding 1000** vs
**confused-bps 100000** (100×). Ignoring entry on cum=5000/entry=4000:
**1000** vs **5000** (5×). Uniswap 30 bps one-shot of the same notional is
**3000** — a swap fee, not accrued funding.

This is **not** a retread of GMX `getFeeBasisPoints` (USDG tax/rebate),
Uniswap V2 `xy`, Solidly `x³y+y³x`, Saddle/Curve `getD`/`getY`, or Maker `rpow`.

## What is not claimed

- Solidity **uint256** / mainnet GMX Vault or GLP parity
- LIN replacing GMX, GLP, or the EVM
- Wall-clock superiority vs solc
- That this clone is a production perps DEX

Machine-written evidence for a given run is in `gmx_funding_evidence.json`
(produced by the harness; do not hand-edit).
