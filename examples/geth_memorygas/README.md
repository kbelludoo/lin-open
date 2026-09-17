# go-ethereum memoryGasCost (Yellow Paper Cmem) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
quadratic memory-expansion gas. The LIN clone itself is
`src/lin_geth_memorygas.lin` in lin-open. The standalone LIN copy lives in a
separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-memorygas

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas_table.go` `memoryGasCost` (LGPL-3.0)
- **Helper:** `core/vm/common.go` `toWordSize`
- **Constants:** `params/protocol_params.go` `MemoryGas=3`, `QuadCoeffDiv=512`
- **Pinned excerpts:** `test/fixtures/external_proof/memoryGasCost.go`, `toWordSize.go`, `memorygas_protocol_params.go`
- **C11 oracle:** `test/oracles/geth_memorygas_c11.c`
- **Go oracle:** `test/oracles/geth_memorygas_go.go`
- **Harness:** `python3 test/prove_geth_memorygas_external.py` or `make geth-memorygas-proof`
- **Event receipt:** `docs/events/EVENT_GETH_MEMORYGAS_CLONE_LIN.rulel`

## Canonical vectors

| case | new size | current len | last cost | fee |
|---|---:|---:|---:|---:|
| empty | 0 | 0 | 0 | 0 |
| first word | 32 | 0 | 0 | 3 |
| 32 words (1 KiB) | 1024 | 0 | 0 | 98 |
| grow 32→33 | 33 | 32 | 3 | 3 |
| no grow | 32 | 32 | 3 | 0 |
| 64 words from 32 | 2048 | 1024 | 98 | 102 |

`mg_fee(1024, 0, 0) = 98` is Yellow Paper \(C_{mem}(32)=3\cdot32+32^{2}/512\).

## What this clone improves versus Geth

1. `*Memory` `Len()` / `lastGasCost` become explicit integer arguments.
2. `newTotalFee - lastGasCost` is underflow-checked. Pinned Geth v1.16.9
   uint64-wraps when `last > total`. LIN fail-closes to 0. The wrap is
   **not reachable** while Geth writes `lastGasCost` after each expansion.
3. `words*words` at the official `0x1FFFFFFFE0` cap does not fit signed i64.
   LIN uses a 128-bit product (same schoolbook as the Compound JumpRate clone).
4. `size > 0x1FFFFFFFE0` fail-closes to 0 instead of `ErrGasUintOverflow`.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- That last>total wrap is a mainnet consensus bug
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands, 128-bit square).
Machine-written evidence for a given run is in `geth_memorygas_evidence.json`
(produced by the harness; do not hand-edit).
