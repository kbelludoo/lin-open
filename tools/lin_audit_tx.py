#!/usr/bin/env python3
"""
Lin-Audit Ethereum — Milestone 1 (M1) Transaction Verifier
Reference Implementation: Canonical RLP, Envelope Parsing, and Keccak-256.

Zero external pip dependencies required (Python 3.8+ standard library only).
Strictly distinguishes Keccak-256 (Ethereum) from NIST SHA3-256 (FIPS 202).
"""

import sys
import os
import json
import argparse
from typing import List, Tuple, Union, Optional, Dict, Any

# ==============================================================================
# 1. PURE PYTHON BIT-EXACT KECCAK-256
# ==============================================================================

# Round Constants for Keccak-f[1600]
KECCAK_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008
]

# Rotation offsets r[x][y]
ROTATION_OFFSETS = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14]
]

def _rol64(x: int, n: int) -> int:
    return ((x << (n % 64)) & 0xFFFFFFFFFFFFFFFF) | (x >> (64 - (n % 64)))

def keccak_f1600(state: List[List[int]]) -> None:
    """In-place Keccak-f[1600] 24-round permutation on 5x5 state of 64-bit lanes."""
    for ir in range(24):
        # 1. Theta Step
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol64(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]

        # 2. Rho & Pi Steps
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol64(state[x][y], ROTATION_OFFSETS[x][y])

        # 3. Chi Step
        for x in range(5):
            for y in range(5):
                state[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) & 0xFFFFFFFFFFFFFFFF

        # 4. Iota Step
        state[0][0] ^= KECCAK_RC[ir]

def keccak256(data: bytes) -> bytes:
    """
    Computes Ethereum Keccak-256 digest over input bytes.
    Rate = 1088 bits (136 bytes), Capacity = 512 bits (64 bytes).
    Domain padding: 0x01 ... 0x80 (distinct from NIST SHA3-256 which uses 0x06).
    """
    rate_bytes = 136
    # 5x5 64-bit state
    state = [[0] * 5 for _ in range(5)]

    # Padding: message || 0x01 || 0x00* || 0x80
    pad_len = rate_bytes - (len(data) % rate_bytes)
    if pad_len == 1:
        padded = data + b'\x81'
    else:
        padded = data + b'\x01' + (b'\x00' * (pad_len - 2)) + b'\x80'

    # Absorb phase
    for block_idx in range(0, len(padded), rate_bytes):
        block = padded[block_idx:block_idx + rate_bytes]
        for i in range(17):  # 17 * 8 = 136 bytes rate
            lane_bytes = block[i * 8:(i + 1) * 8]
            lane_val = int.from_bytes(lane_bytes, byteorder='little')
            x = i % 5
            y = i // 5
            state[x][y] ^= lane_val
        keccak_f1600(state)

    # Squeeze phase: 32 bytes (4 64-bit lanes)
    out = bytearray()
    for i in range(4):
        x = i % 5
        y = i // 5
        out.extend(state[x][y].to_bytes(8, byteorder='little'))

    return bytes(out)

def nist_sha3_256(data: bytes) -> bytes:
    """NIST FIPS 202 SHA3-256 (padding 0x06) used to verify divergence from Keccak-256."""
    rate_bytes = 136
    state = [[0] * 5 for _ in range(5)]
    pad_len = rate_bytes - (len(data) % rate_bytes)
    if pad_len == 1:
        padded = data + b'\x86'
    else:
        padded = data + b'\x06' + (b'\x00' * (pad_len - 2)) + b'\x80'

    for block_idx in range(0, len(padded), rate_bytes):
        block = padded[block_idx:block_idx + rate_bytes]
        for i in range(17):
            lane_bytes = block[i * 8:(i + 1) * 8]
            lane_val = int.from_bytes(lane_bytes, byteorder='little')
            x = i % 5
            y = i // 5
            state[x][y] ^= lane_val
        keccak_f1600(state)

    out = bytearray()
    for i in range(4):
        x = i % 5
        y = i // 5
        out.extend(state[x][y].to_bytes(8, byteorder='little'))
    return bytes(out)

