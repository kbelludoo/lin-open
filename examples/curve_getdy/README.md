# Curve 3pool `get_dy` (quote + fee) — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
3pool `get_dy`. The LIN copy also lives in a separate repo.

- **Upstream:** [curvefi/curve-contract](https://github.com/curvefi/curve-contract) `contracts/pools/3pool/StableSwap3Pool.vy`. Informational-only; hash-pinned, **not vendored**.
- **LIN clone (this tree):** [`src/lin_curve_getdy.lin`](../../src/lin_curve_getdy.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-curve-getdy
- **C11 oracle:** `test/oracles/curve_getdy_c11.c`
- **Harness:** `python3 test/prove_curve_getdy_external.py` or `make curve-getdy-proof`
- **Event receipt:** `docs/events/EVENT_CURVE_GETDY_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Curve's stableswap **quote** at
**SCALE = 1e9**, **N = 3**, **equal rates** (mainnet `RATES` of 1e30 for
USDC/USDT does not fit i64). Real deltas versus the Vyper:

1. `self._xp()`, `self._A()`, and `self.fee` become explicit arguments.
2. `(y*y+c)/den` uses a 128-bit product. If the quotient does not fit i64 the
   clone fail-closes to 0 instead of wrapping.
3. `dx = 0` fail-closes (uint256 would wrap `xp[j]-y-1 = -1`).
4. Fee is `floor(fee * dy / 10**10)` with the published 3pool 0.04% (`4e6`).

Named goldens (equal `1e9` balances, `dx = 1e8`): no-fee **99900110**; 0.04%
fee **99860150** (`A=100`) and **99954955** (`A=2000`); omit-minus-1 **99900111**.

## What is not claimed

- Vyper **uint256** / mainnet **3pool** / **RATES=1e30** parity
- LIN replacing Curve or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk
- `get_y` as a standalone clone (see [clone-lin-curve-gety](https://github.com/kbelludoo/clone-lin-curve-gety))

Machine-written evidence for a given run is in `curve_getdy_evidence.json`
(produced by the harness; do not hand-edit).
