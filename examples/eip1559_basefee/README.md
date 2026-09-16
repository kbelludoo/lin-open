# EIP-1559 CalcBaseFee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Ethereum's
EIP-1559 base-fee update. The LIN clone in this tree is
`src/lin_eip1559_basefee.lin`. The full clone-lin copy lives in a **separate**
repository:

- **Clone-lin (LIN copy):** https://github.com/kbelludoo/clone-lin-eip1559-basefee
- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.14.12` commit `293a300d64be3d9a1c2cc92c26fcff4089deadcd` `consensus/misc/eip1559/eip1559.go` (LGPL-3.0)
- **Pinned fixture:** `test/fixtures/external_proof/eip1559.go`
- **C11 scalar restatement (transpile input):** `test/fixtures/external_proof/eip1559_integer.c`
- **C11 oracle:** `test/oracles/eip1559_basefee_c11.c`
- **Harness:** `python3 test/prove_eip1559_basefee_external.py` or `make eip1559-basefee-proof`
- **Event receipt:** `docs/events/EVENT_EIP1559_BASEFEE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Geth's `CalcBaseFee` after London:

`new = parent ± max(floor(floor(parent_fee * |used-target| / target) / denom), floor_min)`

with `target = gas_limit / elasticity`, `elasticity=2`, `denom=8`,
`InitialBaseFee=1e9` from `params/protocol_params.go`. Canonical vector:
parent fee 1 gwei, gas limit 30M, full block → **1_125_000_000** wei.

Real deltas versus Geth in this profile:

1. `*params.ChainConfig` and `*types.Header` become explicit integer arguments
   (`elasticity`, `denom`, `london`).
2. `(fee * gas_delta) / target` uses a 128-bit product (schoolbook limbs in LIN,
   `__int128` in the C11 oracle). Naive uint64 multiply wraps on
   `1e13 * 15e6`; the clone does not.
3. Negatives and zero elasticity/denominator fail-closed to 0.

## What is not claimed

- Solidity / EVM **uint256** or a replacement Geth node
- LIN replacing Ethereum's fee market
- General superiority vs gc/LLVM
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `eip1559_basefee_evidence.json`
(produced by the harness; do not hand-edit).
