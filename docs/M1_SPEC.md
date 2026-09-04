# M1 Specification: Ethereum Transaction Cryptographic Identity Verifier (RLP & Keccak-256)

**Project:** Lin-Audit Ethereum  
**Milestone:** M1 — Cryptographic Identity of Ethereum Transactions  
**Status:** Canonical Draft  
**Version:** 1.0.0  

---

## 1. Scope and Objective

Milestone 1 (M1) provides an independent, deterministic, and fail-closed cryptographic verifier for raw Ethereum signed transactions.

Given raw transaction bytes (`raw_tx`) and an optional claimed hash (`claimed_hash`), the verifier:
1. Normalizes and validates the hexadecimal byte representation.
2. Identifies the transaction envelope type according to EIP-2718.
3. Parses and validates the payload against canonical Recursive Length Prefix (RLP) rules.
4. Validates structural and semantic field constraints (arities, address lengths, minimal big-endian integer encodings).
5. Reserializes the canonical payload and checks roundtrip byte-level equality.
6. Computes the canonical transaction hash via **Keccak-256** (with padding `0x01 ... 0x80`, strictly distinguished from NIST FIPS 202 SHA3-256).
7. Compares the computed hash against `claimed_hash` (if provided).
8. Emits a structured machine-readable JSON verdict with deterministic error codes.

### 1.1 Non-Goals of M1
- M1 does **not** assert block inclusion or finality (requires block header, index, and Merkle-Patricia Trie proof; scoped for M2/M3).
- M1 does **not** execute EVM bytecode or validate state transitions.
- M1 does **not** recover public keys or verify account nonces/balances against world state.
- M1 does **not** rely on external network RPC connections during verification.

---

## 2. Transaction Formats and Envelopes

The verifier supports four primary transaction types, plus an extension slot:

| Type ID | Standard | Serialized Wire Format | RLP Payload Elements |
|---|---|---|---|
| `0x00` (internal: 0) | Legacy / EIP-155 | `RLP([nonce, gasPrice, gasLimit, to, value, data, v, r, s])` | 9 fields |
| `0x01` (1) | EIP-2930 | `0x01 \|\| RLP([chainId, nonce, gasPrice, gasLimit, to, value, data, accessList, yParity, r, s])` | 11 fields |
| `0x02` (2) | EIP-1559 | `0x02 \|\| RLP([chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList, yParity, r, s])` | 12 fields |
| `0x03` (3) | EIP-4844 | `0x03 \|\| RLP([chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList, maxFeePerBlobGas, blobVersionedHashes, yParity, r, s])` | 14 fields |
| `0x04` (4) | EIP-7702 | `0x04 \|\| RLP([chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList, authorizationList, yParity, r, s])` | Extension |

### 2.1 Envelope Identification Rules
- If the first byte `b[0]` is in the range `[0x01, 0x7f]`:
  - `b[0]` defines the EIP-2718 `TransactionType`.
  - The remaining slice `b[1:]` MUST be a valid, canonical RLP-encoded list representing `TransactionPayload`.
  - The digest input is the full serialized wire format: `Keccak-256(raw_tx)` (the type byte is included in the hash).
- If the first byte `b[0]` is $\ge 0xc0$:
  - The transaction is classified as Legacy (Type 0).
  - The entire slice `b[0:]` MUST be a single, canonical RLP-encoded list.
  - The digest input is `Keccak-256(raw_tx)`.
- Any first byte in `[0x80, 0xbf]` or unrecognized type byte $> 0x04$ MUST be rejected with `UNSUPPORTED_TYPE` or `MALFORMED`.

---

## 3. Canonical RLP Encoding Rules

The RLP parser enforces strict canonical encoding rules. Any violation immediately causes verification to fail:

1. **Short String (`0x00` - `0x7f`)**: A single byte with value $< 0x80$ MUST be encoded as itself (1 byte). Encoding it as a length-prefixed string (`0x81 <byte>`) is non-canonical and MUST be rejected (`NON_CANONICAL`).
2. **String ($0 \le \text{len} \le 55$)**: Byte prefix `0x80 + len`. If $\text{len} = 1$ and the byte value is $< 0x80$, it MUST be rejected (`NON_CANONICAL`).
3. **Long String ($\text{len} > 55$)**: Byte prefix `0xb7 + k` where $k$ is the byte length of the length integer ($1 \le k \le 8$).
   - If $\text{len} \le 55$, encoding as long string MUST be rejected (`NON_CANONICAL`).
   - The length integer MUST NOT have leading zero bytes (`NON_CANONICAL`).
4. **List ($0 \le \text{payload\_len} \le 55$)**: Byte prefix `0xc0 + payload\_len`.
5. **Long List ($\text{payload\_len} > 55$)**: Byte prefix `0xf7 + k` where $k$ is the byte length of the list length integer ($1 \le k \le 8$).
   - If $\text{payload\_len} \le 55$, encoding as long list MUST be rejected (`NON_CANONICAL`).
   - The length integer MUST NOT have leading zero bytes (`NON_CANONICAL`).
6. **No Residual / Trailing Bytes**: The RLP item MUST consume exactly all bytes allocated to it. Any trailing bytes after the root item MUST be rejected (`MALFORMED`).
7. **Buffer Overrun Protection**: Declared RLP item length MUST NOT exceed available slice buffer length (`MALFORMED`).
8. **Minimal Big-Endian Integers**:
   - The integer zero ($0$) MUST be encoded as an empty byte sequence (`0x80` in RLP).
   - Any positive integer MUST be serialized as big-endian without leading zeros (`0x00`). Integers with leading zeros MUST be rejected (`NON_CANONICAL`).
