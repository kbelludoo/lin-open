# go-ethereum IntrinsicGas — LIN clone (results only)

This directory holds **results and proofs** for the LIN clone of Geth's
transaction intrinsic-gas schedule. The LIN kernel is
`src/lin_geth_intrinsicgas.lin` in lin-open. A separate clone-lin repository
holds a copy of that kernel:

- **Clone-lin:** https://github.com/kbelludoo/clone-lin-geth-intrinsicgas
- **Upstream:** [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) tag `v1.16.9` commit `95665d5703e1023995a0ff93e4ce9eb77e8a59bd` `core/state_transition.go` (LGPL-3.0)
- **Pinned fixture:** `test/fixtures/external_proof/state_transition.go` (unmodified) sha256 `449d50d372cc6ddff95f6ffa4eae29e06d38e248b24bc8501036c04f3e3f0c14` git blob `bf5ac07636d5111c281726a4273d149cb10d1d8e`
- **C11 oracle:** `test/oracles/geth_intrinsicgas_c11.c`
- **Harness:** `python3 test/prove_geth_intrinsicgas_external.py`
- **Event receipt:** `docs/events/EVENT_GETH_INTRINSICGAS_CLONE_LIN.rulel`

## What is claimed

Experimental, i64-scale reproduction of Geth `IntrinsicGas` / `toWordSize`
(Homestead create, EIP-2028 Istanbul nonzero calldata, EIP-2930 access lists,
EIP-3860 initcode words, EIP-7702 auth-list using `CallNewAccountGas`).
Operand domain is the same cap Geth publishes as `MaxGasLimit = 2^63-1`.

Real deltas versus the published Go:

1. `bytes.Count` / `len(data)` / `accessList.StorageKeys()` become explicit
   `z`, `nz`, `naddr`, `nkeys`, `nauth` arguments.
2. Access-list and auth-list increments are overflow-checked. Geth v1.16.9
   guards the calldata path with `MaxUint64` and does **not** guard those two
   adds (pinned bytes).
3. Overflow fail-closes to 0 at i64max rather than returning `(0, error)` or
   wrapping uint64.
4. Go transpiler (`src/lin_from_go.lin`) fail-closes the original
   `[]byte` / selector / error-tuple form (`REJ_GO_SLICE`, `REJ_GO_SELECTOR`,
   `REJ_GO_ERROR`) and emits only scalar uint64 functions. C transpiler v2
   adds `REJ_C_ARRAY_PARAM` for `T name[]` decay-to-pointer params.

## What is not claimed

- LIN replacing go-ethereum or Ethereum consensus
- Values above `MaxGasLimit` (Geth IntrinsicGas is uint64; this clone is i64)
- That mainnet access lists wrap (they are small). The finding is the missing
  check in source plus fail-closed arithmetic at the published cap
- Wall-clock superiority vs Geth/solc
- That Compiler 0 executes `go_from_go` string-literal paths (`VM_REJ_STRING_LITERAL`)

Machine-written evidence for a given run is in `geth_intrinsicgas_evidence.json`
(produced by the harness; do not hand-edit).
