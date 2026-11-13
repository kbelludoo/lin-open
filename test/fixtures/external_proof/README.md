# External Proof Fixtures

These files are unmodified copies of public upstream source, pinned for the
independent proof harness. They are **test fixtures**, not vendored libraries.

| File | Upstream | License |
|---|---|---|
| `UniswapV2Library.sol` | [Uniswap/v2-periphery](https://github.com/Uniswap/v2-periphery) | GPL v3 (upstream) |
| `FullMath.sol` | [Uniswap/v3-core](https://github.com/Uniswap/v3-core) | BUSL-1.1 / GPL-3.0 (upstream) |
| `openssl_sha256.c` | [openssl/openssl](https://github.com/openssl/openssl) | Apache-2.0 |
| `qoi.h` | [phoboslab/qoi](https://github.com/phoboslab/qoi) | MIT |
| `tinyexpr.c` | [codeplea/tinyexpr](https://github.com/codeplea/tinyexpr) | zlib |
| `BaseJumpRateModelV2.sol` | [compound-finance/compound-protocol](https://github.com/compound-finance/compound-protocol) | BSD-3-Clause |

**Fetch-only (not stored in this tree):** Curve 3pool
`contracts/pools/3pool/StableSwap3Pool.vy` from
[curvefi/curve-contract](https://github.com/curvefi/curve-contract) commit
`574f44027d089de0eac765f5a74ea5ae96aba968` (git blob
`04d170189a1b5ddfecfc0af9ea3fe23eb0840423`, sha256
`03e0bf29ae2fe945a3629b8085062da8f9d9d25957e86001dfc3df68c895f9dc`).
Upstream LICENSE grants no redistribution right, so the proof harness fetches
and hashes the file at runtime instead of vendoring it.

They are only pinned so an auditor can hash the exact bytes and, with `--fetch`,
re-download them from the GitHub Contents API. No upstream code is compiled or
linked into this repository.

Run `python3 test/prove_all_claims_external.py --fetch` to verify the pinned
records against live GitHub.
