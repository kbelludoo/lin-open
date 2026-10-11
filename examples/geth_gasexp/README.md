# go-ethereum gasExpEIP158 (ExpByteEIP158=50) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
EXP dynamic-gas addend since Spurious Dragon. The LIN clone itself is
`src/lin_geth_gasexp.lin` in lin-open. The standalone LIN copy lives
in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-gasexp

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/vm/gas_table.go` `gasExpEIP158` (LGPL-3.0)
- **Pinned excerpt:** `test/fixtures/external_proof/gasExpEIP158.go`
- **C11 oracle:** `test/oracles/geth_gasexp_c11.c`
- **Go oracle:** `test/oracles/geth_gasexp_go.go`
- **Harness:** `python3 test/prove_geth_gasexp_external.py` or `make geth-gasexp-proof`
- **Event receipt:** `docs/events/EVENT_GETH_GASEXP_CLONE_LIN.rulel`

## Canonical vectors

`gas = ExpGas + expByteLen * ExpByteEIP158` = `10 + n*50`
`expByteLen = ceil(bitLen / 8)` = `(bitLen + 7) / 8`

| bitLen | expByteLen | EXP gas |
|---|---:|---:|
| 0 | 0 | 10 |
| 1 | 1 | 60 |
| 8 | 1 | 60 |
| 9 | 2 | 110 |
| 256 | 32 | **1610** (EVM word) |
| 2048 | 256 | 12810 (Geth comment max) |

`ge_from_bitlen(256) = 1610` is the Yellow Paper / EIP-158 cost of
`EXP` with a 256-bit exponent (one EVM word), the common on-chain
modular-exponent / `pow` width.

## What this clone improves versus Geth

1. `stack.data[stack.len()-2].BitLen()` becomes an explicit `bitLen` integer.
2. `*Stack` / `*Memory` / `*EVM` / `*Contract` unused gas-table params are dropped.
3. Geth's mul has no overflow check (`Max is 256 * ExpByte`); LIN fail-closes above that bound.
4. `math.SafeAdd` overflow and negatives fail-close to 0.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- `gasExpFrontier` / pre-EIP-158 EXP (`ExpByteFrontier=10`)
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_gasexp_evidence.json`
(produced by the harness; do not hand-edit).
