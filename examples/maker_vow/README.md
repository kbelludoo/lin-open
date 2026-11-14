# Maker/Sky Vow heal/kiss/flop/flap — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO
`Vow` surplus/debt settlement. The published LIN copy lives in a separate repository.

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/vow.sol` AGPL-3.0-or-later
  commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
  sha256 `609e5da454c0e68ce1c4dc7eb702a015139cd31305727604b777e13ea7bae302`
  blob `f28d699774ef830bcdc281df4530378a64f4071b`
- **Clone-LIN:** https://github.com/kbelludoo/clone-lin-maker-vow
- **LIN kernel (lin-open, for recomputing proofs):** `src/lin_maker_vow.lin`
- **C11 oracle:** `test/oracles/maker_vow_c11.c`
- **Pointer-free kernel:** `test/oracles/maker_vow_kernel.c`
- **Harness:** `python3 test/prove_maker_vow_external.py` / `make maker-vow-proof`
- **Class:** EXPERIMENTAL uint64-scale. Not mainnet uint256. Not a production Vow replacement.

## What is claimed

Experimental, uint64-scale reproduction of

- unqueued = sub(sub(vat.sin, Sin), Ash)
- heal: rad <= vat.dai AND rad <= unqueued
- kiss: rad <= Ash AND rad <= vat.dai; Ash' = sub(Ash, rad)
- flop: vat.dai == 0 AND sump <= unqueued; Ash' = add(Ash, sump)
- flap: vat.dai >= add(add(vat.sin, bump), hump) AND unqueued == 0

with `RAD'=1e9`. `vat.dai` / `vat.sin` / queued `Sin` / `Ash` / `bump` / `hump` / `sump` are arguments.
Wrapping add fail-closes to 0. `vat.heal` and `kick` are not executed.

Named goldens (uint64-scale, `RAD'=1e9`):

| id | inputs | result |
|---|---|---|
| heal 5e9 | dai=5e9 sin=10e9 Sin=3e9 Ash=1e9 | **1** |
| kiss Ash next | dai=3e9 Ash=2e9 rad=2e9 | **0** |
| flop Ash next | dai=0 sump=2e9 Ash=1e9 | **3000000000** |
| flap | dai=10e9 sin=0 bump=1e9 hump=2e9 | **1** |
| flap blocked by hump | dai=2e9 hump=2e9 | **0** |
| flap if hump=0 | dai=2e9 hump=0 | **1** |
| flap blocked by queued Sin | dai=5e9 sin=3e9 Sin=3e9 | **0** |

Distinct from `vat.heal` (clone-lin-maker-vat-heal) which cancels Dai/sin at the CDP engine.

## What is not claimed

- Solidity **uint256** / mainnet rad=wad×ray / RAY=1e27 parity
- LIN replacing Maker, Sky, or the EVM
- TVL or dollar savings
- zk soundness
- Hidden `vat.dai` / `vat.sin` SLOADs / `flapper.kick` / `flopper.kick` side effects

Machine-written evidence for a given run is in `maker_vow_evidence.json`
(produced by the harness; do not hand-edit).
