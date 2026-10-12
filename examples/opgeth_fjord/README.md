# op-geth Fjord L1 fee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OP Stack's
Fjord L1 data-availability fee. The full LIN clone is published in a separate
repository; lin-open keeps proofs and the clone-lin link.

- **Upstream:** [ethereum-optimism/op-geth](https://github.com/ethereum-optimism/op-geth) tag `v1.101702.3` commit `7da4560d1fb3045286b70a8dc23360d2626543f2` (LGPL-3.0)
- **LIN clone (this tree):** [`src/lin_opgeth_fjord.lin`](../../src/lin_opgeth_fjord.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-opgeth-fjord
- **Pinned excerpts:** `test/fixtures/external_proof/NewL1CostFuncFjord.go`, `estimatedDASizeScaled.go`, `newL1CostFuncEcotone.go`, `fjord_constants.go`
- **C11 oracle:** `test/oracles/opgeth_fjord_c11.c`
- **Go oracle:** `test/oracles/opgeth_fjord_go.go`
- **Harness:** `python3 test/prove_opgeth_fjord_external.py`
- **Event receipt:** `docs/events/EVENT_OPGETH_FJORD_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of the **named contrasts** that a fee
estimator gets wrong if it copies an older OP Stack formula:

1. Fjord: `estimatedSize * (baseFeeScalar*l1BaseFee*16 + blobFeeScalar*l1BlobBaseFee) / 1e12`
   with `estimatedSize = max(100e6, 836500*fastlz - 42585600)`. Official emptyTx
   goldens from `rollup_cost_test.go`: fee `3203000`, min gas `1600`. FastLZ of
   emptyTx is pinned at `31` (`TestFlzCompressLen`); the compressor is not ported.
2. An Ecotone leftover (`calldataGas * inner / 16e6`) prices the same emptyTx at
   `960900` — **2242100 wei undercharge**.
3. Dropping the min-size clamp on FastLZ 31 yields a **negative** estimated size
   (intercept is `-42585600`). LIN fail-closes that path to 0; op-geth clamps to
   `100e6`.
4. Solidity-parity vector (FastLZ 235, scalars 20/15, fees 2e6/3e6): fee `105484`,
   gas `2463`.
5. FastLZ size and fee scalars are function arguments. op-geth reads `L1Block`
   via `GetState` and compresses the tx with `FlzCompressLen`.

## What is not claimed

- LIN replacing op-geth, Base, Optimism, or OP Stack consensus
- `FlzCompressLen` / FastLZ compressor / DA batch encoding
- First-Ecotone Bedrock fallback (unset blob+scalar slot)
- uint256 / full-node parity / deposit-tx exemption

Machine-written evidence for a given run is in `opgeth_fjord_evidence.json`
(produced by the harness; do not hand-edit).
