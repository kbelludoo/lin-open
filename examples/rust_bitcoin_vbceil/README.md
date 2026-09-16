# rust-bitcoin FeeRate sat/vB ceil — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of rust-bitcoin's
`FeeRate` sat/MvB unit conversions (`to_sat_per_vb_ceil` / floor, sat/kwu, sat/kvb).
The LIN kernel is `src/lin_rust_bitcoin_vbceil.lin` in lin-open. The LIN copy of
the kernel is published in a separate clone-lin repository.

- **Upstream:** [rust-bitcoin/rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin) `units/src/fee_rate/mod.rs` (CC0-1.0)
- **Pinned commit:** `cb2404331101acac9df5a07487ea6f3ed1828037`
- **LIN clone (this tree):** [`src/lin_rust_bitcoin_vbceil.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-52b9/src/lin_rust_bitcoin_vbceil.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-rust-bitcoin-vbceil
- **Pinned fixture:** `test/fixtures/external_proof/rust_bitcoin_fee_rate_mod.rs`
- **C11 oracle:** `test/oracles/rust_bitcoin_vbceil_c11.c`
- **Harness:** `python3 test/prove_rust_bitcoin_vbceil_external.py`
- **Event receipt:** `docs/events/EVENT_RUST_BITCOIN_VBCEIL_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of rust-bitcoin `FeeRate` constructors and
ceil/floor conversions. The real deltas versus the Rust API in this profile are:

1. The `FeeRate` newtype / `self` receiver is an explicit `sat_mvb` argument.
2. `u64::div_ceil` is remainder-based. Naive `(n + d - 1) / d` wraps at
   `u64::MAX` (C11 unsigned: naive result 0 vs rem ceil 18446744073710). LIN
   never forms `n+d-1`.
3. Constructors fail-closed outside the rust `u32` input domain (negative or
   `> u32::MAX` → 0) instead of wrapping a `u32` cast.

## What is not claimed

- Full `u64` `FeeRate::MAX` domain (LIN Compiler 0 integers are i64)
- LIN replacing rust-bitcoin, Bitcoin Core mempool policy, or a wallet
- Wall-clock superiority vs rustc/LLVM
- That in-memory libtcc JIT ran on a host without libtcc

Machine-written evidence for a given run is in `rust_bitcoin_vbceil_evidence.json`
(produced by the harness; do not hand-edit).
