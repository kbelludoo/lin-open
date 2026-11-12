# Maker/Sky jug.drip — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of MakerDAO /
Sky `Jug.drip`. The LIN kernel copy lives in a separate repository; lin-open
keeps proofs, hashes, and the in-tree kernel used by Compiler 0.

- **Upstream:** [makerdao/dss](https://github.com/makerdao/dss) `src/jug.sol` commit `fa4f6630afb0624d04a003e920b0d71a00331d98` (AGPL-3.0-or-later). Hashes only: sha256 `cefc440545885a916920ce2dc251916f2fc218701ba32413d3ce4884fba07927`, git blob `dae9b263f699ed917e1d0a16bb51dc8b0326764f`. `jug.sol` is **not vendored**.
- **Clone-lin repo:** https://github.com/kbelludoo/clone-lin-maker-jug-drip
- **LIN clone (this tree, for proofs):** [`src/lin_maker_jug_drip.lin`](../../src/lin_maker_jug_drip.lin)
- **C11 oracle:** `test/oracles/maker_jug_drip_c11.c`
- **Harness:** `python3 test/prove_maker_jug_drip_external.py` or `make maker-jug-drip-proof`
- **Event receipt:** `docs/events/EVENT_MAKER_JUG_DRIP_CLONE_LIN.rulel`

## What is claimed

Experimental, uint64-scale reproduction of Maker's per-second stability-fee
compounding `rate = rmul(rpow(base+duty, now-rho, RAY), prev)`. Real deltas
versus the Solidity jug in this profile:

1. Storage (`now`, `rho`, `base`, `duty`, `vat.ilks[].rate`) are function
   arguments. `vat.fold` is not a hidden side effect; `jgd_diff(rate, prev)`
   returns the fold delta.
2. `rpow` half-up `(x*x + RAY'/2)/RAY'` and floor `rmul` use a 128-bit
   product. If the quotient does not fit i64 the clone fail-closes to 0.
3. `now < rho` fail-closes (Solidity `require` reverts). `10 ** 27` (RAY)
   is rejected by the Solidity transpiler; this clone uses `RAY'=1e9`.

Named goldens (`RAY'=1e9`, `duty=RAY'+1e6`, `prev=RAY'`): identity duty
leaves prev unchanged; `now < rho` → **0**; dt=2 drip **1002001000** vs
first-order linear **1002000000**; dt=10 drip **1010045120** vs linear
**1010000000**; naive i64 `7e18*3e18` wraps to **-5389669316318724096**.

## What is not claimed

- Solidity **uint256** / mainnet **vat.ilks.rate** / **RAY=1e27** parity
- LIN replacing Maker, Sky, Dai, USDS, or the EVM
- Any TVL or dollar-savings figure
- Computational soundness of Merkle / zk receipts

Machine-written evidence for a given run is in `maker_jug_drip_evidence.json`
(produced by the harness; do not hand-edit).
