# go-ethereum callGas (EIP-150 63/64) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
EIP-150 call stipend. The LIN clone itself is `src/lin_geth_callgas.lin`
in lin-open. The standalone LIN copy lives in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-callgas

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas.go` `callGas` (LGPL-3.0)
- **Pinned excerpt:** `test/fixtures/external_proof/callGas.go`
- **C11 oracle:** `test/oracles/geth_callgas_c11.c`
- **Go oracle:** `test/oracles/geth_callgas_go.go`
- **Harness:** `python3 test/prove_geth_callgas_external.py` or `make geth-callgas-proof`
- **Event receipt:** `docs/events/EVENT_GETH_CALLGAS_CLONE_LIN.rulel`

## Canonical vectors

| case | EIP-150 | available | base | cost | cost_hi | gas |
|---|---|---:|---:|---:|---:|---:|
| 64k requested 64k | 1 | 64000 | 0 | 64000 | 0 | 63000 |
| requested below stipend | 1 | 64000 | 700 | 1000 | 0 | 1000 |
| 64 requested 100 | 1 | 64 | 0 | 100 | 0 | 63 |
| 65 requested 65 | 1 | 65 | 0 | 65 | 0 | 64 |
| pre-EIP-150 passthrough | 0 | 1000 | 0 | 1000 | 0 | 1000 |
| EIP-150 cost not uint64 | 1 | 1000 | 0 | 0 | 1 | 985 |

`cg_callgas(1, 64000, 0, 64000, 0) = 63000` is `remaining - remaining/64`.

## What this clone improves versus Geth

1. `*uint256.Int` becomes explicit `cost` / `cost_hi` integer arguments.
2. `available - base` is underflow-checked. Pinned Geth v1.16.9 uint64-wraps
   when `available < base`. After wrap the 63/64 cap can be skipped and a
   small requested cost is granted. LIN fail-closes to 0. Callers of
   `gasCall` typically already hold remaining ≥ static cost; this is an
   audit of the helper, not a claimed consensus bug.
3. Pre-EIP-150 `cost_hi != 0` fail-closes to 0 instead of `ErrGasUintOverflow`.
4. Stipend uses Geth's `x - x/64` form, not a naive `x*63/64` product.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- That available<base wrap is a mainnet consensus bug
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_callgas_evidence.json`
(produced by the harness; do not hand-edit).
