# Compound liquidateCalculateSeizeTokens — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2
liquidation seize-token math. The LIN kernel lives at
`src/lin_compound_seize.lin` in lin-open. The full clone-lin copy is a
separate public repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-compound-seize
- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol)
  `contracts/Comptroller.sol` (`liquidateCalculateSeizeTokens`) +
  `contracts/ExponentialNoError.sol` (BSD-3-Clause), commit
  `a3214f67b73310d547e00fc578e8355911c9d376`
- **Pinned fixtures:** `test/fixtures/external_proof/ExponentialNoError.sol`
  and `test/fixtures/external_proof/Comptroller_liquidateCalculateSeizeTokens.sol`
- **C11 oracle:** `test/oracles/compound_seize_c11.c`
- **Harness:** `python3 test/prove_compound_seize_external.py` or
  `make compound-seize-proof`
- **Event receipt:** `docs/events/EVENT_COMPOUND_SEIZE_CLONE_LIN.rulel`

## Formula (Compound Exp truncation order)

```
num_m   = (incentive * priceBorrowed) / 1e18
den_m   = (priceCollateral * exchangeRate) / 1e18
ratio_m = (num_m * 1e18) / den_m
seize   = (ratio_m * actualRepayAmount) / 1e18
```

Zero oracle price fail-closes to 0 (Compound returns `PRICE_ERROR` and 0 tokens).

Canonical uint64-scale vector: repay=1000, incentive=1.08e18 (8% bonus),
equal prices 1e18, exchangeRate=0.2e18 → **5400** collateral cTokens.

## What is claimed

Experimental, uint64-scale reproduction of Compound's liquidation seize math.
Real deltas versus the Solidity Comptroller in this profile:

1. Oracle prices, `exchangeRateStored` and `liquidationIncentiveMantissa` are
   function arguments, not hidden contract storage / `oracle.getUnderlyingPrice`.
2. Exp `mul_` / `div_` / `mul_ScalarTruncate` uses a 128-bit product
   (schoolbook limbs in LIN, `__int128` in the C11 oracle). If the quotient
   does not fit in uint64 the clone fail-closes to 0 instead of wrapping.

## What is not claimed

- Solidity **uint256** / mainnet **cToken** / Chainlink oracle parity
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `compound_seize_evidence.json`
(produced by the harness; do not hand-edit).
