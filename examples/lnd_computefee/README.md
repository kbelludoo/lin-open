# lnd BOLT07 ComputeFee — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Lightning
Labs' `lnd` HTLC forwarding fee. The LIN clone itself is
`src/lin_lnd_computefee.lin` in lin-open.

- **Upstream:** [lightningnetwork/lnd](https://github.com/lightningnetwork/lnd) `v0.21.3-beta` (MIT)
  - `graph/db/models/cached_edge_policy.go` `CachedEdgePolicy.ComputeFee` (BOLT 07)
  - `graph/db/models/inbound_fee.go` `InboundFee.CalcFee`
- **LIN clone (this tree):** [`src/lin_lnd_computefee.lin`](../../src/lin_lnd_computefee.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-lnd-computefee
- **Pinned fixtures:** `test/fixtures/external_proof/lnd_cached_edge_policy.go`, `lnd_inbound_fee.go`, `lnd_inbound_fee_test.go`
- **C11 oracle:** `test/oracles/lnd_computefee_c11.c`
- **Harness:** `python3 test/prove_lnd_computefee_external.py`
- **Event receipt:** `docs/events/EVENT_LND_COMPUTEFEE_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of BOLT 07 forwarding fees:

```
fee_msat = fee_base_msat + (amount_to_forward_msat * fee_proportional_millionths) / 1_000_000
```

and lnd inbound `CalcFee` (signed base/rate, toward-zero division, rate cap ±10×).

Real deltas versus the Go method:

1. Receiver fields (`FeeBaseMSat`, `FeeProportionalMillionths`) are function arguments.
2. `amt * ppm` uses a 128-bit product. Go `uint64` wraps; the clone fail-closes if the quotient does not fit uint64.
3. `1e6` is the integer `1000000` (BOLT `feeRateParts`).

## What is not claimed

- LIN replacing lnd, LDK, or a Lightning routing node
- Gossip, channel graph, HTLC state machines, or onion routing
- General superiority vs Go/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `lnd_computefee_evidence.json`
(produced by the harness; do not hand-edit).
