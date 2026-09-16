# LIN as a numeric coprocessor (u512) with an auditable receipt

Class: **EXPERIMENTAL**. This is FullMath *width* (a 512-bit product, then 512/256
restoring division). It is not Uniswap V3 `FullMath.sol` CRT/mulmod assembly, not a
deployed pool, and not a claim that `settle_u256_word` is closed.

LIN is sold here as a **numeric coprocessor**: it computes `mulDiv(a,b,d)=(a*b)/d`
for `a,b,d < 2^256` with a real 512-bit intermediate, and it emits a receipt an
external auditor can recompute **without LIN**.

## What is proved

| Primitive | Statement | Oracles |
|---|---|---|
| mul | 256×256 → 512 schoolbook, carry in 16-bit limbs | Python `int`, C11 16-bit, C11 64-bit `__int128` |
| ge | unsigned compare on 512 bits (division-loop predicate) | same |
| div | 512/256 → 256 restoring; remainder identity `q*d+r == n` | same |
| mulDiv | guards `-1` (d=0) and `-2` (quotient ≥ 2^256) | same + LinVM |
| receipt | LNR1 240-byte leaves, `LIN:U512:LEAF:1` / `LIN:U512:NODE:1` | Python hashlib only |

The 512-bit intermediate is then **off the suspect list** for silent wrap. That
does **not** close the uint256 settler: `settle_u256_word` still fail-closes with
`-2` when the product does not fit in 256 bits (SafeMath width). A phantom AMM
(`amount_in=1, reserve_in=1, reserve_out=ceil(2^256/997)`) is the witness:
coprocessor **APPROVES**, settler returns **`-2`**.

End-to-end still required, and shipped as a **slice** (not the 157/2000 campaign):

- `settle_u256_word` vs `ref_amount_out` on one Mainnet `EXACT_INPUT` and one
  `OVERPAID_INPUT` (lin==ref; on-chain equals lin only for EXACT)
- guards `-1` (zero in) and `-2` (phantom overflow)
- real LinVM `steps` bound into LCR2 (208 bytes), verified by
  `examples/defi_settlement_proof/sdk/verify_u256_client.py`

## Reproduce

```bash
make u512-coprocessor-proof
# or:
python3 test/prove_u512_coprocessor_external.py
python3 test/prove_u256_lcr2_e2e_slice.py
```

Auditor (no LIN, no gcc):

```bash
python3 examples/u512_coprocessor/verify_u512_receipt.py \
  examples/u512_coprocessor/u512_coprocessor_evidence.json
```

## What is not claimed

- Solidity FullMath bit-exact vs `mulmod`/`not(0)` CRT reconstruction
- `settle_u256_word` returning the FullMath quotient on phantom overflow
- The full unfiltered 157-swap / 2000-swap campaign
- zk / computational soundness of Merkle (this is tamper-evidence plus re-execution)
- LIN replacing Uniswap or the EVM
