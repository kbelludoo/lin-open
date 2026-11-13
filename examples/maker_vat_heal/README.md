# Maker/Sky Vat.heal — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.heal` (surplus-buffer settlement). The LIN copy also lives in a separate
clone-lin repository.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later), commit `fa4f6630afb0624d04a003e920b0d71a00331d98` — **not vendored**
- **Clone-LIN repo:** [kbelludoo/clone-lin-maker-vat-heal](https://github.com/kbelludoo/clone-lin-maker-vat-heal)
- **LIN clone (this tree, for the harness):** [`src/lin_maker_vat_heal.lin`](../../src/lin_maker_vat_heal.lin)
- **C11 oracle:** `test/oracles/maker_vat_heal_c11.c`
- **Harness:** `python3 test/prove_maker_vat_heal_external.py` or `make maker-vat-heal-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_HEAL_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY' = 1e9`) reproduction of Maker `heal`:
unsigned `_sub` of `sin[u]`, `dai[u]`, `vice`, and `debt` by the same `rad`.
Real deltas versus the Solidity vat in this profile:

1. Storage (`sin[u]`, `dai[u]`, `vice`, `debt`) is function arguments, not
   hidden mappings / `msg.sender`.
2. No `live == 1` gate and no `auth` (unlike `frob` / `suck`). Settlement math
   remains defined after cage.
3. Four-way identity: `Δsin = Δdai = Δvice = Δdebt = rad` when `heal_ok = 1`.
4. Underflow of any of the four accounts fail-closes to `heal_ok = 0` instead
   of wrapping. Checked add of `new + rad` fail-closes when the restore does
   not fit uint64.

Named goldens: VOW heal `rad=1e18` on `sin=2e18 dai=3e18 vice=2e18 debt=5e18`
→ **heal_ok=1**, leftover dai `2e18`; FULL_SETTLE `rad=vice=2e18` → **new_vice=0**,
**settled=2e18**, leftover dai `1e18`; sin/dai/vice/debt underflow → **0**;
naive i64 `7e18+3e18` wraps to **-8446744073709551616**; checked `u_add`
fail-closes to **0**. No `live`/`auth`.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray rad parity
- LIN replacing Maker, Sky, vat, Vow, or the EVM
- TVL or dollar savings from surplus-buffer settlement
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_vat_heal_evidence.json`
(produced by the harness; do not hand-edit).
