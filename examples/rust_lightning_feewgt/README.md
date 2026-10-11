# rust-lightning fee_for_weight (253 sat/kW floor) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of LDK's
on-chain fee from sats-per-kilo-weight. The LIN clone itself is
`src/lin_rust_lightning_feewgt.lin` in lin-open. The standalone LIN copy
lives in a separate repository:

- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-rust-lightning-feewgt

- **Upstream:** [lightningdevkit/rust-lightning](https://github.com/lightningdevkit/rust-lightning) tag `v0.2.7` commit `5ce2ecb33d32e3b61ef01d5ead0ee6693c0cd7d1` `lightning/src/chain/chaininterface.rs` `fee_for_weight` (Apache-2.0 OR MIT)
- **Pinned excerpt:** `test/fixtures/external_proof/fee_for_weight.rs`
- **C11 oracle:** `test/oracles/rust_lightning_feewgt_c11.c`
- **Rust oracle:** `test/oracles/rust_lightning_feewgt.rs`
- **Harness:** `python3 test/prove_rust_lightning_feewgt_external.py` or `make rust-lightning-feewgt-proof`
- **Event receipt:** `docs/events/EVENT_RUST_LIGHTNING_FEEWGT_CLONE_LIN.rulel`

## Canonical vectors (v0.2.7)

| feerate (sat/kW) | weight (WU) | fee (sat) |
|---|---:|---:|
| 253 | 1000 | **253** |
| 253 | 1 | 1 |
| 1 | 999 | 1 |
| 1 | 1001 | 2 |
| 253 | 440 | **112** (P2WPKH-sized, LDK floor) |
| 2530 | 440 | 1114 |
| 253 | 0 | **0** (fail-closed; Rust panics) |
| 4294967295 | 2147483649 | **0** (i64 product overflow) |

`fw_p2wpkh_floor() = 112` is `ceil(253 * 440 / 1000)` — the fee LDK posts
for a 110 vB / 440 WU spend at the 1 sat/vB floor after Core Lightning's
weight-to-vbyte rounding (`FEERATE_FLOOR_SATS_PER_KW = 253`).

This is **not** BOLT-07 routing `ComputeFee` (lnd
`fee_base_msat + amt * ppm / 1e6`). It is the on-chain
`sats/kW * weight` used for commitment, HTLC, splice, and sweep
transactions.

## What this clone improves versus rust-lightning v0.2.7

1. `((feerate as u64 * weight) + 1000 - 1) / 1000` becomes remainder
   ceil (`q = prod/1000; if rem != 0 { q+1 }`) — no `+999` overflow.
2. `feerate * weight` overflow fail-closes to 0 instead of wrapping u64.
3. `weight == 0` fail-closes to 0 instead of dividing by zero / panicking.
4. `compute_feerate` saturates to `u32::MAX` on overflow instead of
   wrap-then-`try_into().unwrap_or(u32::max_value())`.
5. The 253 sat/kW floor is an explicit `fw_bounded(est)` argument, not a
   `FeeEstimator` trait object.

## What is not claimed

- LIN replacing rust-lightning, LDK, Phoenix, Breez, or a Lightning node
- BOLT-07 routing fee / lnd `ComputeFee` parity
- rust-bitcoin `FeeRate::to_sat_per_vb_ceil` / `div_by_weight_ceil`
- Compiler 0 executing `rs_from_rs` string-literal paths (`VM_REJ_STRING_LITERAL`)
- Computational soundness of Merkle / zk receipts

Class: **EXPERIMENTAL** (real published algorithm, i64-scale operands).
Machine-written evidence for a given run is in `rust_lightning_feewgt_evidence.json`
(produced by the harness; do not hand-edit).
