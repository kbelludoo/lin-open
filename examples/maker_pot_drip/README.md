# Maker/Sky `pot.drip` (Dai Savings Rate chi) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO /
Sky Protocol `Pot.drip`. The LIN copy also lives in a separate repo.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/pot.sol` (AGPL-3.0-or-later). Hash-pinned, **not vendored**.
- **LIN clone (this tree):** [`src/lin_maker_pot_drip.lin`](../../src/lin_maker_pot_drip.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-maker-pot-drip
- **C11 oracle:** `test/oracles/maker_pot_drip_c11.c`
- **Harness:** `python3 test/prove_maker_pot_drip_external.py` or `make maker-pot-drip-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_POT_DRIP_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Maker's DSR chi accumulator at
**RAY' = 1e9** (mainnet RAY = 1e27 does not fit i64). Real deltas versus the
Solidity:

1. Solidity 0.6 `now`, `dsr`, `chi`, and `rho` become explicit arguments.
2. `(a*b)/RAY'` (floor rmul) and rpow half-up use a 128-bit product. If the
   quotient does not fit i64 the clone fail-closes to 0 instead of wrapping.
3. `10 ** N` for N≤18 now expands in `lin_from_solidity.lin`; `10 ** 27` is
   rejected (`REJ_SOLIDITY_RAY27`).
4. No `vat.suck` hidden Dai mint — `mpd_chi_delta` / `mpd_suck_rad` are
   pure functions of `(dsr, chi, dt, Pie)`.

Named goldens (`dsr = RAY' + 1e6`): dt=2 drip **1002001000** vs first-order
linear **1002000000**; dt=10 **1010045120** vs **1010000000**.

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / sDAI / sUSDS parity
- LIN replacing Maker, Sky, or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `jug.drip` (see clone-lin-maker-jug-drip)

Machine-written evidence for a given run is in `maker_pot_drip_evidence.json`
(produced by the harness; do not hand-edit).
