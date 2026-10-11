# go-ethereum gasCreateEip3860 (EIP-3860) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
EIP-3860 initcode word-gas surcharge. The LIN clone itself is
`src/lin_geth_create3860.lin` in lin-open. The standalone LIN copy lives
in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-create3860

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas_table.go` `gasCreateEip3860` / `gasCreate2Eip3860` (LGPL-3.0)
- **Pinned excerpt:** `test/fixtures/external_proof/gasCreateEip3860.go`
- **C11 oracle:** `test/oracles/geth_create3860_c11.c`
- **Go oracle:** `test/oracles/geth_create3860_go.go`
- **Harness:** `python3 test/prove_geth_create3860_external.py` or `make geth-create3860-proof`
- **Event receipt:** `docs/events/EVENT_GETH_CREATE3860_CLONE_LIN.rulel`

## Canonical vectors

| size | CREATE word gas | CREATE2 word gas |
|---|---:|---:|
| 0 | 0 | 0 |
| 1 | 2 | 8 |
| 32 | 2 | 8 |
| 33 | 4 | 16 |
| 49152 (`MaxInitCodeSize`) | 3072 | 12288 |
| 49153 | LIN=0 / Geth=error | LIN=0 / Geth=error |

`ic_create(32) = 2` is `InitCodeWordGas * ((size+31)/32)`.
`ic_create2(32) = 8` adds `Keccak256WordGas`.

## What this clone improves versus Geth

1. `stack.Back(2)` / `*Stack` / `*Memory` / `*EVM` become explicit `size` and optional `memgas` integers.
2. `size > MaxInitCodeSize` fail-closes to 0. Geth returns `ErrMaxInitCodeSizeExceeded` and does not return leftover memory gas.
3. CREATE2's keccak word surcharge is an explicit `2+6` sum, not a `params.` selector.
4. Negative size fail-closes (Geth models this as `Uint64WithOverflow`).

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Full CREATE/CREATE2 including Yellow Paper `Cmem` (that is the separate memoryGasCost clone)
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_create3860_evidence.json`
(produced by the harness; do not hand-edit).
