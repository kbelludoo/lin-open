# Maker/Sky Vat.suck — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.suck` (auth unbacked DAI mint; inverse of `heal`). The LIN copy also lives
in a separate clone-lin repository.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later), commit `fa4f6630afb0624d04a003e920b0d71a00331d98` — **not vendored**
- **Clone-LIN repo:** [kbelludoo/clone-lin-maker-vat-suck](https://github.com/kbelludoo/clone-lin-maker-vat-suck)
- **LIN clone (this tree, for the harness):** [`src/lin_maker_vat_suck.lin`](../../src/lin_maker_vat_suck.lin)
- **C11 oracle:** `test/oracles/maker_vat_suck_c11.c`
- **Harness:** `python3 test/prove_maker_vat_suck_external.py` or `make maker-vat-suck-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_SUCK_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY' = 1e9`) reproduction of Maker `suck`:
unsigned `_add` of `sin[u]`, `dai[v]`, `vice`, and `debt` by the same `rad`,
gated on explicit `auth` (`wards == 1`). Real deltas versus the Solidity vat
in this profile:

1. Storage (`sin[u]`, `dai[v]`, `vice`, `debt`) and `wards`/auth are function
   arguments, not hidden mappings / `msg.sender`.
2. Auth is explicit. There is no `live == 1` gate (unlike `frob`). Unauth mint
   fail-closes to `suck_ok = 0`.
3. Four-way identity: `Δsin = Δdai = Δvice = Δdebt = rad` when `suck_ok = 1`.
4. Overflow of any of the four accounts fail-closes to `suck_ok = 0` instead
   of wrapping. `suck` then unsigned `_sub` (heal) restores the four accounts.

Named goldens: VOW suck `rad=1e18` on `sin=2e18 dai=3e18 vice=2e18 debt=5e18 auth=1`
→ **suck_ok=1**, new vice `3e18`; FULL_MINT `rad=2e18` → **new_vice=4e18**,
**minted=2e18**, leftover dai `5e18`; unauth `auth=0` → **0**;
sin overflow `7e18+3e18` → **0**; naive i64 `7e18+3e18` wraps to
**-8446744073709551616**; checked `u_add` fail-closes to **0**. Auth required,
no `live`. Inverse of `heal`.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray rad parity
- LIN replacing Maker, Sky, vat, Vow, or the EVM
- TVL or dollar savings from unbacked mint / flop auctions
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_vat_suck_evidence.json`
(produced by the harness; do not hand-edit).
