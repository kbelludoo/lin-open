# Maker/Sky Vat.flux — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.flux` (unlocked collateral / gem transfer with src-only `wish`).

The LIN copy lives in a **separate** repository:
**[kbelludoo/clone-lin-maker-vat-flux](https://github.com/kbelludoo/clone-lin-maker-vat-flux)**

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` AGPL-3.0-or-later, commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
- **LIN kernel (also in this tree for the harness):** `src/lin_maker_vat_flux.lin`
- **C11 oracle:** `test/oracles/maker_vat_flux_c11.c`
- **Harness:** `python3 test/prove_maker_vat_flux_external.py` or `make maker-vat-flux-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_FLUX_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not vat.move (dai rad). Not vat.fork.

## What is claimed

Experimental, uint64-scale reproduction of Maker `flux`: `gem[ilk][src] -= wad; gem[ilk][dst] += wad` after `wish(src, msg.sender)`. Real deltas versus the Solidity vat in this profile:

1. `gem[ilk][usr]` storage and `wish`/`msg.sender` are function arguments.
2. Unsigned `_add`/`_sub` fail-close to 0 instead of reverting; naive i64 `7e18+3e18` wraps, checked add does not.
3. Src-only wish is explicit: destination cannot refuse incoming gem (`dst_consent_required=0`).
4. `live` is not required (flux still works after `cage`); LIN measures `live_required=0`.
5. Gem is conserved: leftover_src + leftover_dst equals src + dst when `flux_ok=1`.

## What is not claimed

- Solidity **uint256** / mainnet gem-wad parity
- LIN replacing Maker, Sky, vat, or the EVM
- TVL or dollar savings from gem transfers
- Computational soundness of Merkle / zk
- Address identity (src and dst balances are independent arguments)
- `vat.move` (dai rad) — still open on the clone-lin queue

Machine-written evidence for a given run is in `maker_vat_flux_evidence.json` (produced by the harness; do not hand-edit).
