# Curve 3pool get_y_D — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
3pool `get_y_D` / `_calc_withdraw_one_coin` (single-coin LP withdrawal). The
LIN copy also lives in a separate repo.

- **Upstream:** [curvefi/curve-contract](https://github.com/curvefi/curve-contract) `StableSwap3Pool.vy` at commit `bae23a2fc9a0302d174ea1ffce8219a44a92149c`. Hash-pinned, **not vendored**. Informational-only / all rights reserved.
- **LIN clone (this tree):** [`src/lin_curve_getyd.lin`](../../src/lin_curve_getyd.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-curve-getyd
- **C11 oracle:** `test/oracles/curve_getyd_c11.c`
- **Harness:** `python3 test/prove_curve_getyd_external.py` or `make curve-getyd-proof`
- **Event receipt:** `docs/events/EVENT_CURVE_GETYD_CLONE_LIN.rulel`

Distinct from [clone-lin-curve-gety](https://github.com/kbelludoo/clone-lin-curve-gety) (`get_D`/`get_y`) and [clone-lin-curve-getdy](https://github.com/kbelludoo/clone-lin-curve-getdy) (`get_dy`).

## What is claimed

Experimental, uint64-scale reproduction of Curve's `get_y_D` Newton solver
at **SCALE = 1e9**, **N = 3**. Real deltas versus the Vyper:

1. Storage `self.balances`, ramped `self._A()`, and `token.totalSupply`
   become explicit arguments (`i`, `D`, `x0/x1/x2`, `amp`, `burn/supply`).
2. A 10% LP burn from equal `1e9` balances at `A=100` returns **299632067**
   of coin 0, not 300000000 (constant-sum D drop). The **367933**-unit
   haircut is the stableswap imbalance penalty, made explicit.
3. The fee path uses Curve's `xp[i]*D1/D0 - new_y` (not `xp[i]-new_y`) with
   baked 3pool 0.04% (`n_fee = 150000` over `FEE_DEN=1e9`) → **299572241**.
4. `totalSupply` / `self.balances` are fail-closed in the transpilers
   (`REJ_SOLIDITY_TOTALSUPPLY` / `REJ_SOLIDITY_SELF_BALANCES` and C/Rust twins)
   instead of being silently dropped.
5. `(y*y+c)/(2y+b-D)` uses a 128-bit product. If the quotient does not fit
   i64 the clone fail-closes to 0 instead of wrapping.

Named goldens: identity `get_y_D` → **1000000000**; 10% burn `D1` → **2700000000**;
`y` after 10% at `A=100` → **700367933**; `dy0` → **299632067**; `A=2000` `dy0` →
**299981370**; fee path → **299572241**; naive i64 `D^2` wraps to
**-8838116264523025375**.

## What is not claimed

- Vyper **uint256** / mainnet **RATES** / **PRECISION_MUL** / **3pool**
- `get_D` / `get_y` / `get_dy` / `exchange` / `raw_call`
- LIN replacing Curve or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `curve_getyd_evidence.json`
(produced by the harness; do not hand-edit).
