# Ethereum consensus-spec base reward — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Ethereum's
consensus-spec `integer_squareroot` (Phase 0 helper, still current) and Altair
`get_base_reward` / `get_base_reward_per_increment`.

- **Upstream:** [ethereum/consensus-specs](https://github.com/ethereum/consensus-specs) tag `v1.5.0` commit `b5c3b619887c7850a8c1d3540b471092be73ad84` (CC0-1.0)
- **LIN clone (this tree):** [`src/lin_eth_base_reward.lin`](../../src/lin_eth_base_reward.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-eth-basereward
- **Pinned fixtures:** `test/fixtures/external_proof/beacon-chain-phase0.md`, `beacon-chain-altair.md`
- **C11 oracle:** `test/oracles/eth_base_reward_c11.c`
- **Harness:** `python3 test/prove_eth_base_reward_external.py`
- **Event receipt:** `docs/events/EVENT_ETH_BASE_REWARD_CLONE_LIN.rulel`

## What is claimed

Experimental reproduction of the published uint64 Gwei helpers:

1. BeaconState fields are function arguments (`effective_balance`, `total_balance`).
2. Integer square root uses overflow-safe `floor((a+b)/2)` plus the spec's
   `UINT64_MAX → 4294967295` special case (LIN encodes `UINT64_MAX` as i64 `-1`).
3. `total_balance == 0` fail-closes to 0 (the spec's `get_total_balance` mins at
   1 ETH; naive C division is undefined).

Canonical vector (Altair): 1 validator, 32 ETH effective, 32 ETH total →
**11448672 Gwei** per epoch. Class: **EXPERIMENTAL**, not a beacon node.

## What is not claimed

- A production beacon node / validator client
- Electra 2048 ETH max-effective-balance as a special case
- LIN replacing Prysm, Lighthouse, nimbus, or the EVM
- General wall-clock superiority
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `eth_base_reward_evidence.json`
(produced by the harness; do not hand-edit).
