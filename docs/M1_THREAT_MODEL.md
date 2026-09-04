# M1 Threat Model & Scope Boundaries: Lin-Audit Ethereum

**Project:** Lin-Audit Ethereum  
**Component:** M1 — Cryptographic Identity Verifier  
**Document:** `docs/M1_THREAT_MODEL.md`  
**Version:** 1.0.0  

---

## 1. Executive Summary

The M1 component serves as a strictly bounded cryptographic verifier. Its objective is to answer a single question with mathematical certainty:
> *"Does this sequence of raw bytes form a canonically encoded Ethereum transaction whose hash equals the claimed identifier?"*

It deliberately does not evaluate network state, account balance, chain consensus, or transaction inclusion.

---

## 2. Threat & Adversary Model

### 2.1 Untrusted Sources
The verifier assumes that all external inputs (`raw_tx`, `claimed_hash`, surrounding JSON metadata, block numbers, indices) may originate from a malicious adversary or an untrusted / faulty RPC node.

Specific attacks considered:
1. **JSON vs. Wire Format Mismatch**:
   - *Attack*: Providing a modified JSON receipt or balance change while presenting unrelated or corrupted raw transaction bytes.
   - *Defense*: M1 ignores JSON descriptions of fields during cryptographic verification; `raw_tx` bytes are the sole cryptographic source of truth.
2. **Envelope Stripping / Direct RLP Attack**:
   - *Attack*: Stripping the EIP-2718 type byte (`0x01`, `0x02`, `0x03`) and hashing the underlying RLP list directly, or vice-versa, to forge transaction hashes.
   - *Defense*: Envelope type identification strictly determines hash input framing. For typed transactions, the single byte prefix is preserved in the Keccak-256 pre-image.
3. **Malleated / Non-Canonical RLP Encodings**:
   - *Attack*: Inserting leading zeros into integer values (e.g. `nonce = 0x0001` instead of `0x01`), using long-string prefixes for payloads $< 56$ bytes, or appending extraneous bytes after the transaction payload.
   - *Defense*: Strict canonical parser rules reject non-minimal encodings, and a roundtrip reserialization check enforces byte-for-byte fidelity.
4. **NIST SHA3-256 Substitution**:
   - *Attack*: Using standard FIPS 202 SHA3-256 (e.g. standard `hashlib.sha3_256`) rather than Ethereum Keccak-256, causing systematic silent divergences across all typed and legacy transactions.
   - *Defense*: Built-in self-testing and distinct padding constants guarantee that Keccak-256 cannot be replaced with NIST SHA3.
5. **Memory Exhaustion & Denial of Service**:
   - *Attack*: Passing gigabyte-sized payloads or recursively nested RLP trees to exhaust memory.
   - *Defense*: Input size is bounded (default max 2 MB), recursion depth is bounded to 4 levels, and array allocations are pre-checked against slice bounds.

---

## 3. Explicit Boundaries: What M1 Does NOT Guarantee

To prevent deceptive marketing or overclaiming in grant proposals and technical papers, the boundaries of M1 are defined below:

| Feature / Property | Included in M1? | Reason / Scoped Milestone |
|---|---|---|
| **Cryptographic Byte Identity** | **YES** | Proves `Keccak-256(raw_tx) == claimed_hash` and canonical encoding. |
| **Canonical RLP & EIP-2718 Envelope** | **YES** | Validates exact wire format and field structure. |
| **Fail-closed Error Taxonomy** | **YES** | Deterministic error codes for malformed/non-canonical data. |
| **Block Inclusion Proof** | **NO** | Requires block header `transactionsRoot` and Merkle-Patricia Trie (scoped for M2/M3). |
| **Finality / Consensus Proof** | **NO** | Requires Proof-of-Stake Casper FFG checkpoint / sync committee validation (scoped for later). |
| **Signer Key Recovery (ECDSA)** | **NO** | `ecrecover` recovery from $(v, r, s)$ requires secp256k1 engine; kept outside M1 core to minimize TCB. |
| **Account Nonce / Balance Validity** | **NO** | Requires state trie lookup (`stateRoot`). |
| **EVM Execution / Revert Status** | **NO** | Requires EVM bytecode interpreter; transaction hash is valid even if transaction reverts. |

---

## 4. Policy on Claims (Grant & Research Communications)

Any paper, proposal, documentation, or public repository statement regarding Lin-Audit M1 MUST adhere to the following permitted vs. forbidden claims:

### Permitted Claims
- *"Lin-Audit M1 provides an independent, fail-closed verifier for Ethereum transaction wire format and Keccak-256 digests."*
- *"The verifier validates canonical RLP and EIP-2718 envelopes across Legacy, EIP-2930, EIP-1559, and EIP-4844 transactions."*
- *"The cryptographic calculation is reproducible offline without connection to an Ethereum RPC node."*
- *"The parser rejects non-canonical integer serializations, trailing bytes, and arity mismatches."*

### Forbidden Claims
- ❌ *"Lin-Audit proves the transaction was executed by the Ethereum network."* (False: M1 does not check inclusion or execution).
- ❌ *"Lin-Audit verifies the full Ethereum state."* (False: M1 only checks transaction byte identity).
- ❌ *"Lin-Audit replaces an Ethereum archive node."* (False: M1 is an audit component, not an indexer or archive node).
- ❌ *"Lin-Audit guarantees the funds were transferred."* (False: A transaction can have a valid hash and canonical encoding but revert during EVM execution).
