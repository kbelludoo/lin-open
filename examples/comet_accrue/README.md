# Compound III accruedInterestIndices — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound III's
per-second supply/borrow index update. The standalone LIN copy lives in a
separate repository:

- **Clone-lin:** https://github.com/kbelludoo/clone-lin-comet-accrue
- **In-tree kernel (lin-open):** [`src/lin_comet_accrue.lin`](../../src/lin_comet_accrue.lin)

## Upstream (pinned, auditable)

- [compound-finance/comet](https://github.com/compound-finance/comet)
  `contracts/CometWithExtendedAssetList.sol`
  (`accruedInterestIndices` / `getSupplyRate` / `getBorrowRate` / `mulFactor` / `getUtilization`)
- Constants: `contracts/CometCore.sol`
  (`SECONDS_PER_YEAR = 31_536_000`, `FACTOR_SCALE = 1e18`, `BASE_INDEX_SCALE = 1e15`)
- commit `f766f51583c23acc33b2a7824654ef2029a96804`
- CometWithExtendedAssetList.sol git blob `3490e984d133789aa1afe2e8f7e37a11d2512396`
  sha256 `c9099e56eda092fd0150005706edf086723899afb102f164b60ad1f36a426961`
- CometCore.sol git blob `534f2701b6c8e683f9294112b0bcc23878d39fe6`
  sha256 `1d80f0d12c101d01c2e1f38e8662cfcf350299b1c78188f8c501bb1c51b5ec78`
- BUSL-1.1 Change Date 2025-12-31 elapsed; Change License **GPL-2.0-or-later**
  (this run is 2026-10-12)

## Proofs

- Pinned fixtures: `test/fixtures/external_proof/CometWithExtendedAssetList.sol` + `CometCore.sol`
- C11 oracle: `test/oracles/comet_accrue_c11.c`
- Harness: `python3 test/prove_comet_accrue_external.py`
- Gate: `test/verify_comet_accrue.sh` / `make comet-accrue-proof`
- Event receipt: `docs/events/EVENT_COMET_ACCRUE_CLONE_LIN.rulel`
- Machine-written evidence: `comet_accrue_evidence.json` (do not hand-edit)

## What is claimed

Experimental, uint64-scale reproduction of Compound III's per-second index
accrual. Real deltas versus the Solidity implementation in this profile:

1. Hidden `getUtilization()` / `getSupplyRate` / `getBorrowRate` / storage IRM
   slopes / `baseSupplyIndex` become function arguments.
2. `mulFactor(n, rate * timeElapsed)` is `n * (rate * dt) / 1e18` with a
   128-bit product. Naive signed-i64 `rate * dt` wraps; LIN fail-closes if
   that product does not fit uint64. Solidity `uint256` would succeed.
3. `floor(index * rate / 1e18) * dt` is **not** the on-chain formula. For
   genesis index `1e15`, rate `1`, dt `1000` the two-step path yields **0**;
   `(rate * dt)` first yields **1**.
4. Named contrast (not a TVL claim): Compound V2 JumpRate is **per-block**
   (`blocksPerYear = 2102400`). Compound III is **per-second**
   (`SECONDS_PER_YEAR = 31536000`). Same 1% wad, genesis index, 365-day year:
   feeding the V2 per-block rate into the III update over-accrues by
   `31536000/2102400 ≈ 15`.

This is **not** the presentValue / principalValue kernel
(`clone-lin-comet-pv`).

## What is not claimed

- Solidity **uint256** / mainnet Comet / USDC / PriceFeed parity
- LIN replacing Compound III, JumpRate, or the EVM
- Live liquidation or interest-income profit
- General superiority vs solc/LLVM
