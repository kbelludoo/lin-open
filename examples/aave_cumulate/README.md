# Aave V3 `cumulateToLiquidityIndex` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`ReserveLogic.cumulateToLiquidityIndex` (flashloan premium folded into the
aToken liquidity index). The LIN copy also lives in a separate repo.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `ReserveLogic.sol` + `WadRayMath.sol`. Hash-pinned, **not vendored**. MIT after BUSL Change Date 2023-01-27.
- **LIN clone (this tree):** [`src/lin_aave_cumulate.lin`](../../src/lin_aave_cumulate.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-cumulate
- **C11 oracle:** `test/oracles/aave_cumulate_c11.c`
- **Harness:** `python3 test/prove_aave_cumulate_external.py` or `make aave-cumulate-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_CUMULATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's flashloan-premium-into-index
kernel at **RAY' = 1e9** (mainnet `RAY = 1e27` does not fit i64). Real deltas
versus the Solidity:

1. `reserve.liquidityIndex` storage write / `toUint128` become an explicit
   `index` argument and a returned next index.
2. `wadToRay` / `rayDiv` / `rayMul` use a 128-bit product with half-up addend.
   If the quotient does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. `totalLiquidity = 0` fail-closes (Solidity `rayDiv` by zero reverts).

Named goldens: identity `amount=0` leaves index `1e9`; 0.1% premium **1001000000**;
typical 0.09% Aave flashloan premium **1000900000**; `rayMul(1, 5e8)` half-up **1**
vs floor **0**.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / **aToken** parity
- LIN replacing Aave or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- Standalone `rayMul` / `wadToRay` clones (see clone-lin-aave-raymul / clone-lin-aave-raytowad)

Machine-written evidence for a given run is in `aave_cumulate_evidence.json`
(produced by the harness; do not hand-edit).
