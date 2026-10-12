# Geth EIP-7702 call-variant gas — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of go-ethereum's
Pectra `makeCallVariantGasCallEIP7702`. The full LIN clone is published in a
separate repository; lin-open keeps proofs and the clone-lin link.

- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` (LGPL-3.0)
- **LIN clone (this tree):** [`src/lin_geth_eip7702.lin`](../../src/lin_geth_eip7702.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-geth-eip7702
- **Pinned excerpts:** `test/fixtures/external_proof/gasCallEIP7702.go`, `parseDelegation.go`, `enable7702.go`
- **C11 oracle:** `test/oracles/geth_eip7702_c11.c`
- **Go oracle:** `test/oracles/geth_eip7702_go.go`
- **Harness:** `python3 test/prove_geth_eip7702_external.py`
- **Event receipt:** `docs/events/EVENT_GETH_EIP7702_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of the **named contrast** vs EIP-2929:

1. Shared Pectra wrapper: charge Berlin cold-warm `2500` via `UseGas` if the
   call target is cold, **then** charge `100` (warm) or `2600` (full cold, not
   2500) if `ParseDelegation` succeeds, **then** EIP-150 63/64, then add the
   precharge back. Opcode total = `100 + dynamic`.
2. `ParseDelegation` is `len==23 && prefix 0xef0100`. LIN lifts that to
   `e7702_parse_ok(code_len, prefix_ok)` — no `[]byte`.
3. Because 63/64 runs **after** the extra 100/2600, a 64000-gas 63/64-bound
   CALL is **+2** (warm target) or **+41** (cold target) vs 2929, not +100/+2600.
   A requested-bound CALL (`req=1000`) **does** add the full 2600.
4. A fee estimator that copies 2929 onto 7702 delegated CALLs undercharges.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Quadratic `memoryGasCost` / Cmem (memory_gas is an explicit integer)
- CallStipend 2300, EIP-4762 Verkle, byte-level code parsing
- uint256 / full-node parity

Machine-written evidence for a given run is in `geth_eip7702_evidence.json`
(produced by the harness; do not hand-edit).
