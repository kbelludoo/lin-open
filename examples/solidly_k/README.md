# Solidly BaseV1Pair cubic k — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Solidly
`BaseV1Pair` `_k` / `_f` / `_d` / `_get_y`. The standalone LIN copy lives in a
separate clone-lin repository; lin-open keeps proofs, the kernel, and the
transpiler delta.

- **Upstream:** [transmissions11/solidly](https://github.com/transmissions11/solidly) `contracts/BaseV1-core.sol` (MIT)
- **LIN clone (this tree):** [`src/lin_solidly_k.lin`](../../src/lin_solidly_k.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-solidly-k
- **Pinned fixture:** `test/fixtures/external_proof/BaseV1-core.sol`
- **C11 oracle:** `test/oracles/solidly_k_c11.c`
- **Harness:** `python3 test/prove_solidly_k_external.py`
- **Event receipt:** `docs/events/EVENT_SOLIDLY_K_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale / WAD'=1e6 reproduction of Solidly **stable cubic
invariant** `x³y + y³x` versus **volatile** `xy`, plus Newton `_get_y` used by
`getAmountOut`. Class: EXPERIMENTAL (real published algorithm, deliberately
reduced operand width).

Velodrome (Optimism) and Aerodrome (Base) inherit this kernel. The pin is the
MIT Solidly source, not the BUSL Velodrome tree.

Real deltas versus the Solidity pair in this profile:

1. `amount_in` / `reserve_in` / `reserve_out` / `stable` / `fee_bps` are explicit LIN arguments (no pair storage, no `tokenIn` address).
2. WAD'=1e6 instead of 1e18 (sequential 1e18 cubes overflow signed i64).
3. `(a*b)/WAD` uses a 128-bit product. Naive i64 `(x*x)/WAD` wraps; the clone fail-closes overflow to 0.
4. Newton is capped at 16 iterations (Solidly 255) and fail-closes if `dy > y`.

Named commercial contrast on a 1:1 pool, 10k in, 1 bps fee: **cubic out=9997**,
**xy out=9900**. Using the volatile formula on a stable pool underpays.

This is **not** a retread of Uniswap V2 `xy`, Uniswap V3 sqrt-price, Saddle/Curve
`getD`/`getY`, or Maker `rpow`.

## What is not claimed

- Solidity **uint256** / **WAD=1e18** / mainnet Velodrome or Aerodrome swap parity
- LIN replacing Solidly, Velodrome, Aerodrome, or the EVM
- Wall-clock superiority vs solc
- That this clone is a production DEX

Machine-written evidence for a given run is in `solidly_k_evidence.json`
(produced by the harness; do not hand-edit).
