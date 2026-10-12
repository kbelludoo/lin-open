# Aave V3 health factor — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Aave V3's
`percentMul` + `wadDiv` health-factor formula. The LIN clone itself lives in
a separate repository.

- **Upstream:** [aave/aave-v3-core](https://github.com/aave/aave-v3-core) `v1.19.4`
  (`GenericLogic.sol`, `PercentageMath.sol`, `WadRayMath.sol`)
- **License:** MIT (upstream BUSL-1.1 Change Date 2023-01-27 elapsed)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-aave-health
- **LIN clone (results pointer in this tree):** [`src/lin_aave_health.lin`](../../src/lin_aave_health.lin)
- **Pinned fixtures:** `test/fixtures/external_proof/{AaveHealth.excerpt.sol,PercentageMath.sol,WadRayMath.sol,GenericLogic.sol}`
- **C11 oracle:** `test/oracles/aave_health_c11.c`
- **Harness:** `python3 test/prove_aave_health_external.py`
- **Event receipt:** `docs/events/EVENT_AAVE_HEALTH_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Aave's health factor:

`HF = percentMul(collateral, avgLT).wadDiv(debt)` with `WAD=1e18`,
`PERCENTAGE_FACTOR=1e4`, half-up rounding. Liquidatable iff `HF < 1e18`.

Deltas versus the Solidity path in this profile:

1. Storage/oracle walk (`getAssetPrice`, reserve mappings) is lifted to
   explicit `coll`, `lt`, `debt` arguments.
2. `(a*b + half)/d` uses a 128-bit product. Quotient overflow fail-closes to 0.
3. `debt==0` fail-closes to 0 (`ahf_no_debt=1`); Aave returns `uint256.max`.
4. Skip-LT `wadDiv(coll, debt)` and Liquity-style ICR (no liquidation
   threshold) are named rejected paths: coll=10000 debt=8500 LT=80% is
   **liquidatable** on Aave (HF ≈ 0.941e18) and **falsely healthy** if LT is
   skipped (≈ 1.176e18).

## What is not claimed

- Solidity **uint256** / mainnet Aave pool parity
- `rayMul` / `rayDiv` (`RAY=1e27` exceeds signed i64 and is rejected)
- LIN replacing Aave, Liquity, Compound, or the EVM
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `aave_health_evidence.json`
(produced by the harness; do not hand-edit).
