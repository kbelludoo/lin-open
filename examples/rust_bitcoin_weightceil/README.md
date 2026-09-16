# rust-bitcoin Amount::div_by_weight_ceil — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of rust-bitcoin's
minimum-sufficient fee-rate math. The LIN kernel is
`src/lin_rust_bitcoin_weightceil.lin` in lin-open.

- **Upstream:** [rust-bitcoin/rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin) `units/src/amount/unsigned.rs` (CC0-1.0) commit `1cbf4bd62ea99c558c6d8ef794edbd984a2a4684`
- **LIN clone (this tree):** [`src/lin_rust_bitcoin_weightceil.lin`](../../src/lin_rust_bitcoin_weightceil.lin)
- **Separate clone-lin repo:** not created in this run (`createRepository` is not accessible). The LIN clone is the in-tree file above; proofs stay in lin-open.
- **Pinned fixture:** `test/fixtures/external_proof/rust_bitcoin_amount_unsigned.rs`
- **C11 oracle:** `test/oracles/rust_bitcoin_weightceil_c11.c`
- **Harness:** `python3 test/prove_rust_bitcoin_weightceil_external.py`
- **Event receipt:** `docs/events/EVENT_RUST_BITCOIN_WEIGHTCEIL_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of
`Amount::div_by_weight_ceil`: `(sats * 4_000_000).div_ceil(wu)` in sat/MvB.

Published rust-bitcoin goldens this clone must match:

| sats | wu | floor sat/MvB | ceil sat/MvB |
|---|---|---|---|
| 1 | 1000 | 4000 | 4000 |
| 329 | 381 | 3454068 | **3454069** |
| 10 | 200 | 200000 | 200000 |
| 10 | 300 | 133333 | 133334 |

Real deltas versus the Rust API in this profile:

1. `ops::Div<Weight> for Amount` is **floor**. Ceil is the rate that actually
   covers the fee. LIN names ceil and reports `rwc_floor_underpay=1` on 329/381.
2. `(sats * 4e6)` overflows i64 on `MAX_MONEY`; LIN uses a 128-bit product and
   fail-closes if the FeeRate does not fit i64 (`None` encoded as `-1`).
3. A ceil increment that would wrap i64 (`q+1 <= 0`) fail-closes instead of
   becoming a negative rate.

## What is not claimed

- rust-bitcoin **wallet / PSBT / script / network**
- **u64** FeeRate / **u128** as in rustc (this clone is i64 + 128-bit schoolbook)
- LIN replacing rust-bitcoin or Bitcoin Core
- General superiority vs rustc
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in
`rust_bitcoin_weightceil_evidence.json` (produced by the harness; do not hand-edit).