# ==============================================================================
# 2. CANONICAL RLP PARSER & ENCODER
# ==============================================================================

class RLPError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

class RLPItem:
    def __init__(self, is_list: bool, data: Union[bytes, List['RLPItem']], raw_slice: bytes):
        self.is_list = is_list
        self.data = data
        self.raw_slice = raw_slice

    def to_python(self) -> Any:
        if self.is_list:
            return [child.to_python() for child in self.data]  # type: ignore
        return bytes(self.data)  # type: ignore

def encode_canonical_rlp(item: Union[bytes, int, list]) -> bytes:
    """Canonical RLP serialiser."""
    if isinstance(item, int):
        if item == 0:
            return b'\x80'
        # minimal big-endian without leading zeros
        n_bytes = (item.bit_length() + 7) // 8
        b_val = item.to_bytes(n_bytes, byteorder='big')
        return encode_canonical_rlp(b_val)
    elif isinstance(item, (bytes, bytearray)):
        b = bytes(item)
        if len(b) == 1 and b[0] < 0x80:
            return b
        elif len(b) <= 55:
            return bytes([0x80 + len(b)]) + b
        else:
            len_bytes = (len(b).bit_length() + 7) // 8
            l_b = len(b).to_bytes(len_bytes, byteorder='big')
            return bytes([0xb7 + len(l_b)]) + l_b + b
    elif isinstance(item, list):
        payload = b''.join(encode_canonical_rlp(child) for child in item)
        if len(payload) <= 55:
            return bytes([0xc0 + len(payload)]) + payload
        else:
            len_bytes = (len(payload).bit_length() + 7) // 8
            l_b = len(payload).to_bytes(len_bytes, byteorder='big')
            return bytes([0xf7 + len(l_b)]) + l_b + payload
    else:
        raise ValueError(f"Unsupported type for RLP encoding: {type(item)}")

