# 512-bit numeric coprocessor (experimental)

LIN as a **numeric coprocessor with an auditable receipt**, not as a Uniswap
replacement.

- **Engine:** [`src/lin_u512_coprocessor.lin`](../../src/lin_u512_coprocessor.lin)
- **Harness:** `python3 test/prove_u512_coprocessor_external.py`
- **Auditor (no LIN, no C11):** `python3 test/prove_u512_coprocessor_external.py --verify-receipt examples/u512_coprocessor/u512_coprocessor_evidence.json`
- **C11 oracle:** `test/oracles/u512_coprocessor_c11.c` (64-bit limbs XOR 32-bit limbs)
- **Upstream pin:** Uniswap v3 `FullMath.sol` in `test/fixtures/external_proof/`
- **Event:** `docs/events/EVENT_U512_COPROCESSOR_2026_09_15.rulel`

## Claimed

`mulDiv(a,b,d)=(a*b)/d` for `a,b,d < 2^256` uses a 512-bit product. This
directory's evidence JSON is written by the harness when Python bigint, the
C11 oracle, and Compiler-0 LIN agree, and when an LNR1 Merkle root recomputed
with `hashlib` rejects a 1-bit leaf tamper.

## Not claimed

- `settle_u256_word` vs `ref_amount_out` on EXACT / OVERPAID classes
- LCR2 208-byte records with real LinVM steps
- production replacement of FullMath / Uniswap / EVM
- zk soundness of Merkle (tamper-evidence only)

`u512_coprocessor_evidence.json` is machine-written. Do not hand-edit.
