# Uniswap V3 computeSwapStep — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V3
`SwapMath.computeSwapStep`. The standalone LIN copy lives in a separate
clone-lin repository; lin-open keeps proofs, the kernel, and the transpiler
delta.

- **Upstream:** [Uniswap/v3-core](https://github.com/Uniswap/v3-core) tag `v1.0.0` `contracts/libraries/SwapMath.sol` (BUSL-1.1 Change Date 2023-04-01 elapsed → GPL-2.0-or-later)
- **LIN clone (this tree):** [`src/lin_uniswap_v3_step.lin`](../../src/lin_uniswap_v3_step.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v3-step
- **Pinned fixture:** `test/fixtures/external_proof/SwapMath.sol`
- **C11 oracle:** `test/oracles/uniswap_v3_step_c11.c`
- **Harness:** `python3 test/prove_uniswap_v3_step_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V3_STEP_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale / Q32 reproduction of the Uniswap V3 **swap-step
cap**: remaining after fee vs amount-to-target, exact-in vs exact-out sign,
and fee remainder vs `mulDivRoundingUp`. Class: EXPERIMENTAL (real published
algorithm, deliberately reduced operand width).

Real deltas versus the Solidity library in this profile:

1. `sqrtRatioCurrentX96` / `sqrtRatioTargetX96` / `liquidity` / `amountRemaining` / `feePips` are explicit LIN arguments (no pool storage).
2. Q32=2^32 instead of Q96=2^96 (Q96 exceeds signed i64 and is rejected).
3. `(a*b)/d` uses a 128-bit product. Naive i64 `(remaining*(1e6-fee))/1e6` wraps; the clone fail-closes overflow to 0.
4. Tuple `(next, amountIn, amountOut, feeAmount)` is split into named functions.

This is **not** a retread of `getNextSqrtPriceFromInput` (clone-lin-uniswap-v3-next-sqrt), `getNextSqrtPriceFromOutput` (clone-lin-uniswap-v3-output), amount-delta (clone-lin-uniswap-v3-sqrt), or the tick table (clone-lin-uniswap-v3-tick). Those appear only as helpers inside the cap.

## What is not claimed

- Solidity **uint160** / **Q64.96** / mainnet **Pool** / **SwapRouter** / NFT parity
- LIN replacing Uniswap or the EVM
- Wall-clock superiority vs solc
- That this clone is a production AMM

Machine-written evidence for a given run is in `uniswap_v3_step_evidence.json`
(produced by the harness; do not hand-edit).
