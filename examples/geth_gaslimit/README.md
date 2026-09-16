# go-ethereum CalcGasLimit / VerifyGaslimit — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
block gas-limit adjuster. The LIN clone itself is `src/lin_geth_gaslimit.lin`
in lin-open.

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.14.12` commit `293a300d64be3d9a1c2cc92c26fcff4089deadcd` (LGPL-3.0)
- **Kernel:** `core/block_validator.go` `CalcGasLimit` + `consensus/misc/gaslimit.go` `VerifyGaslimit`
- **LIN clone (this tree):** [`src/lin_geth_gaslimit.lin`](../../src/lin_geth_gaslimit.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-gaslimit
- **Pinned fixtures:** `test/fixtures/external_proof/geth_v1_14_12_CalcGasLimit.go`, `geth_v1_14_12_VerifyGaslimit.go`
- **C11 oracle:** `test/oracles/geth_gaslimit_c11.c`
- **Harness:** `python3 test/prove_geth_gaslimit_external.py`
- **Event receipt:** `docs/events/EVENT_GETH_CALCGASLIMIT_CLONE_LIN.rulel`
- **Go transpiler (fail-closed subset):** `src/lin_from_go.lin`

## What is claimed

Experimental reproduction of Geth's gas-limit step and header check on the
domain Geth actually allows (`MaxGasLimit = 2^63-1`, which fits LIN i64).
Published `TestCalcGasLimit` goldens:

| parent | max increase | min decrease |
|---:|---:|---:|
| 20_000_000 | 20_019_530 | 19_980_470 |
| 40_000_000 | 40_039_061 | 39_960_939 |

Real deltas versus Geth in this profile:

1. `params.GasLimitBoundDivisor` / `params.MinGasLimit` are function arguments.
2. `(parent/divisor)-1` uint64 wrap when `parent < divisor` fail-closes to 0.
3. `VerifyGaslimit`'s `int64(uint64)` casts become a non-negative abs-diff; negatives are rejected.

## What is not claimed

- LIN replacing go-ethereum, Ethereum consensus, or block production
- uint64 values above `2^63-1`
- General superiority vs Go/gc
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `geth_gaslimit_evidence.json`
(produced by the harness; do not hand-edit).
