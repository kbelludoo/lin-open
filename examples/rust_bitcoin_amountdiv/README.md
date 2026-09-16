# rust-bitcoin Amount::checked_div — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of rust-bitcoin's
unsigned `Amount` integer division. The LIN clone itself is
`src/lin_rust_bitcoin_amountdiv.lin` in lin-open.

- **Upstream:** [rust-bitcoin/rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin) `units/src/amount/unsigned.rs` (CC0-1.0)
- **Pinned commit:** `1cbf4bd62ea99c558c6d8ef794edbd984a2a4684`
- **LIN clone (this tree):** [`src/lin_rust_bitcoin_amountdiv.lin`](../../src/lin_rust_bitcoin_amountdiv.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-rust-bitcoin-amountdiv
- **Pinned fixture:** `test/fixtures/external_proof/rust_bitcoin_amount_unsigned.rs`
- **C11 oracle:** `test/oracles/rust_bitcoin_amountdiv_c11.c`
- **Harness:** `python3 test/prove_rust_bitcoin_amountdiv_external.py`
- **Event receipt:** `docs/events/EVENT_RUST_BITCOIN_AMOUNTDIV_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of:

1. `Amount::from_sat` — reject above `21_000_000 * 100_000_000` (MAX_MONEY).
2. `Amount::checked_div` / `checked_rem` — `None` (encoded `-1`) iff divisor is 0.
   Remainder identity `sat = q*rhs + r` is a first-class LIN function.
3. `div_by_weight_floor` — `(sats * 4_000_000) / wu` as sat/MvB using a 128-bit
   product. Naive signed i64 wraps on `MAX_MONEY * 4e6`.

## What is not claimed

- A rust-bitcoin wallet, PSBT, or script interpreter
- LIN replacing rust-bitcoin or Bitcoin Core
- General superiority vs rustc/LLVM
- That Compiler 0 interprets string-literal transpiler modules
  (`VM_REJ_STRING_LITERAL`); `lin_from_rust` / `lin_from_c` emit paths are
  typechecked, not executed by `lin_c0 vm`

Machine-written evidence for a given run is in
`rust_bitcoin_amountdiv_evidence.json` (produced by the harness; do not hand-edit).
