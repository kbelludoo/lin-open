# Bitcoin Core v27.1 dust policy — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Bitcoin Core's
`GetDustThreshold` / `IsDust`. The LIN sources stay in lin-open; the full
clone-lin copy is a separate public repository.

- **Upstream:** [bitcoin/bitcoin](https://github.com/bitcoin/bitcoin) tag `v27.1` commit `1088a98f5aad080cc6cca2da174f206509fcda6c` (MIT)
- **LIN clone (this tree):** [`src/lin_bitcoin_core_dust.lin`](https://github.com/kbelludoo/lin-open/blob/cursor/linguagem-lin-e-valida-o-766a/src/lin_bitcoin_core_dust.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-bitcoin-core-dust
- **Pinned excerpt:** `test/fixtures/external_proof/bitcoin_core_v27_1_dust_excerpt.cpp`
- **C11 oracle:** `test/oracles/bitcoin_core_dust_c11.c`
- **Harness:** `python3 test/prove_bitcoin_core_dust_external.py`
- **Event receipt:** `docs/events/EVENT_BITCOIN_CORE_DUST_CLONE_LIN.rulel`

## What is claimed (EXPERIMENTAL)

Default Core `DUST_RELAY_TX_FEE = 3000` sat/kvB, integer-ceil `GetFee`, CompactSize
for `script_len < 253`:

| output type | script_len | witness? | nSize | dust (sat) |
|---|---|---|---|---|
| P2PKH | 25 | no | 182 | **546** |
| P2SH | 23 | no | 180 | **540** |
| P2WPKH | 22 | yes | 98 | **294** |
| P2TR / P2WSH | 34 | yes | 110 | **330** |

`IsDust` is `nValue < threshold`. A 545 sat P2PKH output is dust; 546 is not.
Unspendable scripts have threshold 0, so a 1 sat OP_RETURN is not dust under this
predicate.

Core `GetFee` uses `std::ceil(double)`. On the dust-scale grid the C11 oracle
checks integer ceil against IEEE ceil. Negative fee rates fail-closed to -1.

Taproot still uses the P2WPKH 107-byte dummy spend ([bitcoin/bitcoin#22779](https://github.com/bitcoin/bitcoin/pull/22779)),
so P2TR dust is 330 sat at the default rate, not a BIP340 keypath figure.

## What is not claimed

- LIN replacing bitcoind, a wallet, or consensus
- IEEE ceil == integer ceil outside the measured grid
- GetSerializeSize of arbitrary scripts / CompactSize of huge scripts
- wall-clock superiority vs gcc or bitcoind

Machine-written evidence for a given run is in `bitcoin_core_dust_evidence.json`
(produced by the harness; do not hand-edit).
