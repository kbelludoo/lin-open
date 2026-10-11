# go-ethereum makeGasLog (LogDataGas=8) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
LOG0–LOG4 execution-gas addends. The LIN clone itself is
`src/lin_geth_gaslog.lin` in lin-open. The standalone LIN copy lives
in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-gaslog

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas_table.go` `makeGasLog` (LGPL-3.0)
- **Pinned excerpt:** `test/fixtures/external_proof/makeGasLog.go`
- **C11 oracle:** `test/oracles/geth_gaslog_c11.c`
- **Go oracle:** `test/oracles/geth_gaslog_go.go`
- **Harness:** `python3 test/prove_geth_gaslog_external.py` or `make geth-gaslog-proof`
- **Event receipt:** `docs/events/EVENT_GETH_GASLOG_CLONE_LIN.rulel`

## Canonical vectors

`exec = LogGas + n*LogTopicGas + size*LogDataGas` = `375 + n*375 + size*8`

| n (LOG*) | size (data bytes) | exec gas |
|---|---:|---:|
| 0 | 0 | 375 |
| 0 | 1 | 383 |
| 0 | 32 | 631 |
| 3 | 32 | **1756** (ERC-20 `Transfer`) |
| 4 | 0 | 1875 |
| 4 | 1024 | 10067 |

`gl_exec(3, 32) = 1756` is the Yellow Paper cost of a standard ERC-20
`Transfer(address,address,uint256)` log (3 topics + 32-byte amount),
before memory expansion.

## What this clone improves versus Geth

1. `makeGasLog` is a closure factory (`return func(...)` over `n`). LIN is a pure function of `n` and `size`.
2. `stack.Back(1)` / `*Stack` / `*Memory` / `*EVM` become explicit `size` and optional `memgas` integers.
3. `n` outside `0..4` fail-closes (the jump table only wires LOG0–LOG4).
4. Negative size fail-closes (Geth models this as `Uint64WithOverflow`).

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Full LOG* including Yellow Paper `Cmem` (that is the separate memoryGasCost clone)
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_gaslog_evidence.json`
(produced by the harness; do not hand-edit).
