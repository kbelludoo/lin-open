# Maker/Sky Vat.fork — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.fork` (dual-consent CDP split of `ink`/`art` between urns). The LIN copy
also lives in a separate clone-lin repository.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later), commit `fa4f6630afb0624d04a003e920b0d71a00331d98` — **not vendored**
- **Clone-LIN repo:** [kbelludoo/clone-lin-maker-vat-fork](https://github.com/kbelludoo/clone-lin-maker-vat-fork) HEAD `ea4688430ede84ba6c07ccbe819cb349b6fa9884` (LIN blob `0fdee0df`, C blob `db7d22a7`)
- **LIN clone (this tree, for the harness):** [`src/lin_maker_vat_fork.lin`](../../src/lin_maker_vat_fork.lin)
- **C11 oracle:** `test/oracles/maker_vat_fork_c11.c`
- **Harness:** `python3 test/prove_maker_vat_fork_external.py` or `make maker-vat-fork-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_FORK_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY' = 1e9`) reproduction of Maker `fork`:
signed `_sub`/`_add` of `ink`/`art` on two urns, then both sides must stay
safe (`art * rate <= ink * spot`) and non-dusty, with dual `wish` consent.
Real deltas versus the Solidity vat in this profile:

1. Storage (`urns[src]`, `urns[dst]`, `ilks.rate/spot/dust`) and dual `wish`
   are function arguments, not hidden mappings / `msg.sender`.
2. No `live == 1` and no `wards`/auth (unlike `frob` / `suck`). Missing
   consent fail-closes to `fork_ok = 0`.
3. Dual safety + dual dust after the split. Ink and art are conserved.
4. Signed `dink`/`dart` overflow/underflow fail-closes instead of wrapping.

Named goldens: SAFE_SPLIT `dink=1e9 dart=5e8` on `u=5e9/2e9 v=3e9/1e9`
rate=spot=1e9 dust=1e18 wish=1,1 → **fork_ok=1**, both vaults `4e9/1.5e9`;
UNSAFE_DST thin collateral → **0**; leftover tab below dust → **0**;
no-wish → **0**; signed negative dink moves ink dst→src; naive i64
`7e18*3e18` wraps, 128-bit muldiv fail-closes to **0**.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray tab parity
- LIN replacing Maker, Sky, vat, or the EVM
- TVL or dollar savings from CDP splits
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_vat_fork_evidence.json`
(produced by the harness; do not hand-edit).
