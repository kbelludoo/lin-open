# Curve 3pool get_D / get_y — LIN clone (results only)

This directory holds **results and proofs** for an experimental LIN clone of
Curve Finance 3pool's stableswap Newton solver. The LIN kernel also lives at
[`src/lin_curve_gety.lin`](../../src/lin_curve_gety.lin); a copy is published
separately as **clone-lin**.

- **Upstream:** [curvefi/curve-contract](https://github.com/curvefi/curve-contract) `contracts/pools/3pool/StableSwap3Pool.vy` commit `bae23a2fc9a0302d174ea1ffce8219a44a92149c` (informational-only; **not vendored**)
- **LIN clone (this tree):** [`src/lin_curve_gety.lin`](../../src/lin_curve_gety.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-curve-gety
- **Pin (hashes only):** `test/fixtures/external_proof/curve_3pool_gety.pin.rulel`
- **C11 oracle:** `test/oracles/curve_gety_c11.c`
- **Harness:** `python3 test/prove_curve_gety_external.py`
- **Vyper transpiler delta:** `src/lin_from_vyper.lin` (fail-closed `10 ** N` + Curve rejects)
- **Event receipt:** `docs/events/EVENT_CURVE_GETY_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-positive (`SCALE=1e9`, `N=3`) reproduction of Curve's `get_D`
and `get_y` Newton iteration. Real deltas versus the Vyper 3pool:

1. `amp` and balances `x0,x1,x2` are function arguments, not `self._A()` /
   `block.timestamp` ramps or `uint256[N_COINS]` storage.
2. `(y*y + c) / (2y + b - D)` uses a 128-bit product. Naive signed i64 `D*D`
   on an imbalanced invariant wraps; the clone does not.
3. `get_dy` with `dx=0` would compute `xp[j] - y - 1 = -1` and wrap in
   uint256. LIN fail-closes to 0.
4. `lin_from_vyper.lin` rejects `self.`, `raw_call`, `uint256[N_COINS]`, and
   `assert`, and expands Curve's `10 ** 18` / `10 ** 10` literals.

## What is not claimed

- Vyper **uint256** / mainnet **3pool** / `RATES` / `PRECISION` / fee parity
- LIN replacing Curve, Saddle, Uniswap, or the EVM
- TVL savings or wall-clock superiority vs vyper/solc
- A license to redistribute Curve.Fi source
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `curve_gety_evidence.json`
(produced by the harness; do not hand-edit).
