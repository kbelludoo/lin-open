# Maker/Sky Vat.move — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.move` (internal DAI / rad transfer with src-only `wish`).

The LIN copy lives in a **separate** repository:
**[kbelludoo/clone-lin-maker-vat-move](https://github.com/kbelludoo/clone-lin-maker-vat-move)**

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` AGPL-3.0-or-later, commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
- **LIN kernel (also in this tree for the harness):** `src/lin_maker_vat_move.lin`
- **C11 oracle:** `test/oracles/maker_vat_move_c11.c`
- **Harness:** `python3 test/prove_maker_vat_move_external.py` or `make maker-vat-move-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_MOVE_CLONE_LIN.rulel`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not vat.flux (gem wad).

## What is claimed

Experimental, uint64-scale reproduction of Maker `move`: `dai[src] -= rad; dai[dst] += rad` after `wish(src, msg.sender)`. Real deltas versus the Solidity vat in this profile:

1. `dai[usr]` storage and `wish`/`msg.sender` are function arguments.
2. Sequential `_sub` then `_add`: a same-slot self-move is identity. A naive parallel `add_ok(dst, rad)` on the original dst would reject `7e18+3e18` even though Solidity accepts it.
3. Unsigned `_add`/`_sub` fail-close to 0 instead of reverting; naive i64 `7e18+3e18` wraps, checked add does not.
4. Src-only wish is explicit: destination cannot refuse incoming dai (`dst_consent_required=0`).
5. `live` is not required (move still works after `cage`); unit is rad, gem is untouched.

## What is not claimed

- Solidity **uint256** / mainnet dai-rad parity
- LIN replacing Maker, Sky, vat, or the EVM
- TVL or dollar savings from DAI transfers
- Computational soundness of Merkle / zk
- Address identity beyond the explicit same-slot `src==dst` case
- `vat.flux` (gem wad) — already cloned separately

Machine-written evidence for a given run is in `maker_vat_move_evidence.json` (produced by the harness; do not hand-edit).
