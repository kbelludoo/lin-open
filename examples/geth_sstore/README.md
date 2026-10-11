# go-ethereum makeGasSStoreFunc (EIP-3529 SSTORE) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
SSTORE dynamic-gas and refund table since Istanbul / Berlin / London.
The LIN clone itself is `src/lin_geth_sstore.lin` in lin-open. The
standalone LIN copy lives in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-sstore

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/operations_acl.go` `makeGasSStoreFunc` (LGPL-3.0)
- **Pinned excerpt:** `test/fixtures/external_proof/makeGasSStoreFunc.go`
- **C11 oracle:** `test/oracles/geth_sstore_c11.c`
- **Go oracle:** `test/oracles/geth_sstore_go.go`
- **Harness:** `python3 test/prove_geth_sstore_external.py` or `make geth-sstore-proof`
- **Event receipt:** `docs/events/EVENT_GETH_SSTORE_CLONE_LIN.rulel`

## Canonical vectors (EIP-3529, gas_left=100000)

Slot tokens: `0` = empty, `1`/`2`/`3` = distinct nonzeros.

| orig | curr | val | warm | gas | refund |
|---|---|---|---|---:|---:|
| 0 | 0 | 1 | yes | **20000** | 0 |
| 0 | 0 | 1 | no | **22100** | 0 |
| 1 | 1 | 0 | yes | 2900 | **4800** |
| 1 | 1 | 0 | no | 5000 | 4800 |
| 1 | 1 | 2 | yes | 2900 | 0 |
| 0 | 1 | 0 | yes | 100 | **19900** |
| 1 | 2 | 1 | yes | 100 | 2800 |
| 1 | 0 | 1 | yes | 100 | **-2000** |
| * | * | * | * | **0** if gas_left ≤ 2300 | 0 |

`ss_first_credit_cold() = 22100` is the Yellow Paper / EIP-2929 cost of
the first write of a previously empty storage slot when the key is cold —
the common “first ERC-20 credit” SSTORE.

EIP-3529 replace of the clear schedule is the identity
`5000 - 2100 + 1900 = 4800` (was 15000 under EIP-2200).

## What this clone improves versus Geth

1. `StateDB.GetStateAndCommittedState` + `stack.Back`/`peek` become explicit `orig`/`curr`/`val` integers.
2. `*Stack` / `*Memory` / `*EVM` / `*Contract` / `StateDB` unused gas-table params are dropped.
3. Reentrancy sentry (`gas_left<=2300`) and illegal tokens fail-close to 0.
4. Refund is a named signed delta; 4800 vs 15000 is an explicit identity.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Account-capped refund / `RefundQuotientEIP3529` (1/5) application
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_sstore_evidence.json`
(produced by the harness; do not hand-edit).
