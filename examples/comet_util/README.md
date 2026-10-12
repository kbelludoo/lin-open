# Compound III getUtilization — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III
`getUtilization`. The LIN clone itself is `src/lin_comet_util.lin` in lin-open.
A full copy lives in a separate clone-lin repository.

- **Upstream:** [compound-finance/comet](https://github.com/compound-finance/comet) `contracts/CometWithExtendedAssetList.sol` `getUtilization` (GPL-2.0-or-later after BUSL-1.1 Change Date 2025-12-31)
- **LIN clone (this tree):** [`src/lin_comet_util.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-c607/src/lin_comet_util.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-comet-util
- **Pinned excerpt:** `test/fixtures/external_proof/CometGetUtilization.excerpt.sol`
- **C11 oracle:** `test/oracles/comet_util_c11.c`
- **Harness:** `python3 test/prove_comet_util_external.py`
- **Event receipt:** `docs/events/EVENT_COMET_UTIL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound III's present-value
utilization wrap:

`utilization = totalBorrow_pv * FACTOR_SCALE / totalSupply_pv` with `FACTOR_SCALE=1e18`

The real deltas versus the Solidity view in this profile are:

1. Hidden storage (`baseSupplyIndex`, `totalSupplyBase`, `presentValueSupply`)
   is not read. Present-value totals are function arguments.
2. `(borrow * 1e18) / supply` uses a 128-bit product. If the quotient does
   not fit in uint64 the clone fail-closes to 0 instead of wrapping.
3. Empty supply fail-closes to 0 (Solidity takes the `if (totalSupply_ == 0)`
   branch and never divides).
4. Two-step `floor(borrow / supply) * 1e18` is a named rejected path: at 50%
   utilization it yields 0, while the Comet wrap yields `5e17`.
5. Named contrast vs Compound V2 JumpRate `utilizationRate(cash, borrows, reserves)`:
   the same `1e18, 1e18` numbers are **50% in V2** (cash+borrows denom) and
   **100% in III** (present-value totals). Feeding V2 cash as III supply_pv
   doubles the IRM input.

## What is not claimed

- Solidity **uint256** / mainnet **Comet USDC market** parity
- `presentValue` / `principalValue` / `accruedInterestIndices` (other kernels)
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM
- A TVL or production-IRM claim

Machine-written evidence for a given run is in `comet_util_evidence.json`
(produced by the harness; do not hand-edit).
