# Maker LinearDecrease.price — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Maker/Sky
`LinearDecrease.price` (Dutch-auction linear decay). The LIN copy lives in a
separate clone-lin repository; lin-open keeps the kernel plus auditable proofs.

- **Upstream (hash-pinned, not vendored):** [makerdao/dss](https://github.com/makerdao/dss) `src/abaci.sol` (AGPL-3.0-or-later) commit `fa4f6630afb0624d04a003e920b0d71a00331d98`
- **Clone-LIN repo:** https://github.com/kbelludoo/clone-lin-maker-abacus-linear
- **LIN kernel (this tree):** `src/lin_maker_abacus_linear.lin`
- **C11 oracle:** `test/oracles/maker_abacus_linear_c11.c`
- **Transpilable kernel:** `test/oracles/maker_abacus_linear_kernel.c`
- **Harness:** `python3 test/prove_maker_abacus_linear_external.py`
- **Event receipt:** `docs/events/EVENT_MAKER_ABACUS_LINEAR_CLONE_LIN.rulel`
- **Gate:** `make maker-abacus-linear-proof`

## What is claimed

Experimental, uint64-scale reproduction of LinearDecrease:

`price = rmul(top, mul(tau - dur, RAY) / tau)` and `0` when `dur >= tau`.

Real deltas versus the Solidity abacus in this profile:

1. `tau` is a function argument, not hidden `file`'d storage / `wards`.
2. `(tau-dur)*RAY` and `top*factor` fail-close on i64 overflow instead of wrapping.
3. Distinct from StairstepExponentialDecrease `rpow` and from Clipper.take.

## What is not claimed

- Solidity **uint256** / mainnet **ray=1e27** parity
- LIN replacing Maker, Sky, clipper, or the EVM
- TVL or dollar savings
- StairstepExponentialDecrease / ExponentialDecrease rpow
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `maker_abacus_linear_evidence.json`
(produced by the harness; do not hand-edit).
