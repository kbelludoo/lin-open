# EIP-4844 fakeExponential / CalcBlobFee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Ethereum's
EIP-4844 blob-base-fee update. The LIN clone in this tree is
`src/lin_eip4844_blobfee.lin`. The full clone-lin copy lives in a **separate**
repository:

- **Clone-lin (LIN copy):** https://github.com/kbelludoo/clone-lin-eip4844-blobfee
- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.14.12` commit `293a300d64be3d9a1c2cc92c26fcff4089deadcd` `consensus/misc/eip4844/eip4844.go` (LGPL-3.0)
- **Pinned fixture:** `test/fixtures/external_proof/eip4844.go`
- **C11 scalar restatement (transpile input):** `test/fixtures/external_proof/eip4844_integer.c`
- **C11 oracle:** `test/oracles/eip4844_blobfee_c11.c`
- **Harness:** `python3 test/prove_eip4844_blobfee_external.py` or `make eip4844-blobfee-proof`
- **Event receipt:** `docs/events/EVENT_EIP4844_BLOBFEE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Geth's `fakeExponential` /
`CalcBlobFee` after Cancun:

`fee = fakeExponential(minBlobGasPrice, excessBlobGas, updateFraction)`

with `minBlobGasPrice=1`, `updateFraction=3338477`,
`target=3*131072` from `params/protocol_params.go`. Canonical vectors from
Geth `TestCalcBlobFee`: excess 0 → **1** wei; excess 10 MiB → **23** wei.

Real deltas versus Geth in this profile:

1. Package-level `*big.Int` constants become explicit integer arguments
   (`min_price`, `update_frac`).
2. `(accum * numerator) / denominator` uses a 128-bit product (schoolbook
   limbs in LIN, `__int128` in the C11 oracle). Naive uint64 multiply wraps
   on Geth's published vector `(1, 50e6, 2225652)`; the clone does not.
3. Negatives, zero denominator, and uint64 add overflow fail-closed to 0.

## What is not claimed

- Solidity / EVM **uint256** or a replacement Geth node
- LIN replacing Ethereum's blob DA fee market
- General superiority vs gc/LLVM
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `eip4844_blobfee_evidence.json`
(produced by the harness; do not hand-edit).
