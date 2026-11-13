# crvUSD Controller._health — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Curve
crvUSD `Controller._health`. The LIN kernel lives in a separate clone-lin
repository; lin-open keeps proofs only.

- **Upstream (hash-pinned, not vendored):** [curvefi/curve-stablecoin](https://github.com/curvefi/curve-stablecoin) `curve_stablecoin/controller.vy` (informational-only; no reproduction license)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-crvusd-health
- **C11 oracle:** `test/oracles/crvusd_health_c11.c`
- **Harness:** `python3 test/prove_crvusd_health_external.py` / `make crvusd-health-proof`
- **Event receipt:** `docs/events/EVENT_CRVUSD_HEALTH_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale (`SCALE = 1e9`, not 1e18 SWAD) reproduction of
crvUSD Controller health:

`health = x_down * (SCALE - liquidation_discount) / debt - SCALE`

plus the `_full` oracle extra when `ns0 > active_band` and `p > p_up`:

`health += (p - p_up) * y / debt` (precisions already normalized).

Named goldens: equal `x_down=debt` disc 0 → **0** (liquidation line);
disc 6% → **-60000000**; 2× collateral → **+1000000000**; `_full` extra
with 10% price-above-band → **+100000000**. Naive i64 `4e9*4e9` wraps;
128-bit muldiv fail-closes.

## What is not claimed

- Vyper **uint256** / mainnet **crvUSD** / 1e18 SWAD parity
- LIN replacing crvUSD, LLAMMA, Curve, or the EVM
- TVL or dollar savings
- LLAMMA `get_x_down` band math (see clone-lin-llamma-xy)

Machine-written evidence for a given run is in `crvusd_health_evidence.json`
(produced by the harness; do not hand-edit).
