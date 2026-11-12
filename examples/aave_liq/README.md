# Aave V3 `_calculateAvailableCollateralToLiquidate` — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3
`LiquidationLogic._calculateAvailableCollateralToLiquidate` (collateral vs debt
pricing, close factor, liquidation bonus, protocol fee). The LIN copy also lives
in a separate repo.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `LiquidationLogic.sol` + `PercentageMath.sol`. Hash-pinned, **not vendored**. MIT after BUSL Change Date 2023-01-27.
- **LIN clone (this tree):** [`src/lin_aave_liq.lin`](../../src/lin_aave_liq.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-liq
- **C11 oracle:** `test/oracles/aave_liq_c11.c`
- **Harness:** `python3 test/prove_aave_liq_external.py` or `make aave-liq-proof`
- **Event receipt:** `docs/events/EVENT_AAVE_LIQ_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's liquidation available-collateral
kernel at **WAD' = 1e9** (mainnet health-factor threshold `0.95e18` fits i64 and
is recorded; the clone compares HF against `0.95e9`). Real deltas versus the
Solidity:

1. `oracle.getAssetPrice` / reserve configuration / `toUint128` become explicit
   price, unit, bonus and protocol-fee arguments.
2. `percentMul` / `percentDiv` use a 128-bit product with half-up addend.
   If the quotient does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. `collateralPrice = 0` (or zero units) fail-closes (Solidity divides by zero).

Named goldens: equal-price 5% bonus **1050000000**; 10% protocol fee of that
bonus **1045000000 / fee 5000000**; capped user balance `5e8` → debtNeeded
**476190476**; `percentMul(1, 0.5e4)` half-up **1** vs floor **0**; HF above
`0.95*WAD'` uses the 50% close factor.

## What is not claimed

- Solidity **uint256** / mainnet **WAD=1e18** / **oracle** / **aToken** parity
- LIN replacing Aave or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- Standalone `percentMul` clone (see clone-lin-aave-percent)

Machine-written evidence for a given run is in `aave_liq_evidence.json`
(produced by the harness; do not hand-edit).
