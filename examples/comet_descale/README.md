# Compound III accrualDescaleFactor — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III
reward-wei descale. The LIN clone itself is `src/lin_comet_descale.lin` in
lin-open. The copy of the clone lives in a separate repository.

- **Upstream:** [compound-finance/comet](https://github.com/compound-finance/comet) `contracts/CometWithExtendedAssetList.sol` + `CometCore.sol` (GPL-2.0-or-later after BUSL Change Date 2025-12-31)
- **Pinned commit:** `f766f51583c23acc33b2a7824654ef2029a96804`
- **LIN clone (this tree):** [`src/lin_comet_descale.lin`](https://github.com/kbelludoo/lin-open/blob/HEAD/src/lin_comet_descale.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-comet-descale
- **Pinned fixtures:** `test/fixtures/external_proof/CometAccrualDescale.excerpt.sol`, `test/fixtures/external_proof/CometCore.sol`
- **C11 oracle:** `test/oracles/comet_descale_c11.c`
- **Harness:** `python3 test/prove_comet_descale_external.py`
- **Event receipt:** `docs/events/EVENT_COMET_DESCALE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound III

`accrualDescaleFactor = baseScale / 1e6`

then

`principal * indexDelta / trackingIndexScale / factor`.

Class: **EXPERIMENTAL** (real published algorithm, reduced operand width).
Not mainnet uint256.

Named contrasts (all recomputed this run):

| Path | Result |
|---|---|
| USDC 6-dec factor | `1` — preserve, 1 USDC → `1e6` reward wei |
| WETH 18-dec factor | `1e12` — 1 WETH also → `1e6` |
| WBTC 8-dec factor | `100` — 1 WBTC → `1e6` |
| 4-dec `baseScale` | `0` (Solidity `BadDecimals`) |
| WETH forget-descale | `1e18` vs correct `1e6` (`1e12x`) |
| USDC treated as 18-dec | `0` vs correct `1e6` |
| GMX-style 6→18 upscale | `1e18` — opposite direction |
| naive i64 `5e9*1e10/1e6` | wraps; 128-bit muldiv = `5e13` |

## What is not claimed

- Solidity **uint256** / mainnet Comet / COMP distributor parity
- `divBaseWei` tracking-index wrap, `accruedInterestIndices`, or `presentValue` (other clones)
- LIN replacing Compound, Uniswap, or the EVM
- TVL or live COMP-emission profit
- General superiority vs solc/LLVM

Machine-written evidence for a given run is in `comet_descale_evidence.json`
(produced by the harness; do not hand-edit).
