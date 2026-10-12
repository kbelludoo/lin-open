# MakerDAO pot.rpow (Dai Savings Rate) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO
`pot.rpow`. The standalone LIN copy lives in a separate clone-lin repository;
lin-open keeps proofs, the kernel, and the transpiler delta.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) tag `1.3.0` `src/pot.sol` (AGPL-3.0-or-later)
- **LIN clone (this tree):** [`src/lin_maker_rpow.lin`](../../src/lin_maker_rpow.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-maker-rpow
- **Pinned fixture:** `test/fixtures/external_proof/pot.sol`
- **C11 oracle:** `test/oracles/maker_rpow_c11.c`
- **Harness:** `python3 test/prove_maker_rpow_external.py`
- **Event receipt:** `docs/events/EVENT_MAKER_RPOW_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale / RAY'=1e9 reproduction of Maker **binary
fixed-point exponentiation** used by the Dai Savings Rate `drip`:
`chi' = rmul(rpow(dsr, now-rho, RAY), chi)`. Class: EXPERIMENTAL (real
published algorithm, deliberately reduced operand width).

Real deltas versus the Solidity assembly in this profile:

1. `dsr` / `dt` / `chi` / `x` / `n` / `base` are explicit LIN arguments (no pot storage, no `now`).
2. RAY'=1e9 instead of RAY=1e27 (1e27 exceeds signed i64 and is rejected).
3. `(a*b + base/2)/base` uses a 128-bit product. Naive i64 `(x*x)/base` wraps; the clone fail-closes overflow to 0.
4. Named skip-round path (`mds_rpow_no_round`) shows half-up vs floor.

This is **not** a retread of Lido/Rocket/Morpho share-rate or Aave `rayMul`
(RAY=1e27 cannot be a working i64 kernel).

## What is not claimed

- Solidity **uint256** / **RAY=1e27** / mainnet **pot.drip** / **vat.suck** parity
- LIN replacing Maker, Sky, or the EVM
- Wall-clock superiority vs solc
- That this clone is a production DSR

Machine-written evidence for a given run is in `maker_rpow_evidence.json`
(produced by the harness; do not hand-edit).