def parse_canonical_rlp(data: bytes, offset: int = 0) -> Tuple[RLPItem, int]:
    """
    Parses exactly one RLP item starting at `offset`.
    Strictly checks canonical length prefixes and rejects leading zeros in lengths.
    Returns (RLPItem, next_offset).
    """
    if offset >= len(data):
        raise RLPError("MALFORMED", f"Unexpected EOF at byte {offset}")

    b0 = data[offset]

    # 1. Single byte < 0x80
    if b0 < 0x80:
        return RLPItem(is_list=False, data=bytes([b0]), raw_slice=data[offset:offset + 1]), offset + 1

    # 2. Short string (0 <= len <= 55)
    elif b0 <= 0xb7:
        length = b0 - 0x80
        start = offset + 1
        end = start + length
        if end > len(data):
            raise RLPError("MALFORMED", f"String length {length} exceeds buffer size at offset {offset}")
        raw_slice = data[offset:end]
        val = data[start:end]
        if length == 1 and val[0] < 0x80:
            raise RLPError("NON_CANONICAL", f"Single byte < 0x80 encoded as string prefix: 0x{val[0]:02x}")
        return RLPItem(is_list=False, data=val, raw_slice=raw_slice), end

    # 3. Long string (len > 55)
    elif b0 < 0xc0:
        len_of_len = b0 - 0xb7
        len_start = offset + 1
        len_end = len_start + len_of_len
        if len_end > len(data):
            raise RLPError("MALFORMED", f"Length of string length exceeds buffer at offset {offset}")
        len_bytes = data[len_start:len_end]
        if len_bytes[0] == 0:
            raise RLPError("NON_CANONICAL", f"Leading zero in long string length prefix at offset {offset}")
        str_len = int.from_bytes(len_bytes, byteorder='big')
        if str_len <= 55:
            raise RLPError("NON_CANONICAL", f"Long string encoding used for length <= 55 ({str_len})")
        data_start = len_end
        data_end = data_start + str_len
        if data_end > len(data):
            raise RLPError("MALFORMED", f"Long string payload length {str_len} exceeds buffer")
        return RLPItem(is_list=False, data=data[data_start:data_end], raw_slice=data[offset:data_end]), data_end

    # 4. Short list (0 <= payload_len <= 55)
    elif b0 <= 0xf7:
        payload_len = b0 - 0xc0
        list_start = offset + 1
        list_end = list_start + payload_len
        if list_end > len(data):
            raise RLPError("MALFORMED", f"List payload length {payload_len} exceeds buffer at offset {offset}")
        children: List[RLPItem] = []
        curr = list_start
        while curr < list_end:
            child, curr = parse_canonical_rlp(data, curr)
            children.append(child)
        if curr != list_end:
            raise RLPError("MALFORMED", f"List items did not align to declared boundary ({curr} != {list_end})")
        return RLPItem(is_list=True, data=children, raw_slice=data[offset:list_end]), list_end

    # 5. Long list (payload_len > 55)
    else:
        len_of_len = b0 - 0xf7
        len_start = offset + 1
        len_end = len_start + len_of_len
        if len_end > len(data):
            raise RLPError("MALFORMED", f"Length of list length exceeds buffer at offset {offset}")
        len_bytes = data[len_start:len_end]
        if len_bytes[0] == 0:
            raise RLPError("NON_CANONICAL", f"Leading zero in long list length prefix at offset {offset}")
        payload_len = int.from_bytes(len_bytes, byteorder='big')
        if payload_len <= 55:
            raise RLPError("NON_CANONICAL", f"Long list encoding used for payload length <= 55 ({payload_len})")
        list_start = len_end
        list_end = list_start + payload_len
        if list_end > len(data):
            raise RLPError("MALFORMED", f"Long list payload length {payload_len} exceeds buffer")
        children = []
        curr = list_start
        while curr < list_end:
            child, curr = parse_canonical_rlp(data, curr)
            children.append(child)
        if curr != list_end:
            raise RLPError("MALFORMED", f"List items did not align to declared boundary ({curr} != {list_end})")
        return RLPItem(is_list=True, data=children, raw_slice=data[offset:list_end]), list_end

# ==============================================================================
# 3. TRANSACTION ENVELOPE & SEMANTIC VALIDATOR
# ==============================================================================

def validate_canonical_integer(b: bytes, field_name: str) -> int:
    """Validates that a byte sequence is a canonical minimal big-endian integer."""
    if len(b) == 0:
        return 0
    if b[0] == 0:
        raise RLPError("NON_CANONICAL", f"Field '{field_name}' contains leading zero byte in integer encoding")
    return int.from_bytes(b, byteorder='big')

def validate_address(b: bytes, field_name: str) -> Optional[str]:
    """Validates that address is either empty (contract creation) or exactly 20 bytes."""
    if len(b) == 0:
        return None
    if len(b) != 20:
        raise RLPError("INVALID_FIELD_LENGTH", f"Address field '{field_name}' must be 0 or 20 bytes, got {len(b)}")
    return "0x" + b.hex()

def validate_signature_component(b: bytes, field_name: str) -> int:
    """Validates r or s component (canonical big-endian <= 32 bytes)."""
    val = validate_canonical_integer(b, field_name)
    if len(b) > 32:
        raise RLPError("INVALID_FIELD_LENGTH", f"Signature component '{field_name}' exceeds 32 bytes ({len(b)} bytes)")
    return val

