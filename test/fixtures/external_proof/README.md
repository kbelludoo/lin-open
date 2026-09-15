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
| `rust_bitcoin_feerate_scalar.c` | LIN scalar extract of [rust-bitcoin/rust-bitcoin](https://github.com/rust-bitcoin/rust-bitcoin) `FeeRate::mul_by_weight` @ `1cbf4bd62ea99c558c6d8ef794edbd984a2a4684` | CC0-1.0 (upstream) |
| `rust_bitcoin_feerate_scalar.rs` | same, for `lin_from_rust` v2 emit | CC0-1.0 (upstream) |

They are only pinned so an auditor can hash the exact bytes and, with `--fetch`,
re-download them from the GitHub Contents API. No upstream code is compiled or
linked into this repository.

Run `python3 test/prove_all_claims_external.py --fetch` to verify the pinned
records against live GitHub.
