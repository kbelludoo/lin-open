# Compound JumpRateModel V2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2's
JumpRateModel. The LIN clone itself is `src/lin_compound_jumprate.lin`.

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/BaseJumpRateModelV2.sol` (BSD-3-Clause)
- **LIN clone:** [`src/lin_compound_jumprate.lin`](../../src/lin_compound_jumprate.lin)
- **Pinned fixture:** `test/fixtures/external_proof/BaseJumpRateModelV2.sol`
- **C11 oracle:** `test/oracles/compound_jumprate_c11.c`
- **Harness:** `python3 test/prove_compound_jumprate_external.py` (also `make compound-jumprate-proof`)
- **Event receipt:** `docs/events/EVENT_COMPOUND_JUMPRATE_CLONE_LIN.rulel`

## What is claimed (experimental, uint64-scale)

Utilization / jump-rate formulas with 128-bit `(a*b)/d`, checked this run against:

1. independent C11 `__int128` and portable 32-bit limbs
2. independent Python arbitrary-precision integers
3. Compiler 0 interpreter (`lin_c0 vm`)
4. in-memory libtcc JIT when `libtcc.so` + `libtcc1.a` are present (`roundtrip-jit CONSENSUS`)

IRM storage parameters are function arguments. Naive wrapping `uint64` multiply of `1e18*1e18` is shown to disagree with the wide path.

## What is not claimed

- Mainnet Solidity uint256 / cToken parity
- EVM replacement or TVL impact
- Runtime execution of `sol_from_sol` / `sol_from_sol_gate` on Compiler 0 (C0 integer VM refuses string literals: `VM_REJ_STRING_LITERAL`)

Machine-written evidence for a given run is in `compound_jumprate_evidence.json`
(produced by the harness; do not hand-edit).
