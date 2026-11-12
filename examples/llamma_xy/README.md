# crvUSD LLAMMA get_x_down / get_y_up — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve Finance
LLAMMA `get_xy_up` / `get_y_up` / `get_x_down`. The LIN kernel lives in a
separate clone-lin repository; lin-open keeps proofs, the C11 oracle, and the
Compiler 0 harness.

- **Upstream:** [curvefi/curve-stablecoin](https://github.com/curvefi/curve-stablecoin) `curve_stablecoin/AMM.vy` (informational-only; **not vendored**)
- **Separate clone-lin repo:** [kbelludoo/clone-lin-llamma-xy](https://github.com/kbelludoo/clone-lin-llamma-xy)
- **LIN clone (this tree, results copy):** [`src/lin_llamma_xy.lin`](../../src/lin_llamma_xy.lin)
- **Pinned hashes:** `test/fixtures/external_proof/llamma_xy.pin.rulel`
- **C11 oracle:** `test/oracles/llamma_xy_c11.c`
- **Harness:** `python3 test/prove_llamma_xy_external.py` or `make llamma-xy-proof`
- **Event receipt:** `docs/events/EVENT_LLAMMA_XY_CLONE_LIN.rulel`

Distinct from [clone-lin-curve-vp](https://github.com/kbelludoo/clone-lin-curve-vp) (`get_D`/`get_virtual_price`), [clone-lin-curve-gety](https://github.com/kbelludoo/clone-lin-curve-gety), [clone-lin-curve-getdy](https://github.com/kbelludoo/clone-lin-curve-getdy), and [clone-lin-curve-getyd](https://github.com/kbelludoo/clone-lin-curve-getyd).

## What is claimed

Experimental, uint64-scale reproduction of LLAMMA's single-band adiabatic
conversion (collateral `get_y_up` / debt `get_x_down`) with `SCALE=1e9`. Real
deltas versus the Vyper AMM in this profile:

1. Hidden storage (`self.bands_x`/`self.bands_y`, `_user_shares`, `active_band`,
   `p_oracle`, user address) is lifted to function arguments.
2. `Inv=(f+x)*(g+y)` overflows i64 at 1e9-scale. LIN uses a 128-bit product
   (schoolbook limbs in LIN, `__int128` in the C11 oracle) via
   `muldiv(fx,gy,den)` and fail-closes if the quotient does not fit i64.
3. `DEAD_SHARES=1000` is an explicit share denominator. Naive mark
   `y * p_o / SCALE` is an explicit second oracle so the adiabatic haircut
   is auditable (named golden: `x_down=994987437` vs naive `1100000000`).

## What is not claimed

- Solidity/Vyper **uint256** / mainnet **crvUSD** `WAD=1e18` / multi-tick parity
- LIN replacing Curve, crvUSD, LlamaLend, or the EVM
- General superiority vs vyper/LLVM
- Computational soundness of Merkle / zk

Machine-written evidence for a given run is in `llamma_xy_evidence.json`
(produced by the harness; do not hand-edit).