def decode_and_validate_tx(raw_tx: bytes) -> Dict[str, Any]:
    """
    Decodes an Ethereum transaction, validates envelope and canonical RLP,
    and returns parsed structural fields.
    """
    if len(raw_tx) == 0:
        raise RLPError("MALFORMED", "Raw transaction is empty")

    first_byte = raw_tx[0]
    tx_type: int
    payload_slice: bytes

    # EIP-2718 Typed Transaction Envelope
    if 0x01 <= first_byte <= 0x7F:
        tx_type = first_byte
        payload_slice = raw_tx[1:]
        if tx_type not in (1, 2, 3, 4):
            raise RLPError("UNSUPPORTED_TYPE", f"Unsupported EIP-2718 transaction type: 0x{tx_type:02x}")
    elif first_byte >= 0xC0:
        tx_type = 0  # Legacy / EIP-155
        payload_slice = raw_tx
    else:
        raise RLPError("MALFORMED", f"Invalid transaction initial byte: 0x{first_byte:02x}")

    # Parse RLP payload
    root_item, next_offset = parse_canonical_rlp(payload_slice, 0)
    if next_offset != len(payload_slice):
        residual = len(payload_slice) - next_offset
        raise RLPError("MALFORMED", f"Found {residual} residual/trailing bytes after root RLP item")

    if not root_item.is_list:
        raise RLPError("MALFORMED", "Transaction RLP payload must be a list")

    fields: List[RLPItem] = root_item.data  # type: ignore

    # Roundtrip reserialization check
    reserialized = encode_canonical_rlp(root_item.to_python())
    if reserialized != payload_slice:
        raise RLPError("NON_CANONICAL", "Decoded payload does not match canonical RLP reserialization")

    decoded: Dict[str, Any] = {
        "tx_type": tx_type,
        "tx_type_name": {0: "Legacy/EIP-155", 1: "EIP-2930", 2: "EIP-1559", 3: "EIP-4844", 4: "EIP-7702"}.get(tx_type, "Unknown"),
    }

    if tx_type == 0:
        # Legacy: [nonce, gasPrice, gasLimit, to, value, data, v, r, s]
        if len(fields) != 9:
            raise RLPError("WRONG_ARITY", f"Legacy transaction must have 9 fields, got {len(fields)}")
        for i in [0, 1, 2, 3, 4, 5, 6, 7, 8]:
            if fields[i].is_list:
                raise RLPError("MALFORMED", f"Legacy field at index {i} must not be a list")

        decoded["nonce"] = validate_canonical_integer(fields[0].data, "nonce")
        decoded["gas_price"] = validate_canonical_integer(fields[1].data, "gasPrice")
        decoded["gas_limit"] = validate_canonical_integer(fields[2].data, "gasLimit")
        decoded["to"] = validate_address(fields[3].data, "to")
        decoded["value"] = validate_canonical_integer(fields[4].data, "value")
        decoded["data"] = "0x" + bytes(fields[5].data).hex()
        decoded["v"] = validate_canonical_integer(fields[6].data, "v")
        decoded["r"] = validate_signature_component(fields[7].data, "r")
        decoded["s"] = validate_signature_component(fields[8].data, "s")

    elif tx_type == 1:
        # EIP-2930: [chainId, nonce, gasPrice, gasLimit, to, value, data, accessList, yParity, r, s]
        if len(fields) != 11:
            raise RLPError("WRONG_ARITY", f"EIP-2930 transaction must have 11 fields, got {len(fields)}")
        if not fields[7].is_list:
            raise RLPError("MALFORMED", "EIP-2930 accessList must be a list")

        decoded["chain_id"] = validate_canonical_integer(fields[0].data, "chainId")
        decoded["nonce"] = validate_canonical_integer(fields[1].data, "nonce")
        decoded["gas_price"] = validate_canonical_integer(fields[2].data, "gasPrice")
        decoded["gas_limit"] = validate_canonical_integer(fields[3].data, "gasLimit")
        decoded["to"] = validate_address(fields[4].data, "to")
        decoded["value"] = validate_canonical_integer(fields[5].data, "value")
        decoded["data"] = "0x" + bytes(fields[6].data).hex()
        decoded["access_list_count"] = len(fields[7].data)
        decoded["y_parity"] = validate_canonical_integer(fields[8].data, "yParity")
        decoded["r"] = validate_signature_component(fields[9].data, "r")
        decoded["s"] = validate_signature_component(fields[10].data, "s")

    elif tx_type == 2:
        # EIP-1559: [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList, yParity, r, s]
        if len(fields) != 12:
            raise RLPError("WRONG_ARITY", f"EIP-1559 transaction must have 12 fields, got {len(fields)}")
        if not fields[8].is_list:
            raise RLPError("MALFORMED", "EIP-1559 accessList must be a list")

        decoded["chain_id"] = validate_canonical_integer(fields[0].data, "chainId")
        decoded["nonce"] = validate_canonical_integer(fields[1].data, "nonce")
        decoded["max_priority_fee_per_gas"] = validate_canonical_integer(fields[2].data, "maxPriorityFeePerGas")
        decoded["max_fee_per_gas"] = validate_canonical_integer(fields[3].data, "maxFeePerGas")
        decoded["gas_limit"] = validate_canonical_integer(fields[4].data, "gasLimit")
        decoded["to"] = validate_address(fields[5].data, "to")
        decoded["value"] = validate_canonical_integer(fields[6].data, "value")
        decoded["data"] = "0x" + bytes(fields[7].data).hex()
        decoded["access_list_count"] = len(fields[8].data)
        decoded["y_parity"] = validate_canonical_integer(fields[9].data, "yParity")
        decoded["r"] = validate_signature_component(fields[10].data, "r")
        decoded["s"] = validate_signature_component(fields[11].data, "s")

    elif tx_type == 3:
        # EIP-4844: [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas, gasLimit, to, value, data, accessList, maxFeePerBlobGas, blobVersionedHashes, yParity, r, s]
        if len(fields) != 14:
            raise RLPError("WRONG_ARITY", f"EIP-4844 transaction must have 14 fields, got {len(fields)}")
        if not fields[8].is_list:
            raise RLPError("MALFORMED", "EIP-4844 accessList must be a list")
        if not fields[10].is_list:
            raise RLPError("MALFORMED", "EIP-4844 blobVersionedHashes must be a list")

        decoded["chain_id"] = validate_canonical_integer(fields[0].data, "chainId")
        decoded["nonce"] = validate_canonical_integer(fields[1].data, "nonce")
        decoded["max_priority_fee_per_gas"] = validate_canonical_integer(fields[2].data, "maxPriorityFeePerGas")
        decoded["max_fee_per_gas"] = validate_canonical_integer(fields[3].data, "maxFeePerGas")
        decoded["gas_limit"] = validate_canonical_integer(fields[4].data, "gasLimit")
        decoded["to"] = validate_address(fields[5].data, "to")
        if decoded["to"] is None:
            raise RLPError("MALFORMED", "EIP-4844 cannot be a contract creation (to cannot be null)")
        decoded["value"] = validate_canonical_integer(fields[6].data, "value")
        decoded["data"] = "0x" + bytes(fields[7].data).hex()
        decoded["access_list_count"] = len(fields[8].data)
        decoded["max_fee_per_blob_gas"] = validate_canonical_integer(fields[9].data, "maxFeePerBlobGas")
        
        # Validate blob versioned hashes (each must be 32 bytes and start with 0x01)
        blob_hashes = []
        for b_item in fields[10].data:
            if b_item.is_list or len(b_item.data) != 32:
                raise RLPError("INVALID_FIELD_LENGTH", "Blob versioned hash must be exactly 32 bytes")
            if b_item.data[0] != 0x01:
                raise RLPError("MALFORMED", f"Blob versioned hash must begin with 0x01, got 0x{b_item.data[0]:02x}")
            blob_hashes.append("0x" + bytes(b_item.data).hex())
        decoded["blob_versioned_hashes"] = blob_hashes
        decoded["blob_count"] = len(blob_hashes)

        decoded["y_parity"] = validate_canonical_integer(fields[11].data, "yParity")
        decoded["r"] = validate_signature_component(fields[12].data, "r")
        decoded["s"] = validate_signature_component(fields[13].data, "s")

    elif tx_type == 4:
        # EIP-7702 Extension
        decoded["status"] = "EXPERIMENTAL_EXTENSION"

    return decoded

