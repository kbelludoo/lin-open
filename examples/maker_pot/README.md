# Maker/Sky Pot (Dai Savings Rate) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`Pot.drip` / `Pot.join` / `Pot.exit`. The LIN copy lives in a separate clone-lin
repository; lin-open keeps proofs only.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/pot.sol` (AGPL-3.0-or-later, hash-pinned, **not vendored**)
- **Clone-LIN (LIN copy):** https://github.com/kbelludoo/clone-lin-maker-pot-join
- **LIN kernel (identical copy in this tree for the proof harness):** [`src/lin_maker_pot.lin`](../../src/lin_maker_pot.lin)
- **C11 oracle:** `test/oracles/maker_pot_c11.c`
- **Transpilable kernel:** `test/oracles/maker_pot_kernel.c`
- **Harness:** `python3 test/prove_maker_pot_external.py` / `make maker-pot-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_POT_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY'=1e9`) reproduction of Pot's DSR chi update
and pie join/exit. Real deltas versus the Solidity module:

1. `dsr`, `chi`, `rho`, `now`, `Pie`, `pie[usr]` are function arguments, not
   hidden storage / `block.timestamp`.
2. Assembly `_rpow` is a LIN scalar loop with 128-bit half-up muldiv. Floor
   `_rmul` and `chi*wad` use the same 128-bit product; overflow fail-closes
   instead of wrapping i64.
3. `join` requires `now==rho`. `exit` does not — a stale-chi exit is an
   explicit, tested Maker semantic (users leave un-dripped yield on the table).
4. `vat.suck` / `vat.move` hosts are not emitted; the clone returns `suck_rad`
   and `rad`.

Named goldens (`RAY'=1e9`, `dsr=1.01e9`, `Pie=1000`): drip `dt=1` →
`chi'=1010000000`, `suck=10000000000`; `dt=2` → `chi'=1020100000`,
`suck=20100000000`; join `wad=1000` → `rad=1000000000000`; stale join `ok=0`;
stale-chi exit `ok=1`.

## What is not claimed

- Solidity **uint256** / **RAY=1e27** / mainnet **Pot** / **sUSDS** parity
- LIN replacing Maker, Sky, Pot, or the EVM
- TVL or dollar savings
- Computational soundness of Merkle / zk
- `ExponentialDecrease.price` (auction decay) — different kernel

Machine-written evidence for a given run is in `maker_pot_evidence.json`
(produced by the harness; do not hand-edit).
