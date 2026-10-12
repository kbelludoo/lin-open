# op-geth Ecotone L1 fee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of OP Stack's
Ecotone L1 data-availability fee and Isthmus/Jovian operator fee. The full LIN
clone is published in a separate repository; lin-open keeps proofs and the
clone-lin link.

- **Upstream:** [ethereum-optimism/op-geth](https://github.com/ethereum-optimism/op-geth) tag `v1.101702.3` commit `7da4560d1fb3045286b70a8dc23360d2626543f2` (LGPL-3.0)
- **LIN clone (this tree):** [`src/lin_opgeth_ecotone.lin`](../../src/lin_opgeth_ecotone.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-opgeth-ecotone
- **Pinned excerpts:** `test/fixtures/external_proof/newL1CostFuncEcotone.go`, `newL1CostFuncBedrockHelper.go`, `bedrockCalldataGasUsed.go`, `newOperatorCostFuncIsthmus.go`, `newOperatorCostFuncOperatorFeeFix.go`, `l1CostHelper.go`
- **C11 oracle:** `test/oracles/opgeth_ecotone_c11.c`
- **Go oracle:** `test/oracles/opgeth_ecotone_go.go`
- **Harness:** `python3 test/prove_opgeth_ecotone_external.py`
- **Event receipt:** `docs/events/EVENT_OPGETH_ECOTONE_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of the **named contrasts** that a fee
estimator gets wrong if it copies an older OP Stack formula:

1. Ecotone: `calldataGas * (l1BaseFee*16*baseScalar + blobBaseFee*blobScalar) / 16e6`
   with `calldataGas = zeroes*4 + ones*16`. Official emptyTx goldens from
   `rollup_cost_test.go`: fee `960900`, calldata gas `480`.
2. A Bedrock-style estimator that **drops the blob term** prices the same
   emptyTx at `960000` — **900 wei undercharge**. Real Base blob fees make
   this gap material.
3. Bedrock/Regolith official emptyTx: `11326000000000` / `3710000000000`
   (includes overhead 50 and the pre-Regolith `+68` nonzero pad).
4. Isthmus operator `gas*scalar/1e6 + constant` vs Jovian `gas*scalar*100 + constant`
   on the official 1618-gas vector. The variable term differs by **1e8×**.
5. Storage scalars are function arguments. op-geth reads `L1Block` via `GetState`.

## What is not claimed

- LIN replacing op-geth, Base, Optimism, or OP Stack consensus
- Fjord FastLZ / `estimatedDASize` / min-transaction-size clamp
- First-Ecotone Bedrock fallback (unset blob+scalar slot)
- uint256 / full-node parity / deposit-tx exemption

Machine-written evidence for a given run is in `opgeth_ecotone_evidence.json`
(produced by the harness; do not hand-edit).
