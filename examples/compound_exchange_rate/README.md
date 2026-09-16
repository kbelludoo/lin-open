# Compound CToken exchangeRateStoredInternal — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2's
cToken exchange rate. The LIN clone itself is `src/lin_compound_exchange_rate.lin`.

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/CToken.sol` `exchangeRateStoredInternal` (BSD-3-Clause)
- **LIN clone (this tree):** [`src/lin_compound_exchange_rate.lin`](../../src/lin_compound_exchange_rate.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-compound-exrate
- **Pinned excerpt:** `test/fixtures/external_proof/CToken_exchangeRateStoredInternal.sol` (exact substring of pinned `CToken.sol`)
- **C11 oracle:** `test/oracles/compound_exchange_rate_c11.c`
- **Harness:** `python3 test/prove_compound_exchange_rate_external.py`
- **Event receipt:** `docs/events/EVENT_COMPOUND_EXCHANGE_RATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound's stored exchange rate:

```
if totalSupply == 0:
    rate = initialExchangeRateMantissa
else:
    rate = (getCashPrior() + totalBorrows - totalReserves) * 1e18 / totalSupply
```

Real deltas versus the Solidity cToken in this profile:

1. Storage / `getCashPrior()` become function arguments.
2. `(underlying * 1e18) / supply` uses a 128-bit product. If the quotient does
   not fit uint64 the clone fail-closes to 0 instead of wrapping.
3. `cash + borrows - reserves` underflow (Solidity 0.8 revert) fail-closes to
   rate 0 with `cer_ok = 0`. Empty supply is `cer_ok = 1`.

Canonical vectors (recomputable):

| cash | borrows | reserves | supply | initial | rate |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 2e17 | 2e17 |
| 1000 | 0 | 0 | 1000 | 2e17 | 1e18 |
| 1000 | 1000 | 0 | 1000 | 2e17 | 2e18 |
| 1 | 1 | 3 | 1 | 2e17 | 0 (`cer_ok=0`) |

## What is not claimed

- Solidity **uint256** / mainnet **cToken** parity (some Compound initial rates
  such as `2e26` do not fit uint64)
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in
`compound_exchange_rate_evidence.json` (produced by the harness; do not hand-edit).
