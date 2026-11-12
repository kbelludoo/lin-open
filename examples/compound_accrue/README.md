# Compound CToken.accrueInterest — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2
`CToken.accrueInterest`. The LIN clone itself is `src/lin_compound_accrue.lin`
in lin-open. A separate clone-lin GitHub repository publishes the same `.lin`
source: **https://github.com/kbelludoo/clone-lin-compound-accrue**

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/CToken.sol` (BSD-3-Clause), commit `a3214f67b73310d547e00fc578e8355911c9d376`
- **Helpers:** `ExponentialNoError.mul_ScalarTruncate*` and `CTokenInterfaces.borrowRateMaxMantissa = 0.0005e16`
- **LIN clone (this tree):** `src/lin_compound_accrue.lin`
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-compound-accrue
- **C11 oracle:** `test/oracles/compound_accrue_c11.c`
- **Harness:** `python3 test/prove_compound_accrue_external.py`
- **Event receipt:** `docs/events/EVENT_COMPOUND_ACCRUE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound's per-block simple-interest
accrual. The real deltas versus the Solidity cToken in this profile are:

1. `getBlockNumber`, `interestRateModel.getBorrowRate`, and storage
   (`totalBorrows`, `borrowIndex`, `totalReserves`, `reserveFactorMantissa`)
   are function arguments, not hidden environment / contract storage.
2. `(a*b)/1e18` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit in uint64 the clone
   fail-closes to 0 instead of wrapping.
3. `borrowRateMantissa > 0.0005e16` fail-closes to 0 (Solidity 0.8 `require` reverts).
4. Same-block `current == prior` is a documented no-op (Solidity returns `NO_ERROR`
   without writing storage).

## What is not claimed

- Solidity **uint256** / mainnet **cToken** parity
- LIN replacing Compound, Uniswap, or the EVM
- TVL, dollar savings, or wall-clock superiority vs solc/LLVM
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `compound_accrue_evidence.json`
(produced by the harness; do not hand-edit).
