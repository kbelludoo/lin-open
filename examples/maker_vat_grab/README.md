# Maker/Sky Vat.grab — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Vat.grab` (CDP confiscation). The LIN copy also lives in a separate clone-lin
repository.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/vat.sol` (AGPL-3.0-or-later), commit `fa4f6630afb0624d04a003e920b0d71a00331d98` — **not vendored**
- **Clone-LIN repo:** [kbelludoo/clone-lin-maker-vat-grab](https://github.com/kbelludoo/clone-lin-maker-vat-grab)
- **LIN clone (this tree, for the harness):** [`src/lin_maker_vat_grab.lin`](../../src/lin_maker_vat_grab.lin)
- **C11 oracle:** `test/oracles/maker_vat_grab_c11.c`
- **Harness:** `python3 test/prove_maker_vat_grab_external.py` or `make maker-vat-grab-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_VAT_GRAB_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY' = 1e9`) reproduction of Maker `grab`:
signed `ink`/`art` updates, `dtab = rate * dart`, `_sub` into `gem`/`sin`/`vice`.
Real deltas versus the Solidity vat in this profile:

1. Storage (`ink`, `art`, `Art`, `rate`, `gem[v]`, `sin[w]`, `vice`) is
   function arguments, not hidden mappings / `auth`.
2. No `live == 1` gate (unlike `frob`). Confiscation math remains defined after cage.
3. Underwater urns (`tab > ink * spot`) stay `grab_ok = 1`. That is the liquidation
   seize Dog/Clipper uses; `frob` would reject the same overdraw.
4. `(a*b)` uses a 128-bit product. If the product does not fit uint64 the clone
   fail-closes to 0 instead of wrapping.

Named goldens: BARK seize `1e9` ink+art → **grab_ok=1**, clipper `gem=1e9`,
`vice=1e18`; UNDERWATER art `2e9` on ink `1e9` → **underwater=1** and still
**grab_ok=1**, unbacked **vice=2e18**; ink underflow `dink=-1` on `ink=0` → **0**;
naive i64 `7e18*3e18` wraps to **-5389669316318724096**; 128-bit muldiv fail-closes to **0**.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / wad×ray rad parity
- LIN replacing Maker, Sky, vat, Dog, Clipper, or the EVM
- TVL or dollar savings from liquidation
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_vat_grab_evidence.json`
(produced by the harness; do not hand-edit).
