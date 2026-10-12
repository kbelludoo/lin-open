# Uniswap V3 getNextSqrtPriceFromOutput — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Uniswap V3
exact-output next-sqrt math. The standalone LIN copy lives in a separate repo.

- **Upstream:** [Uniswap/v3-core](https://github.com/Uniswap/v3-core) tag `v1.0.0` `contracts/libraries/SqrtPriceMath.sol`
- **License:** GPL-2.0-or-later (BUSL-1.1 Change Date 2023-04-01 elapsed)
- **LIN clone (this tree):** [`src/lin_uniswap_v3_output.lin`](../../src/lin_uniswap_v3_output.lin)
- **Separate clone-lin repo:** https://github.com/kbelludoo/clone-lin-uniswap-v3-output
- **Pinned fixture:** `test/fixtures/external_proof/SqrtPriceMath.sol`
- **C11 oracle:** `test/oracles/uniswap_v3_output_c11.c`
- **Harness:** `python3 test/prove_uniswap_v3_output_external.py`
- **Event receipt:** `docs/events/EVENT_UNISWAP_V3_OUTPUT_CLONE_LIN.rulel`

Class: **EXPERIMENTAL** (real published algorithm, Q32=2^32 not Q96=2^96).
Not a Pool / SwapRouter / NFT position. Not getNextSqrtPriceFromInput
(that is [clone-lin-uniswap-v3-next-sqrt](https://github.com/kbelludoo/clone-lin-uniswap-v3-next-sqrt)).
Not getTickAtSqrtRatio (assembly MSB, rejected).

Machine-written evidence for a given run is in `uniswap_v3_output_evidence.json`
(produced by the harness; do not hand-edit).
