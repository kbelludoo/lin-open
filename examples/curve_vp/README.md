# Curve 3pool get_virtual_price — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
3pool `get_D` / `get_virtual_price`. The LIN kernel lives in a separate
clone-lin repository; lin-open keeps proofs, the C11 oracle, and the Compiler 0
harness.

- **Upstream:** [curvefi/curve-contract](https://github.com/curvefi/curve-contract) `contracts/pools/3pool/StableSwap3Pool.vy` (informational-only; **not vendored**)
- **Separate clone-lin repo:** [kbelludoo/clone-lin-curve-vp](https://github.com/kbelludoo/clone-lin-curve-vp)
- **LIN clone (this tree, results copy):** [`src/lin_curve_vp.lin`](../../src/lin_curve_vp.lin)
- **Pinned hashes:** `test/fixtures/external_proof/curve_vp.pin.rulel`
- **C11 oracle:** `test/oracles/curve_vp_c11.c`
- **Harness:** `python3 test/prove_curve_vp_external.py` or `make curve-vp-proof`
- **Event receipt:** `docs/events/EVENT_CURVE_VP_CLONE_LIN.rulel`

Distinct from [clone-lin-curve-gety](https://github.com/kbelludoo/clone-lin-curve-gety) (`get_D`/`get_y`), [clone-lin-curve-getdy](https://github.com/kbelludoo/clone-lin-curve-getdy) (`get_dy`), and [clone-lin-curve-getyd](https://github.com/kbelludoo/clone-lin-curve-getyd) (`get_y_D`).

## What is claimed

Experimental, uint64-scale reproduction of Curve's Newton invariant and LP
virtual price `D * SCALE / supply` with `SCALE=1e9`. Real deltas versus the
Vyper pool in this profile:

1. Hidden storage (`self._xp()`/`RATES`/`self.balances`, ramped `self._A()`,
   `self.token.totalSupply()`) is lifted to function arguments.
2. Newton `get_D` and `D * SCALE / supply` use a 128-bit product (schoolbook
   limbs in LIN, `__int128` in the C11 oracle). If the quotient does not fit
   i64 the clone fail-closes to 0 instead of wrapping.
3. Imbalance versus constant-sum is an explicit second oracle so the haircut
   is auditable (named golden: `999928603` vs `1000000000`).

## What is not claimed

- Solidity/Vyper **uint256** / mainnet **3pool** `RATES` / `PRECISION=1e18` parity
- LIN replacing Curve, Convex, Yearn, or the EVM
- General superiority vs vyper/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `curve_vp_evidence.json`
(produced by the harness; do not hand-edit).
