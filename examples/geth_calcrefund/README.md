# go-ethereum calcRefund (EIP-3529) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's London
refund cap. The LIN clone itself is `src/lin_geth_calcrefund.lin` in lin-open.
The standalone LIN copy lives in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-calcrefund

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/state_transition.go` `calcRefund` (LGPL-3.0)
- **Constants:** `params/protocol_params.go` `RefundQuotient=2`, `RefundQuotientEIP3529=5`
- **Pinned excerpts:** `test/fixtures/external_proof/calcRefund.go`, `test/fixtures/external_proof/eip3529_protocol_params.go`
- **C11 oracle:** `test/oracles/geth_calcrefund_c11.c`
- **Go oracle:** `test/oracles/geth_calcrefund_go.go`
- **Harness:** `python3 test/prove_geth_calcrefund_external.py` or `make geth-calcrefund-proof`
- **Event receipt:** `docs/events/EVENT_GETH_CALCREFUND_CLONE_LIN.rulel`

## Canonical vectors

| case | used | state refund | london | refund |
|---|---:|---:|---:|---:|
| empty refund counter | 21000 | 0 | 1 | 0 |
| 21k used, large SSTORE, London | 21000 | 100000 | 1 | 4200 |
| 21k used, large SSTORE, pre-London | 21000 | 100000 | 0 | 10500 |
| state refund smaller than cap | 21000 | 1000 | 1 | 1000 |
| 5 used / 5 | 5 | 100 | 1 | 1 |
| 4 used / 5 | 4 | 100 | 1 | 0 |

`cr_london_kept(21000, 100000) = 6300`: EIP-3529 keeps 6300 extra gas consumed
versus the pre-London 50% cap. User-paid gas on that vector is 10500 → 16800.

## What this clone improves versus Geth

1. `ChainConfig.IsLondon` / `state.GetRefund` / `st.gasUsed()` become explicit
   integer arguments `used` / `state_refund` / `london`.
2. `initialGas - gasRemaining` is underflow-checked. Pinned Geth v1.16.9
   uint64-wraps when `remaining > initial`. LIN fail-closes used and refund to 0.
   The wrap is **not reachable** while the `remaining <= initial` invariant
   holds; it is a defect of the unbounded subtraction, not a mainnet consensus
   bug.
3. Overflow of `remaining + refund` fail-closes at i64max (`MaxGasLimit`).
4. `cr_london_kept` is a first-class value for the 50%→20% schedule change.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Full uint64 wrap semantics above `MaxGasLimit`
- Compiler 0 executing `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `geth_calcrefund_evidence.json`
(produced by the harness; do not hand-edit).
