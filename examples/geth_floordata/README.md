# go-ethereum FloorDataGas (EIP-7623) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's Prague
data-floor gas. The LIN clone itself is `src/lin_geth_floordata.lin` in lin-open.
The standalone LIN copy lives in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-floordata

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/state_transition.go` `FloorDataGas` (LGPL-3.0)
- **Constants:** `params/protocol_params.go` `TxGas=21000`, `TxTokenPerNonZeroByte=4`, `TxCostFloorPerToken=10`, `MaxGasLimit=2^63-1`
- **Pinned excerpts:** `test/fixtures/external_proof/FloorDataGas.go`, `test/fixtures/external_proof/eip7623_protocol_params.go`
- **C11 oracle:** `test/oracles/geth_floordata_c11.c`
- **Go oracle:** `test/oracles/geth_floordata_go.go`
- **Harness:** `python3 test/prove_geth_floordata_external.py` or `make geth-floordata-proof`
- **Event receipt:** `docs/events/EVENT_GETH_FLOORDATA_CLONE_LIN.rulel`

## Canonical vectors

| case | z | nz | floor gas |
|---|---:|---:|---:|
| empty transfer | 0 | 0 | 21000 |
| 1 zero byte | 1 | 0 | 21010 |
| 1 nonzero byte | 0 | 1 | 21040 |
| 1 zero + 1 nonzero | 1 | 1 | 21050 |
| 100 zero bytes | 100 | 0 | 22000 |
| 100 nonzero bytes | 0 | 100 | 25000 |
| 500 zero + 1000 nonzero | 500 | 1000 | 66000 |

Prague charge is `max(istanbul_intrinsic, floor)`. For 1 nonzero byte that is
21040 (floor), not 21016 (Istanbul intrinsic). That is the EIP-7623 calldata
floor wallets and relays must budget.

## What this clone improves versus Geth

1. `bytes.Count` / `len([]byte)` become explicit integer arguments `z` / `nz`.
2. `nz * TxTokenPerNonZeroByte` is overflow-checked. Pinned Geth v1.16.9 does
   not guard that multiply; uint64 wrap of `nz=2^62` yields tokens=0 and
   returns 21000. LIN fail-closes to 0. This wrap is **not reachable** at
   `MaxBlockSize=8388608`; it is a defect of the unbounded function, not a
   mainnet consensus bug.
3. Overflow fail-closes at i64max (the published `MaxGasLimit`) instead of
   `(0, error)` against `MaxUint64`.
4. Token-per-zero-byte is an explicit constant (`1`), matching EIP-7623 rather
   than an implicit `+ z`.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Full uint64 wrap semantics above `MaxGasLimit`
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_floordata_evidence.json`
(produced by the harness; do not hand-edit).