9. **Roundtrip Invariance**: Decoded payload items when reserialized via canonical RLP MUST match the input slice byte-for-byte.

---

## 4. Field Validation Constraints

| Field | Type 0 | Type 1 | Type 2 | Type 3 | Constraint |
|---|---|---|---|---|---|
| `chain_id` | implicit in `v` (EIP-155) | Pos 0 | Pos 0 | Pos 0 | Non-negative integer |
| `nonce` | Pos 0 | Pos 1 | Pos 1 | Pos 1 | Non-negative integer ($\le 64$ bits) |
| `gas_price` | Pos 1 | Pos 2 | — | — | Non-negative integer |
| `max_priority_fee` | — | — | Pos 2 | Pos 2 | Non-negative integer |
| `max_fee` | — | — | Pos 3 | Pos 3 | Non-negative integer, $\ge \text{max\_priority\_fee}$ |
| `gas_limit` | Pos 2 | Pos 3 | Pos 4 | Pos 4 | Non-negative integer ($\le 64$ bits) |
| `to` | Pos 3 | Pos 4 | Pos 5 | Pos 5 | Empty bytes (contract creation) OR exactly 20 bytes |
| `value` | Pos 4 | Pos 5 | Pos 6 | Pos 6 | Non-negative integer ($\le 256$ bits) |
| `data` | Pos 5 | Pos 6 | Pos 7 | Pos 7 | Arbitrary byte string |
| `access_list` | — | Pos 7 | Pos 8 | Pos 8 | List of `[address, [storage_key, ...]]` tuples |
| `max_fee_blob_gas` | — | — | — | Pos 9 | Non-negative integer |
| `blob_hashes` | — | — | — | Pos 10 | List of 32-byte hashes, each starting with version byte `0x01` |
| `y_parity` / `v` | Pos 6 | Pos 8 | Pos 9 | Pos 11 | Integer (EIP-155 / parity $\in \{0, 1\}$) |
| `r` | Pos 7 | Pos 9 | Pos 10 | Pos 12 | Non-negative integer, byte length $\le 32$ |
| `s` | Pos 8 | Pos 10 | Pos 11 | Pos 13 | Non-negative integer, byte length $\le 32$ |

---

## 5. Keccak-256 vs. NIST SHA3-256

Ethereum consensus and transaction hashes strictly use the original **Keccak-256** function proposed to the SHA-3 competition, which uses suffix padding:
$$\text{Padding} = 0x01 \parallel 0x00^* \parallel 0x80$$
This is fundamentally distinct from NIST FIPS 202 SHA3-256, which appends domain separation bits `01` prior to padding, resulting in effective padding:
$$\text{Padding}_{\text{NIST}} = 0x06 \parallel 0x00^* \parallel 0x80$$

### 5.1 Test Vector Difference
For empty input `""` (`b""`):
- **Keccak-256**: `c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470`
- **NIST SHA3-256**: `a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a`

The verifier includes an explicit test asserting this discrepancy to prevent silent substitution.

---

## 6. Output Schema & Error Taxonomy

For any input transaction, the verifier outputs deterministic JSON with the following structure:

```json
{
  "schema": "LIN_AUDIT_ETH_M1_V1",
  "valid_encoding": true,
  "tx_type": 2,
  "tx_type_name": "EIP-1559",
  "canonical_payload": "0x...",
  "recomputed_hash": "0x...",
  "claimed_hash": "0x...",
  "hash_matches": true,
  "semantic_valid": true,
  "verdict": "PASS",
  "errors": []
}
```

### 6.1 Verdict Rules
- **`PASS`**: Emitted if and only if `valid_encoding == true`, `semantic_valid == true`, and (if `claimed_hash` was provided) `hash_matches == true`.
- **`FAIL`**: Emitted when encoding is invalid, fields are malformed, or hash does not match.
- **`UNSUPPORTED_TYPE`**: Emitted when the envelope prefix denotes an unknown or unsupported transaction type.

### 6.2 Deterministic Error Codes
1. `MALFORMED`: Syntax error, truncated buffer, undeclared bytes, or trailing residual bytes.
2. `NON_CANONICAL`: RLP encoding violates minimal length or integer encoding rules.
3. `WRONG_ARITY`: Payload list has incorrect number of elements for its transaction type.
4. `INVALID_FIELD_LENGTH`: A field length violates standard constraints (e.g., `to` is not 0 or 20 bytes, `r` or `s` $> 32$ bytes).
5. `UNSUPPORTED_TYPE`: Transaction type byte is not in $\{0, 1, 2, 3\}$ (or supported extension).
6. `HASH_MISMATCH`: Recomputed `Keccak-256(raw_tx)` does not equal `claimed_hash`.

### 6.3 Process Exit Codes
- `0`: Transaction verified successfully (`PASS`).
- `1`: Malformed, non-canonical, or hash mismatch (`FAIL`).
- `2`: Well-formed envelope with unsupported transaction type (`UNSUPPORTED_TYPE`).
- `3`: Command-line usage error, missing file, or argument parsing failure.
- `4`: Internal deterministic execution error.
