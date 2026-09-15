# Compound JumpRateModel V2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2's
JumpRateModel. The LIN clone itself is [`src/lin_compound_jumprate.lin`](../../src/lin_compound_jumprate.lin).

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/BaseJumpRateModelV2.sol` (BSD-3-Clause), commit `a3214f67b73310d547e00fc578e8355911c9d376`
- **Pinned fixture:** `test/fixtures/external_proof/BaseJumpRateModelV2.sol`
- **C11 oracle:** `test/oracles/compound_jumprate_c11.c`
- **Python bigint oracle:** `test/oracles/compound_jumprate_py.py`
- **Harness:** `python3 test/prove_compound_jumprate_external.py`
- **Edges (jump / supply / fail-closed / fuzz):** `python3 test/prove_compound_jumprate_edges.py`
- **Independent third oracle:** `python3 test/prove_melhorias_independent.py`
- **Event receipt:** `docs/events/EVENT_COMPOUND_JUMPRATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound's utilization and jump-rate
formulas. Storage parameters are function arguments. `(a*b)/d` uses a 128-bit
product. Quotients that do not fit non-negative signed i64 fail closed to 0.
Checked against Python bigint, C11 `__int128`, Compiler 0 VM, and (when libtcc
is present) in-memory JIT.

## What is not claimed

Mainnet uint256 / cToken parity, EVM replacement, TVL impact, general speed vs
solc/LLVM, or zk soundness of Merkle receipts.

Machine-written evidence for a given run is in `compound_jumprate_evidence.json`
and `independent_reproof.json` (produced by the harnesses; do not hand-edit).
