# Compound JumpRateModel V2 — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Compound v2's
JumpRateModel. The LIN clone itself is `src/lin_compound_jumprate.lin` in lin-open
(a separate clone-lin GitHub repository was not available in this run).

- **Upstream:** [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) `contracts/BaseJumpRateModelV2.sol` (BSD-3-Clause)
- **LIN clone (this tree):** [`src/lin_compound_jumprate.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-1e91/src/lin_compound_jumprate.lin)
- **Separate clone-lin repo:** not created in this run (GitHub repository-create was unavailable). The LIN clone is the in-tree file above, with proofs only in lin-open.
- **Pinned fixture:** `test/fixtures/external_proof/BaseJumpRateModelV2.sol`
- **C11 oracle:** `test/oracles/compound_jumprate_c11.c`
- **Harness:** `python3 test/prove_compound_jumprate_external.py`
- **Independent re-proof (Python exact, not C11 limbs):** `python3 test/prove_compound_improvements_independent.py`
- **Event receipt:** `docs/events/EVENT_COMPOUND_JUMPRATE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Compound's utilization and jump-rate
formulas, with 128-bit `(a*b)/d`, checked against an independent C11 `__int128`
oracle and Compiler 0 (interpreted LinVM and, when libtcc is present, in-memory
JIT). Storage parameters are function arguments.

## What is not claimed

Mainnet uint256 parity, EVM replacement, or TVL impact.

Machine-written evidence for a given run is in `compound_jumprate_evidence.json`
(produced by the harness; do not hand-edit).
