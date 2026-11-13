# Curve StableSwap 3pool — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve's
3pool StableSwap invariant (`get_D`, `get_y`, `get_dy`). The LIN clone is also
kept in lin-open so the proof harness stays recomputable.

- **Standalone clone-lin repo:** [kbelludoo/clone-lin-curve-stableswap](https://github.com/kbelludoo/clone-lin-curve-stableswap)
- **LIN source in that repo:** [src/lin_curve_stableswap.lin](https://github.com/kbelludoo/clone-lin-curve-stableswap/blob/main/src/lin_curve_stableswap.lin)

- **Upstream (algorithm, not vendored):** [curvefi/curve-contract](https://github.com/curvefi/curve-contract) `contracts/pools/3pool/StableSwap3Pool.vy`
  commit `574f44027d089de0eac765f5a74ea5ae96aba968`. Upstream LICENSE grants **no
  redistribution right**; lin-open does **not** store the Vyper file. The proof
  harness fetches it, hashes it, and checks that the Newton `get_D` formula is
  still present.
- **LIN clone (this tree):** `src/lin_curve_stableswap.lin` (original LIN, not a
  copy of the Vyper)
- **C11 oracle:** `test/oracles/curve_stableswap_c11.c` (`gcc -O2 -std=c11`)
- **Transpilable C kernel (naive uint64):** `test/oracles/curve_get_d_kernel.c`
- **Harness:** `python3 test/prove_curve_stableswap_external.py`
- **Event receipt:** `docs/events/EVENT_CURVE_STABLESWAP_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Curve 3pool `get_D` / `get_y` /
`get_dy` with fee as an argument. Operand scale is ~1e10 so the Newton
accumulator `c` fits uint64 while `D*D` does **not** fit signed i64 — that is
why the clone uses 128-bit muldiv.

Real deltas versus the Vyper pool in this profile:

1. Amplification `A`, balances, and `fee` are function arguments, not hidden
   storage / `block.timestamp` ramps.
2. `(a*b + c)/d` uses a 128-bit product (schoolbook limbs in LIN, `__int128`
   in the C11 oracle). If the quotient does not fit uint64 the clone
   fail-closes to 0 instead of wrapping.
3. Zero coin / zero `A` / division by zero fail-closed to 0 (Vyper reverts).

## What is not claimed

- Vyper **uint256** / mainnet **3pool** quote parity
- LIN replacing Curve, Uniswap, or the EVM
- A TVL or revenue figure for this clone
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `curve_stableswap_evidence.json`
(produced by the harness; do not hand-edit).
