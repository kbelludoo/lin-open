# GMX V2 getBorrowingFactorPerSecond — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of GMX V2
`getBorrowingFactorPerSecond`. The LIN sources live in lin-open; a full
clone-lin copy is in a **separate** repository.

- **Upstream:** [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) `contracts/market/MarketUtils.sol` (GPL-2.0-or-later after BUSL Change Date 2026-08-31)
- **Pinned commit:** `a85ea3491c19c93bb4b5a002d9b358fb769b7849`
- **LIN clone (this tree):** [`src/lin_gmx_v2_borrow_fps.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-3cda/src/lin_gmx_v2_borrow_fps.lin)
- **Separate clone-lin repo:** [https://github.com/kbelludoo/clone-lin-gmx-v2-borrow-fps](https://github.com/kbelludoo/clone-lin-gmx-v2-borrow-fps)
- **Pinned excerpts:** `test/fixtures/external_proof/GetBorrowingFactorPerSecond.excerpt.sol` and kink / usage / cumulative / Precision siblings
- **C11 oracle:** `test/oracles/gmx_v2_borrow_fps_c11.c`
- **Harness:** `python3 test/prove_gmx_v2_borrow_fps_external.py`
- **Event receipt:** `docs/events/EVENT_GMX_V2_BORROW_FPS_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of GMX V2 borrowing-factor-per-second
(FLOAT' = 1e6, exponent/pow identity skip). Real deltas versus the Solidity
kernel in this profile:

1. DataStore parameters are function arguments.
2. `(a*b)/d` uses a 128-bit product. Naive signed i64 `7e9*2e9/1e6` wraps.
3. Empty pool fail-closes (`g2b_ok=0`) instead of reverting.
4. `skipBorrowingFeeForSmallerSide` zeros the lighter OI; equal OI still charges both.
5. Kink additional is raw `(above-base)*diff/(FLOAT-opt)`, not `applyFactor`.
6. Cumulative delta is `duration * fps`. `applyFactor(duration, fps)` floors
   `3600*10/1e6` to 0. A V1-style `floor(duration/3600)*fps` yields 10.

## What is not claimed

- Solidity **uint256** / Arbitrum GMX V2 **FLOAT=1e30** parity
- `PRBMathUD60x18.pow` when the exponent is not 1.0
- LIN replacing GMX, Uniswap, or the EVM
- A full port of GMX V1 `getNextBorrowingRate` (interval contrast only)

Machine-written evidence for a given run is in `gmx_v2_borrow_fps_evidence.json`
(produced by the harness; do not hand-edit).
