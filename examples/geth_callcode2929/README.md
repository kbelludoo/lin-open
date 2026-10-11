# Geth CALLCODE / DELEGATECALL / STATICCALL EIP-2929 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of go-ethereum's
Berlin CALL variants that are **not** `gasCallEIP2929`. The full LIN clone is
published in a separate repository; lin-open keeps proofs and the clone-lin link.

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` (LGPL-3.0)
- **LIN clone (this tree):** [`src/lin_geth_callcode2929.lin`](../../src/lin_geth_callcode2929.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-callcode2929
- **Pinned excerpts:** `test/fixtures/external_proof/gasCallCodeEIP2929.go`, `test/fixtures/external_proof/gasCallCode.go`
- **C11 oracle:** `test/oracles/geth_callcode2929_c11.c`
- **Go oracle:** `test/oracles/geth_callcode2929_go.go`
- **Harness:** `python3 test/prove_geth_callcode2929_external.py`
- **Event receipt:** `docs/events/EVENT_GETH_CALLCODE2929_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of the **named contrast** vs CALL:

1. Shared Berlin wrapper (`makeCallVariantGasCallEIP2929`): charge cold-warm
   `2500` via `UseGas` **before** EIP-150 63/64, then add `2500` back into
   returned dynamic gas. Opcode total = `100 + dynamic`.
2. `gasCallCode` extras = memory + `CallValueTransferGas=9000` if value.
   It **never** adds `CallNewAccountGas=25000` (CALLCODE runs in the caller).
3. `gasDelegateCall` / `gasStaticCall` extras = memory only.
4. Because 63/64 is applied **after** extras, `CALL − CALLCODE` at
   value+new is **390**, not 25000. A naive `CALL − 25000` fee is wrong.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Quadratic `memoryGasCost` / Cmem (memory_gas is an explicit integer)
- CallStipend 2300, EIP-7702 `ParseDelegation`, EIP-4762 Verkle
- uint256 / full-node parity

Machine-written evidence for a given run is in `geth_callcode2929_evidence.json`
(produced by the harness; do not hand-edit).
