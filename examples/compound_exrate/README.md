# Compound V2 `exchangeRateStoredInternal` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2
`CToken.exchangeRateStoredInternal` (cToken share price). The LIN copy also
lives in a separate repo.

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `CToken.sol` + `ExponentialNoError.sol`. Hash-pinned, **not vendored**. BSD-3-Clause.
- **LIN clone (this tree):** [`src/lin_compound_exrate.lin`](../../src/lin_compound_exrate.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-compound-xrate
- **C11 oracle:** `test/oracles/compound_exrate_c11.c`
- **Harness:** `python3 test/prove_compound_exrate_external.py` or `make compound-exrate-proof`
- **Event receipt:** `docs/events/EVENT_COMPOUND_EXRATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound's cToken exchange-rate
kernel at **SCALE = 1e9**. Real deltas versus the Solidity:

1. Storage `getCashPrior` / `totalBorrows` / `totalReserves` / `totalSupply` /
   `initialExchangeRateMantissa` / hidden `expScale` become explicit arguments.
2. `(cash + borrows - reserves) * scale / supply` uses a 128-bit product. If
   the quotient does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. `cash + borrows < reserves` fail-closes to 0 (Solidity 0.8 reverts).
4. Zero `totalSupply` returns the explicit initial rate (Compound's typical
   0.02 mantissa → 2e7 at SCALE=1e9). The Solidity transpiler now expands
   `0.02e18` and fail-closes `getCashPrior` / `.balanceOf(` / `address(this).balance`.

Named goldens: par-one `1e9` → **1000000000**; 10% borrows → **1100000000**;
10% reserves → **900000000**; zero supply → **20000000**; underflow → **0**.

## What is not claimed

- Solidity **uint256** / mainnet **expScale=1e18** / live cToken parity
- LIN replacing Compound or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `getCashPrior` ERC-20/ETH balance reads (fail-closed in the transpiler)
- `accrueInterest` (see clone-lin-compound-accrue)

Machine-written evidence for a given run is in `compound_exrate_evidence.json`
(produced by the harness; do not hand-edit).
