# GMX V1 validateLiquidation — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`VaultUtils.validateLiquidation`. The standalone LIN copy lives in a
separate repository:

- **Clone-lin:** https://github.com/kbelludoo/clone-lin-gmx-liq
- **In-tree kernel (lin-open):** [`src/lin_gmx_liq.lin`](../../src/lin_gmx_liq.lin)

## Upstream

- Repo: [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts)
- File: `contracts/core/VaultUtils.sol` (MIT)
- Commit: `fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8`
- sha256: `ad831f3c8d675c42665c854368bc06696e1cba23bd3294f91aa2ce4c0a8fc495`
- git blob: `8e29c3ff19258d191f6d2459c110a917ba1f9906`
- Fixture: `test/fixtures/external_proof/VaultUtils.sol`

## What is claimed (EXPERIMENTAL, uint64-scale)

The published GMX V1 liquidation gate, with storage lifted to arguments:

1. Losses exceed collateral → state `1`, fees = `marginFees` (not remaining 0).
2. `remaining < marginFees` → state `1`, **fees capped to remaining** (not `marginFees`).
3. `remaining` in `[marginFees, marginFees+liquidationFeeUsd)` → state `1`, fees = `marginFees` (not remaining, not margin+liq).
4. `remaining * maxLeverage < size * 10000` → state `2` (max leverage), fees = `marginFees`.
5. Else healthy state `0`. Profits are added to remaining **only when `raise=0`** (liquidatePosition).

Named traps vs this kernel: no-cap 950 vs 900; include-liq 950 vs 900; raise=1 omits profit (state `-4` vs healthy `0`); naive i64 `4e9*3e9` false-flags leverage.

This is **not** `getNextFundingRate`, **not** `getFundingFee`, **not** `getFeeBasisPoints`.

## What is not claimed

- Solidity uint256 / mainnet Vault / GLP parity
- LIN replacing GMX keepers or the EVM
- Wall-clock superiority vs solc

## How to re-run

```
python3 test/prove_gmx_liq_external.py
```

Machine-written evidence: `gmx_liq_evidence.json` (do not hand-edit).
Event receipt: `docs/events/EVENT_GMX_LIQ_CLONE_LIN.rulel`.