# ==============================================================================
# 4. VERIFICATION PIPELINE
# ==============================================================================

def verify_ethereum_tx(raw_hex: str, claimed_hash: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the full M1 cryptographic and structural verification pipeline.
    Returns structured JSON output per LIN_AUDIT_ETH_M1_V1.
    """
    errors: List[str] = []
    clean_hex = raw_hex.strip()
    if clean_hex.startswith("0x") or clean_hex.startswith("0X"):
        clean_hex = clean_hex[2:]

    result: Dict[str, Any] = {
        "schema": "LIN_AUDIT_ETH_M1_V1",
        "valid_encoding": False,
        "tx_type": None,
        "tx_type_name": None,
        "canonical_payload": None,
        "recomputed_hash": None,
        "claimed_hash": claimed_hash,
        "hash_matches": None,
        "semantic_valid": False,
        "verdict": "FAIL",
        "errors": errors
    }

    try:
        raw_bytes = bytes.fromhex(clean_hex)
    except ValueError as e:
        errors.append("MALFORMED: Invalid hexadecimal input")
        return result

    if len(raw_bytes) > 2 * 1024 * 1024:  # 2MB defense limit
        errors.append("MALFORMED: Raw transaction exceeds maximum size of 2MB")
        return result

    # Compute Keccak-256 over exact wire bytes
    recomputed_hash_bytes = keccak256(raw_bytes)
    recomputed_hash_hex = "0x" + recomputed_hash_bytes.hex()
    result["recomputed_hash"] = recomputed_hash_hex

    if claimed_hash:
        claimed_norm = claimed_hash.lower()
        if not claimed_norm.startswith("0x"):
            claimed_norm = "0x" + claimed_norm
        result["claimed_hash"] = claimed_norm
        result["hash_matches"] = (recomputed_hash_hex == claimed_norm)
        if not result["hash_matches"]:
            errors.append(f"HASH_MISMATCH: Computed {recomputed_hash_hex} != Claimed {claimed_norm}")

    # Decode and validate structural and canonical RLP rules
    try:
        decoded = decode_and_validate_tx(raw_bytes)
        result["valid_encoding"] = True
        result["semantic_valid"] = True
        result["tx_type"] = decoded.get("tx_type")
        result["tx_type_name"] = decoded.get("tx_type_name")
        result["canonical_payload"] = "0x" + raw_bytes.hex()
        result["decoded_fields"] = decoded
    except RLPError as e:
        errors.append(f"{e.code}: {str(e)}")
        if e.code == "UNSUPPORTED_TYPE":
            result["verdict"] = "UNSUPPORTED_TYPE"
            return result
    except Exception as e:
        errors.append(f"MALFORMED: {str(e)}")

    if result["valid_encoding"] and result["semantic_valid"]:
        if claimed_hash is None or result["hash_matches"] is True:
            result["verdict"] = "PASS"
        else:
            result["verdict"] = "FAIL"
    else:
        result["verdict"] = "FAIL"

    return result

# ==============================================================================
# 5. CLI INTERFACE
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Lin-Audit Ethereum — Milestone 1 (M1) Transaction Verifier"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: tx-hash
    hash_parser = subparsers.add_parser("tx-hash", help="Verify raw transaction bytes against claimed hash")
    hash_parser.add_argument("--raw", required=True, help="Raw transaction hex (with or without 0x)")
    hash_parser.add_argument("--claimed", required=False, help="Claimed transaction hash hex")

    # Command: tx-decode
    decode_parser = subparsers.add_parser("tx-decode", help="Decode and inspect transaction fields")
    decode_parser.add_argument("--raw", required=True, help="Raw transaction hex")

    # Command: tx-file
    file_parser = subparsers.add_parser("tx-file", help="Verify a single JSON fixture file")
    file_parser.add_argument("--file", required=True, help="Path to fixture JSON")

    # Command: corpus verify
    corpus_parser = subparsers.add_parser("corpus", help="Corpus operations")
    corpus_subparsers = corpus_parser.add_subparsers(dest="corpus_command", required=True)
    verify_parser = corpus_subparsers.add_parser("verify", help="Verify entire fixture directory")
    verify_parser.add_argument("--dir", required=True, help="Directory containing JSON fixtures")
    verify_parser.add_argument("--report", required=False, help="Path to write JSON report")

    args = parser.parse_args()

    if args.command == "tx-hash":
        report = verify_ethereum_tx(args.raw, args.claimed)
        print(json.dumps(report, indent=2))
        if report["verdict"] == "PASS":
            sys.exit(0)
        elif report["verdict"] == "UNSUPPORTED_TYPE":
            sys.exit(2)
        else:
            sys.exit(1)

    elif args.command == "tx-decode":
        report = verify_ethereum_tx(args.raw)
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["valid_encoding"] else 1)

    elif args.command == "tx-file":
        if not os.path.exists(args.file):
            print(json.dumps({"error": f"File not found: {args.file}"}), file=sys.stderr)
            sys.exit(3)
        with open(args.file, "r", encoding="utf-8") as f:
            fixture = json.load(f)
        raw_tx = fixture.get("raw_tx") or fixture.get("raw")
        claimed_hash = fixture.get("claimed_hash") or fixture.get("hash")
        if not raw_tx:
            print(json.dumps({"error": "Fixture missing raw_tx"}), file=sys.stderr)
            sys.exit(3)
        report = verify_ethereum_tx(raw_tx, claimed_hash)
        print(json.dumps(report, indent=2))
        if report["verdict"] == "PASS":
            sys.exit(0)
        elif report["verdict"] == "UNSUPPORTED_TYPE":
            sys.exit(2)
        else:
            sys.exit(1)

    elif args.command == "corpus" and args.corpus_command == "verify":
        if not os.path.isdir(args.dir):
            print(f"Directory not found: {args.dir}", file=sys.stderr)
            sys.exit(3)

        files = [os.path.join(args.dir, f) for f in os.listdir(args.dir) if f.endswith(".json")]
        files.sort()
        passed = 0
        failed = 0
        unsupported = 0
        details = []

        for fpath in files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    fix = json.load(f)
                raw_tx = fix.get("raw_tx") or fix.get("raw")
                claimed = fix.get("claimed_hash") or fix.get("hash")
                if not raw_tx:
                    continue
                rep = verify_ethereum_tx(raw_tx, claimed)
                rep["fixture_file"] = os.path.basename(fpath)
                details.append(rep)
                if rep["verdict"] == "PASS":
                    passed += 1
                elif rep["verdict"] == "UNSUPPORTED_TYPE":
                    unsupported += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                details.append({"fixture_file": os.path.basename(fpath), "verdict": "FAIL", "errors": [str(e)]})

        summary = {
            "total_fixtures": len(details),
            "passed": passed,
            "failed": failed,
            "unsupported": unsupported,
            "all_passed": (failed == 0 and unsupported == 0 and passed > 0)
        }
        full_report = {"summary": summary, "details": details}

        if args.report:
            with open(args.report, "w", encoding="utf-8") as rf:
                json.dump(full_report, rf, indent=2)
            print(f"Verified {len(details)} fixtures: {passed} PASS, {failed} FAIL, {unsupported} UNSUPPORTED. Report saved to {args.report}")
        else:
            print(json.dumps(full_report, indent=2))

        sys.exit(0 if summary["all_passed"] else 1)

if __name__ == "__main__":
    main()
