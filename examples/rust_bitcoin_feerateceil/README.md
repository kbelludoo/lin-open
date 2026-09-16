# rust-bitcoin Amount::div_by_fee_rate_ceil — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of rust-bitcoin's
`Amount::div_by_fee_rate_ceil`. The LIN clone itself is
`src/lin_rust_bitcoin_feerateceil.lin` in lin-open.

- **Upstream:** [rust-bitcoin/rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin) `units/src/amount/unsigned.rs` (CC0-1.0) commit `1cbf4bd62ea99c558c6d8ef794edbd984a2a4684`
- **LIN clone (this tree):** [`src/lin_rust_bitcoin_feerateceil.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-18a2/src/lin_rust_bitcoin_feerateceil.lin)
- **Separate clone-lin repo:** [kbelludoo/clone-lin-rust-bitcoin-feerateceil](https://github.com/kbelludoo/clone-lin-rust-bitcoin-feerateceil) (created this run; kernel files also live in lin-open because the bot cannot push into that repo)
- **Pinned fixtures:** `test/fixtures/external_proof/rust_bitcoin_amount_unsigned.rs`, `rust_bitcoin_fee.rs`, `rust_bitcoin_fee_rate_mod.rs`
- **C11 oracle:** `test/oracles/rust_bitcoin_feerateceil_c11.c`
- **Harness:** `python3 test/prove_rust_bitcoin_feerateceil_external.py`
- **Event receipt:** `docs/events/EVENT_RUST_BITCOIN_FEERATECEIL_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of rust-bitcoin's fee-budget-to-weight
ceil. The real deltas versus the upstream API in this profile are:

1. `Amount / FeeRate` is **floor**. Ceil is the minimum weight that covers the
   fee: 1000 sat at 3 sat/kwu is 333333 wu (floor) vs **333334 wu** (ceil).
2. Remainder ceil, not `(a + d - 1) / d`, so `a + d - 1` cannot wrap.
3. FeeRate inner sat/MvB is a function argument. `1 sat/MvB` ceil-converts to
   `1 sat/kwu` (4000× vs floor 0) — an explicit detector, not a silent newtype.

## What is not claimed

- A production wallet or rust-bitcoin replacement
- u64::MAX FeeRate range
- LIN replacing Bitcoin Core
- `lin_c0 vm` of string-literal transpiler modules (`VM_REJ_STRING_LITERAL`)

Machine-written evidence for a given run is in `rust_bitcoin_feerateceil_evidence.json`
(produced by the harness; do not hand-edit).
