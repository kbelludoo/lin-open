#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN Standalone Pilot Verifier — uint256 (LCR2 Schema, 208 Bytes)
Zero-Trust, Zero-Knowledge:
  - Não executa código LIN nem confia em campos redundantes não verificados
  - Valida o registro canônico LCR2 de 208 bytes contra todos os campos do bundle JSON
  - Valida prefixos de domínio LIN:LEAF:1 e LIN:NODE:1 (FIPS 180-4 SHA-256)
  - Prova de inclusão O(log B) = O(1) em bloco B=4
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
SCHEMA_ID = b"LCR2"
SCHEMA_VERSION = 1
PROFILE_LINVM1 = 1

def verify_u256_block_bundle(
    bundle_data: Dict[str, Any],
    expected_image_digest: str,
    seen_tx_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    if not isinstance(bundle_data, dict):
        return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_JSON_ROOT"}

    actual_img_digest = bundle_data.get("image_loader_digest")
    if actual_img_digest != expected_image_digest:
        return {
            "schema": "LIN_VERIFY_RESULT_U256_1",
            "valid": False,
            "reason": "BAD_IMAGE_DIGEST",
            "detail": f"Esperado {expected_image_digest}, recebido {actual_img_digest}"
        }

    merkle_root = bundle_data.get("merkle_root_sha256")
    if not merkle_root or len(merkle_root) != 64:
        return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_ROOT_LENGTH"}

    try:
        bytes.fromhex(merkle_root)
    except ValueError:
        return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_ROOT_HEX"}

    txs = bundle_data.get("transactions", [])
    if not isinstance(txs, list) or len(txs) != 4:
        return {
            "schema": "LIN_VERIFY_RESULT_U256_1",
            "valid": False,
            "reason": "BLOCK_POLICY",
            "detail": f"Bloco deve conter exatamente 4 transações (recebido {len(txs) if isinstance(txs, list) else 'invalid'})"
        }

    def h_parent(l: bytes, r: bytes) -> bytes:
        return hashlib.sha256(DOM_NODE + l + r).digest()

    computed_leaves = []
    if seen_tx_ids is None:
        seen_tx_ids = set()

    for idx, tx in enumerate(txs):
        if not isinstance(tx, dict):
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_TX_ENTRY"}

        raw_hex = tx.get("raw_record_hex")
        if not raw_hex or not isinstance(raw_hex, str):
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_HEX"}

        try:
            raw_rec = bytes.fromhex(raw_hex)
        except ValueError:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_HEX"}

        if len(raw_rec) != 208:
            return {
                "schema": "LIN_VERIFY_RESULT_U256_1",
                "valid": False,
                "reason": "BAD_LENGTH",
                "detail": f"Registro LCR2 com tamanho {len(raw_rec)} != 208 bytes"
            }

        # Header 0..7: LCR2, v=1, p=1, reserved=0
        if raw_rec[0:4] != SCHEMA_ID:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_MAGIC"}
        if raw_rec[4] != SCHEMA_VERSION:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_VERSION"}
        if raw_rec[5] != PROFILE_LINVM1:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_PROFILE"}
        if raw_rec[6:8] != b"\x00\x00":
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RESERVED"}

        img_in_rec = raw_rec[8:40].hex()
        if img_in_rec != actual_img_digest:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_IMAGE_DIGEST"}

        run_id, tx_id = struct.unpack_from("<QQ", raw_rec, 40)
        ain_be = raw_rec[56:88]
        rin_be = raw_rec[88:120]
        rout_be = raw_rec[120:152]
        aout_be = raw_rec[152:184]
        steps, status = struct.unpack_from("<Qq", raw_rec, 184)

        if tx.get("run_id") != run_id:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "run_id"}
        if tx.get("tx_id") != tx_id:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "tx_id"}
        if tx.get("amount_in_hex") != ain_be.hex():
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "amount_in"}
        if tx.get("reserve_in_hex") != rin_be.hex():
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "reserve_in"}
        if tx.get("reserve_out_hex") != rout_be.hex():
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "reserve_out"}
        if tx.get("amount_out_hex") != aout_be.hex():
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "amount_out"}
        if tx.get("steps") != steps:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "steps"}
        if tx.get("status_code") != status:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "status_code"}

        if tx_id in seen_tx_ids:
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "REPLAY", "detail": f"tx_id={tx_id}"}
        seen_tx_ids.add(tx_id)

        leaf_h = hashlib.sha256(DOM_LEAF + raw_rec).digest()
        if tx.get("leaf_hash_hex") != leaf_h.hex():
            return {"schema": "LIN_VERIFY_RESULT_U256_1", "valid": False, "reason": "BAD_LEAF_HASH"}
        computed_leaves.append(leaf_h)

    n0 = h_parent(computed_leaves[0], computed_leaves[1])
    n1 = h_parent(computed_leaves[2], computed_leaves[3])
    expected_root = h_parent(n0, n1).hex()

    if expected_root != merkle_root:
        return {
            "schema": "LIN_VERIFY_RESULT_U256_1",
            "valid": False,
            "reason": "BAD_ROOT",
            "detail": f"Calculado {expected_root}, declarado {merkle_root}"
        }

    return {
        "schema": "LIN_VERIFY_RESULT_U256_1",
        "valid": True,
        "reason": "OK",
        "image_loader_digest": actual_img_digest,
        "merkle_root_sha256": merkle_root,
        "checks": {
            "image_digest": True,
            "canonical_record": True,
            "leaf_digest": True,
            "merkle_path": True,
            "replay_policy": True
        }
    }

if __name__ == "__main__":
    print("Verificador Independente LCR2 uint256 carregado com sucesso.")
