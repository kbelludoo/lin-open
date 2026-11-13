# Sky sUSDS convertToAssets — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Sky Protocol
`SUsds.convertToAssets` / `convertToShares` — ERC-4626 share conversion against
the savings-rate accumulator `chi` (`assets = shares * chi / RAY`).

**Clone-LIN (standalone LIN copy):** https://github.com/kbelludoo/clone-lin-sky-susds

- **Upstream (hash-pinned, not vendored):** [sky-ecosystem/sdai](https://github.com/sky-ecosystem/sdai) `dfc7f41cb7599afcb0f0eb1ddaadbf9dd4015dce` branch `susds`
  - `src/SUsds.sol` sha256 `9fe0c713751142e75a1da60ad6c0127d5ad01cb6d24289183ac48b202f3c5d69` blob `efe937675bbbbc7f93bde453fd5648fa885655ab`
  - License AGPL-3.0-or-later. lin-open does **not** vendor the Solidity source.
- **LIN kernel (harness copy):** [`src/lin_sky_susds.lin`](../../src/lin_sky_susds.lin)
- **C11 oracle:** `test/oracles/sky_susds_c11.c`
- **Transpilable kernel:** `test/oracles/sky_susds_kernel.c`
- **Harness:** `python3 test/prove_sky_susds_external.py` / `make sky-susds-proof`
- **Event receipt:** `docs/events/EVENT_SKY_SUSDS_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256 ray. Not a production sUSDS.

## Named goldens

- PAR `chi=1000` (1.0 RAY) shares=500 → assets **500**
- ACCRUED `chi=1100` shares=1000 → assets **1100**; assets=1100 → shares **1000**
- FLOOR remainder: 1 share → **1** asset; 1 asset → **0** shares
- CEIL `previewMint(1)` → **2** assets; `previewWithdraw(1)` → **1** share
- ROUNDTRIP `100` assets → 90 shares → 99 assets (loss **1**)
- `chi=0` fail-closes to **0**
- convertTo* are **not** wards-auth; `_rpow` / `block.timestamp` / OZ offset are **absent**
- OVERFLOW `7e9*3e9` checked mul **0**; naive i64 wraps to `2553255926290448384`

## What is not claimed

Uint256 ray / mainnet sUSDS / drip `_rpow` parity.
LIN replacing Sky, Maker, sUSDS, or the EVM.
TVL or dollar savings. zk soundness. OZ ERC-4626 virtual shares. `pot.drip`.
