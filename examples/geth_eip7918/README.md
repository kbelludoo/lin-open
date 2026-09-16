# Geth Osaka EIP-7918 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
Osaka EIP-7918 blob reserve-price path. The LIN clone itself is
`src/lin_geth_eip7918.lin` in lin-open.

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) `consensus/misc/eip4844/eip4844.go` (LGPL-3.0)
- **Pinned commit:** `24dd23631661017452cfc7bcd07c114d3796cd65`
- **LIN clone (this tree):** [`src/lin_geth_eip7918.lin`](../../src/lin_geth_eip7918.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-eip7918
- **Pinned fixture:** `test/fixtures/external_proof/eip4844.go`
- **C11 oracle:** `test/oracles/geth_eip7918_c11.c`
- **Harness:** `python3 test/prove_geth_eip7918_external.py`
- **Event receipt:** `docs/events/EVENT_GETH_EIP7918_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Geth's `calcExcessBlobGas` **Osaka
path** (EIP-7918):

```
if parent_excess + parent_used < target * GAS_PER_BLOB: return 0
if BlobBaseCost * base_fee > blob_fee * GAS_PER_BLOB:
    return parent_excess + parent_used * (max - target) / max
return parent_excess + parent_used - target * GAS_PER_BLOB
```

Real deltas versus Geth in this profile:

1. `*types.Header` / `*params.ChainConfig` / `*big.Int` become function arguments.
2. Reserve-price products use a 128-bit compare (schoolbook limbs in LIN, `__int128` in C11).
3. `fakeExponential` intermediates that do not fit uint64 fail-closed to 0 (Geth min blob fee is 1).

Geth test vectors reproduced:

| Vector | Result |
|---|---|
| Prague BelowReservePrice (`base_fee=1e9`, 6 blobs) | `262144` |
| Prague AboveReservePrice (`base_fee=1`) | `0` |
| TestCalcBlobFeePostOsaka BPO1 | `5617366` |
| TestCalcBlobFeePostOsaka BPO3 | `20107103` |
| TestFakeExponential `(1, 50000000, 2225652)` | `5709098764` |

## What is not claimed

- Geth **big.Int** / arbitrary mainnet Osaka header parity
- LIN replacing Geth, the EVM, or proto-danksharding
- General superiority vs gc/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `geth_eip7918_evidence.json`
(produced by the harness; do not hand-edit).
