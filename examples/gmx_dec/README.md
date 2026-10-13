# GMX V1 adjustForDecimals / tokenToUsdMin — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V1
`Vault.adjustForDecimals` and companion `tokenToUsdMin`. The standalone
LIN copy lives in a separate repository:

- **Clone-lin:** https://github.com/kbelludoo/clone-lin-gmx-dec
- **In-tree kernel (lin-open):** [`src/lin_gmx_dec.lin`](../../src/lin_gmx_dec.lin)

## Upstream

- Repo: [gmx-io/gmx-contracts](https://github.com/gmx-io/gmx-contracts)
- File: `contracts/core/Vault.sol` (MIT)
- Commit: `fe55c4ba8911ae2378b50bfb9bece5ee50cf2af8`
- sha256: `0b49e265fc4c04d3eea74b07d698748050671a2df259f1faa8d05cabf2970f92`
- git blob: `4aef3c7dcf40b4657e7dfcef582958dc2d418126`
- Fixture: `test/fixtures/external_proof/Vault.sol`

## What is claimed (EXPERIMENTAL, uint64-scale)

The published GMX V1 decimals-normalize muldiv, with storage lifted to arguments:

1. `adjustForDecimals(amount, decDiv, decMul) = amount * 10^decMul / 10^decDiv`
2. USDG uses `USDG_DECIMALS = 18`, **not** `PRICE_PRECISION = 30`
3. `tokenToUsdMin(amount, price, decimals) = amount * price / 10^decimals`
4. 128-bit product so `5e9 * 10^10 / 10^6` is `5e13`, not a wrapped i64

Named traps vs this kernel: ignore-decimals `1e6` vs `1e18`; treat-USDC-as-18 USD `0` vs `1e8`; PRICE_PRECISION 30 fail-closes to `0` vs USDG 18 = `1e18`.

This is **not** `validateLiquidation`, **not** `getNextFundingRate`, **not** `getFundingFee`, **not** `getFeeBasisPoints`.

## What is not claimed

- Solidity uint256 / mainnet Vault / GLP / 30-decimal price parity
- LIN replacing GMX keepers or the EVM
- Wall-clock superiority vs solc
- `PRICE_PRECISION = 10**30` as a working i64 literal (Compiler 0 rejects it)

## How to re-run

```
python3 test/prove_gmx_dec_external.py
```

Machine-written evidence: `gmx_dec_evidence.json` (do not hand-edit).
Event receipt: `docs/events/EVENT_GMX_DEC_CLONE_LIN.rulel`.
