# Maker ExponentialDecrease.price — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO / Sky
`ExponentialDecrease.price`. The LIN copy of the kernel also lives in a
separate clone-lin repository.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/abaci.sol` (AGPL-3.0-or-later, **not vendored**)
- **Pinned commit:** `fa4f6630afb0624d04a003e920b0d71a00331d98`
  - sha256 `a4c3dc0368d66a5bf84e586f0cf76e2e80fb8b336c00348a97cc0d4ddcb016ca`
  - git blob `6cbd666267fc9f534ae52a45926eec5aa44b3bc5`
- **LIN clone (this tree, proof kernel):** [`src/lin_maker_abacus_exp.lin`](../../src/lin_maker_abacus_exp.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-maker-abacus-exp
- **C11 oracle:** `test/oracles/maker_abacus_exp_c11.c`
- **Pointer-free C kernel:** `test/oracles/maker_abacus_exp_kernel.c`
- **Harness:** `python3 test/prove_maker_abacus_exp_external.py` or `make maker-abacus-exp-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_ABACUS_EXP_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`RAY'=1e9`) reproduction of Maker's continuous
per-second exponential Dutch-auction price:

`price(top, dur) = rmul(top, rpow(cut, dur, RAY))`

Real deltas versus the Solidity abacus in this profile:

1. Storage parameter (`cut`) and `wards`/`file` are function arguments, not
   hidden contract storage / `msg.sender`. There is no `step`.
2. Upstream `rpow` is Yul assembly. LIN uses a 128-bit half-up product
   (schoolbook limbs), matching C11 `__int128` and Python bigint. If the
   quotient does not fit uint64 the clone fail-closes to 0 instead of wrapping.
3. `cut > RAY'` fail-closes (Solidity `file` rejects `cut > RAY`).
4. Continuous `n = dur` decays every second. That is **not** LinearDecrease
   (`tau`) and **not** StairstepExponentialDecrease (`n = dur / step`). At
   `dur=1` this clone is `0.99 * top`; a stairstep with `step=90` would still
   equal `top`.

Named goldens (`cut = 0.99 * RAY'`):

| id | dur | price |
|---|---|---|
| PAR | 0 | 1000000000 |
| SEC1 | 1 | 990000000 |
| SEC2 | 2 | 980100000 |
| SEC3 | 3 | 970299000 |
| NOT_HOLD | 89 | 408820172 |
| ODD | 1, top=123456789 | 122222221 |

## What is not claimed

- Solidity **uint256** / mainnet **RAY=1e27** / **Clipper.take** parity
- LIN replacing Maker, Sky, clipper, or the EVM
- LinearDecrease.price or StairstepExponentialDecrease
- TVL or dollar savings
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_abacus_exp_evidence.json`
(produced by the harness; do not hand-edit).
