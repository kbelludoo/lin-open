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
- **Independent third oracle (this run):** `python3 test/prove_melhorias_independent.py` (Python bigint vs LIN vs C11)
- **Event receipt:** `docs/events/EVENT_COMPOUND_JUMPRATE_CLONE_LIN.rulel`
- **Harden event:** `docs/events/EVENT_COMPOUND_JUMPRATE_HARDEN_2026_09_15.rulel`
- **Independent re-proof event:** `docs/events/EVENT_INDEPENDENT_REPROOF_2026_09_15.rulel`
- **View-storage lift (experimental):** `src/lin_sol_view_lift.lin` — extra args only, not 128-bit muldiv

## What is claimed

Experimental, uint64-scale reproduction of Compound's utilization and jump-rate
formulas. The real deltas versus the Solidity IRM in this profile are:

1. Storage parameters (`baseRatePerBlock`, `multiplierPerBlock`,
   `jumpMultiplierPerBlock`, `kink`) are function arguments, not hidden
   contract storage / `msg.sender`.
2. `(a*b)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128` in
   the C11 oracle). If the quotient does not fit in uint64 the clone
   fail-closes to 0 instead of wrapping. Remainder identity `a*b = q*d + r`
   is checked by an independent Python bigint oracle.

## What is not claimed

- Solidity **uint256** / mainnet **cToken** parity
- LIN replacing Compound, Uniswap, or the EVM
- General superiority vs solc/LLVM (a SipHash ~20.8× figure is
  compile-turnaround on one host, not a kernel benchmark)
- Computational soundness of Merkle / zk (C4 is tamper-evidence plus
  re-execution of `lin_c_receipt`; the first C4 fail on PR 79 was a missing
  binary, not false math)

Machine-written evidence for a given run is in `compound_jumprate_evidence.json`
and `independent_reproof.json` (produced by the harness; do not hand-edit).
