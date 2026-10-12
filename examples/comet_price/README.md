# Compound III mulPrice / divPrice — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III
`mulPrice` / `divPrice` (Chainlink 8-dec `PRICE_SCALE`). The LIN clone itself
is `src/lin_comet_price.lin` in lin-open. The standalone copy lives at:

**https://github.com/kbelludoo/clone-lin-comet-price**

- **Upstream:** [compound-finance/comet](https://github.com/compound-finance/comet) `contracts/CometWithExtendedAssetList.sol` + `CometCore.sol` (GPL-2.0-or-later after BUSL Change Date 2025-12-31)
- **LIN clone (this tree):** [`src/lin_comet_price.lin`](../../src/lin_comet_price.lin)
- **Pinned excerpt:** `test/fixtures/external_proof/CometPriceScale.excerpt.sol`
- **C11 oracle:** `test/oracles/comet_price_c11.c`
- **Harness:** `python3 test/prove_comet_price_external.py`
- **Event receipt:** `docs/events/EVENT_COMET_PRICE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Comet's common-price wrap used by
`isBorrowCollateralized` / `isLiquidatable` / `absorbInternal`. Real deltas:

1. `getPrice`, `baseScale`, and `asset.scale` are function arguments, not
   hidden storage / PriceFeed calls.
2. `(n * price) / fromScale` uses a 128-bit product. Quotients that do not
   fit uint64 fail-close to 0. `price == 0` fail-closes 0 (Solidity 0.8 reverts).
3. Named rejected paths: FACTOR_SCALE as price (~1e10× on 1 USDC@$1),
   BASE_INDEX_SCALE as price (~1e7×), `mulFactor` as `mulPrice` (floors to 0),
   reorder `(n/fromScale)*price` (0 vs 3 on `(3,5,4)`), skip-CF (false ok on
   a 50% CF underwater account), `divPrice` with `toScale=PRICE_SCALE` (100×
   USDC payout). WBTC 8-dec hides `PRICE_SCALE` vs `asset.scale`.

## What is not claimed

- Solidity **uint256** / mainnet Comet market / Chainlink feed parity
- getUtilization / presentValue / tracking-index / accruedInterestIndices
  (other clone-lin repos)
- LIN replacing Compound, Uniswap, or the EVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `comet_price_evidence.json`
(produced by the harness; do not hand-edit).
