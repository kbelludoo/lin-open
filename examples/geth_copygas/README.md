# go-ethereum memoryCopierGas (CopyGas=3) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
copy-word and KECCAK256-word gas addends. The LIN clone itself is
`src/lin_geth_copygas.lin` in lin-open. The standalone LIN copy lives
in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-copygas

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas_table.go` `memoryCopierGas` / `gasKeccak256` (LGPL-3.0)
- **Pinned excerpts:** `test/fixtures/external_proof/memoryCopierGas.go`, `test/fixtures/external_proof/gasKeccak256.go`
- **C11 oracle:** `test/oracles/geth_copygas_c11.c`
- **Go oracle:** `test/oracles/geth_copygas_go.go`
- **Harness:** `python3 test/prove_geth_copygas_external.py` or `make geth-copygas-proof`
- **Event receipt:** `docs/events/EVENT_GETH_COPYGAS_CLONE_LIN.rulel`

## Canonical vectors

| size | COPY word gas (`CopyGas=3`) | KECCAK256 word gas (`Keccak256WordGas=6`) |
|---|---:|---:|
| 0 | 0 | 0 |
| 1 | 3 | 6 |
| 32 | 3 | 6 |
| 33 | 6 | 12 |
| 1024 | 96 | 192 |
| 24576 | 2304 | 4608 |
| 49152 | 4608 | 9216 |

`cg_copy(32) = 3` is `CopyGas * ((size+31)/32)`.
`cg_keccak(32) = 6` is `Keccak256WordGas * ((size+31)/32)`.

## What this clone improves versus Geth

1. `memoryCopierGas` is a closure factory (`return func(...)`). LIN is a pure function of `size`.
2. `stack.Back(stackpos)` / `*Stack` / `*Memory` / `*EVM` become explicit `size` and optional `memgas` integers.
3. KECCAK256 word gas is explicit `6*words`, not mixed with CREATE2's `2+6` initcode surcharge.
4. Negative size fail-closes (Geth models this as `Uint64WithOverflow`).

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Full COPY/KECCAK256 including Yellow Paper `Cmem` (that is the separate memoryGasCost clone)
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_copygas_evidence.json`
(produced by the harness; do not hand-edit).
