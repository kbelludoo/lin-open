# Aave V3 `calculateAvailableBorrows` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`GenericLogic.calculateAvailableBorrows` (remaining borrow capacity) plus the
`ValidationLogic` isolation-mode debt-ceiling check. The LIN copy also lives
in a separate repo.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `GenericLogic.sol` + `PercentageMath.sol` + `ValidationLogic.sol`. Hash-pinned, **not vendored**. MIT after BUSL Change Date 2023-01-27.
- **LIN clone (this tree):** [`src/lin_aave_borrows.lin`](../../src/lin_aave_borrows.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-borrows
- **C11 oracle:** `test/oracles/aave_borrows_c11.c`
- **Harness:** `python3 test/prove_aave_borrows_external.py` or `make aave-borrows-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_BORROWS_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's available-borrows kernel at
**PERCENTAGE_FACTOR = 1e4** (same bps as Aave). Real deltas versus the Solidity:

1. `calculateUserAccountData` / `oracle.getAssetPrice` become explicit
   collateral, debt, LTV and isolation current/ceiling arguments.
2. `percentMul` uses a 128-bit product with half-up addend. If the quotient
   does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. Underwater accounts (`percentMul(collateral, ltv) < debt`) return 0
   (Solidity unsigned sub would revert in 0.8).
4. Isolation units are `amount / 10**(decimals-2)`; `decimals < 2` fail-closes.

Named goldens: 80% LTV on `1e9` collateral with `1e8` debt → **700000000**;
underwater `1000/900` → **0**; USDC 6-dec `1e6` → **100** isolation units;
`percentMul(1, 0.5e4)` half-up **1** vs floor **0**.

## What is not claimed

- Solidity **uint256** / mainnet **WAD=1e18** / **oracle** / **aToken** parity
- LIN replacing Aave or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- Standalone `percentMul` clone (see clone-lin-aave-percent)
- Full `calculateUserAccountData` (oracle loop; fail-closed in the transpiler)

Machine-written evidence for a given run is in `aave_borrows_evidence.json`
(produced by the harness; do not hand-edit).
