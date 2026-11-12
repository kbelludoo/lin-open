# Aave V3 variable IRM — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3's
`DefaultReserveInterestRateStrategy` variable-rate kernel. The LIN copy of the
algorithm also lives in a separate clone-lin repository.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `contracts/protocol/pool/DefaultReserveInterestRateStrategy.sol` (MIT after BUSL-1.1 Change Date 2023-01-27). Solidity is **not vendored**.
- **LIN clone (this tree):** [`src/lin_aave_irm.lin`](../../src/lin_aave_irm.lin)
- **clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-irm
- **C11 oracle:** `test/oracles/aave_irm_c11.c`
- **Harness:** `python3 test/prove_aave_irm_external.py` or `make aave-irm-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_IRM_CLONE_LIN.rulel`

## What is claimed

Experimental, RAY'=1e9 reproduction of Aave's two-slope variable borrow rate
and the liquidity rate after reserve factor. Real deltas versus the Solidity
IRM in this profile:

1. `IERC20(reserve).balanceOf(aToken) + liquidityAdded - liquidityTaken` is an
   explicit `availableLiquidity` argument (no hidden ERC-20 state).
2. Immutable slopes / optimal usage / base rate are function arguments.
3. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle) with unsigned half-up remainder. If the quotient does not
   fit in uint64 the clone fail-closes to 0 instead of wrapping.

Named goldens (RAY'=1e9, optimal=0.8e9, slope1=0.04e9, slope2=0.8e9, rf=15%):

| Input | Result |
|---|---|
| `rayMul(1, 5e8)` | **1** vs floor **0** |
| `rayDiv(2, 3)` | **666666667** vs floor **666666666** |
| variable rate at 50% util | **25000000** |
| variable rate at 80% util (kink) | **40000000** |
| variable rate at 90% util | **440000000** |
| liquidity rate at 50% util, rf=15% | **10625000** |

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / aToken parity
- Stable-rate branch (deprecated in Aave V3.2)
- LIN replacing Aave, Uniswap, or the EVM
- General superiority vs solc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `aave_irm_evidence.json`
(produced by the harness; do not hand-edit).
