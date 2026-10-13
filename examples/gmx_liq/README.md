# GMX V1 validateLiquidation — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`VaultUtils.validateLiquidation`. The standalone LIN copy lives in
[clone-lin-gmx-liq](https://github.com/kbelludoo/clone-lin-gmx-liq).

- **Upstream:** [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts) `contracts/core/VaultUtils.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_gmx_liq.lin`](../../src/lin_gmx_liq.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-gmx-liq
- **Pinned fixture:** `test/fixtures/external_proof/VaultUtils.sol`
- **C11 oracle:** `test/oracles/gmx_liq_c11.c`
- **Harness:** `python3 test/prove_gmx_liq_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_LIQ_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V1 remaining-collateral
liquidation. The real deltas versus the Solidity view in this profile are:

1. Vault storage (`getPosition`, `getDelta`, `getFundingFee`, `getPositionFee`,
   `liquidationFeeUsd`, `maxLeverage`) is function arguments, not hidden
   contract reads.
2. `remaining * maxLeverage < size * 10000` uses a 128-bit product compare
   (schoolbook limbs in LIN, `__int128` in the C11 oracle). Naive i64 multiply
   wraps `4e9*3e9` and falsely flags max-leverage.
3. When remaining collateral is below computed `marginFees`, collected fees
   cap to remaining (80000) instead of the computed 90000.

## What is not claimed

- Solidity **uint256** / mainnet **GMX Vault / GLP** parity
- LIN replacing GMX, Uniswap, or the EVM
- A retread of `getFundingFee`, `getNextFundingRate`, or `getFeeBasisPoints`
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `gmx_liq_evidence.json`
(produced by the harness; do not hand-edit).
