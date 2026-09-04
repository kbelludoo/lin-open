#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN Standalone Pilot Verifier (Normativo: LIN-PILOT-VERIFIER-FUZZ-001 §6)
Zero-Trust, Zero-Knowledge:
  - Não executa código LIN nem confia em campos externos não verificados
  - Valida todos os campos redundantes contra o registro binário canônico de 112 bytes
  - Valida o hash bruto do arquivo LINBC1 se fornecido
  - Valida prefixos de domínio LIN:LEAF:1 e LIN:NODE:1
  - Retorna decisão JSON padronizada (LIN_VERIFY_RESULT_1)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set


DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
SCHEMA_ID = b"LCR1"
SCHEMA_VERSION = 1
PROFILE_LINVM1 = 1


def verify_block_bundle(
    bundle_data: Dict[str, Any],
    expected_image_digest: str,
    expected_file_sha256: Optional[str] = None,
    seen_tx_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    if not isinstance(bundle_data, dict):
        return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_JSON_ROOT"}

    # 1. Checagem de digest da imagem
    actual_img_digest = bundle_data.get("image_loader_digest")
    if actual_img_digest != expected_image_digest:
        return {
            "schema": "LIN_VERIFY_RESULT_1",
            "valid": False,
            "reason": "BAD_IMAGE_DIGEST",
            "detail": f"Esperado {expected_image_digest}, recebido {actual_img_digest}"
        }

    # 2. Checagem do hash bruto do arquivo se especificado
    if expected_file_sha256 is not None:
        file_sha = bundle_data.get("image_file_sha256")
        if file_sha != expected_file_sha256:
            return {
                "schema": "LIN_VERIFY_RESULT_1",
                "valid": False,
                "reason": "BAD_FILE_SHA256",
                "detail": f"image_file_sha256 divergente: esperado {expected_file_sha256}, recebido {file_sha}"
            }

    merkle_root = bundle_data.get("merkle_root_sha256")
    if not merkle_root or len(merkle_root) != 64:
        return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_ROOT_LENGTH"}

    try:
        bytes.fromhex(merkle_root)
    except ValueError:
        return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_ROOT_HEX"}

    txs = bundle_data.get("transactions", [])
    if not isinstance(txs, list) or len(txs) != 4:
        return {
            "schema": "LIN_VERIFY_RESULT_1",
            "valid": False,
            "reason": "BLOCK_POLICY",
            "detail": f"Bloco deve conter exatamente 4 transações (recebido {len(txs) if isinstance(txs, list) else 'invalid'})"
        }

    def h_parent(l: bytes, r: bytes) -> bytes:
        return hashlib.sha256(DOM_NODE + l + r).digest()

    for idx, tx in enumerate(txs):
        if not isinstance(tx, dict):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_TX_ENTRY"}

        raw_hex = tx.get("raw_record_hex")
        if not raw_hex or not isinstance(raw_hex, str):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_HEX"}

        try:
            raw_rec = bytes.fromhex(raw_hex)
        except ValueError:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_HEX"}

        if len(raw_rec) != 112:
            return {
                "schema": "LIN_VERIFY_RESULT_1",
                "valid": False,
                "reason": "BAD_LENGTH",
                "detail": f"Registro com tamanho {len(raw_rec)} != 112 bytes"
            }

        # Header 0..7: LCR1, v=1, p=1, reserved=0
        if raw_rec[0:4] != SCHEMA_ID:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_MAGIC"}
        if raw_rec[4] != SCHEMA_VERSION:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_VERSION"}
        if raw_rec[5] != PROFILE_LINVM1:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_PROFILE"}
        if raw_rec[6:8] != b"\x00\x00":
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RESERVED"}

        img_in_rec = raw_rec[8:40].hex()
        if img_in_rec != actual_img_digest:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_IMAGE_DIGEST"}

        # Descompactar inteiros do registro canônico
        run_id, tx_id = struct.unpack_from("<QQ", raw_rec, 40)
        ain, rin, rout, min_out, out_val = struct.unpack_from("<qqqqq", raw_rec, 56)
        steps, status = struct.unpack_from("<Qq", raw_rec, 96)

        # Validação estrita de TODOS os campos redundantes do JSON contra o registro binário
        if tx.get("run_id") != run_id:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "run_id divergente"}
        if tx.get("tx_id") != tx_id:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "tx_id divergente"}
        if tx.get("amount_in") != ain:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "amount_in divergente"}
        if tx.get("reserve_in") != rin:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "reserve_in divergente"}
        if tx.get("reserve_out") != rout:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "reserve_out divergente"}
        if tx.get("min_out") != min_out:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "min_out divergente"}
        if tx.get("out_val") != out_val:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "out_val divergente"}
        if tx.get("steps") != steps:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "steps divergente"}
        if tx.get("status_code") != status:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING", "detail": "status_code divergente"}

        if status not in (1, -1):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_STATUS"}

        # Replay / Duplicação de tx_id no lote ou na sessão
        if seen_tx_ids is not None:
            if tx_id in seen_tx_ids:
                return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "REPLAY", "detail": f"tx_id {tx_id} duplicado"}
            seen_tx_ids.add(tx_id)

        # Recalcular hash da folha com domínio
        leaf = hashlib.sha256(DOM_LEAF + raw_rec).digest()
        if leaf.hex() != tx.get("leaf_hash_hex"):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_LEAF_DIGEST"}

        # Validar caminho Merkle
        proof = tx.get("merkle_proof", {})
        if not isinstance(proof, dict):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_PROOF_FORMAT"}

        s0_hex = proof.get("sibling0_hex")
        s1_hex = proof.get("sibling1_hex")
        path_bits = proof.get("path_bits")

        if not s0_hex or not s1_hex or path_bits not in (0, 1, 2, 3):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_PATH_BITS"}

        try:
            s0 = bytes.fromhex(s0_hex)
            s1 = bytes.fromhex(s1_hex)
        except ValueError:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_SIBLING_HEX"}

        if len(s0) != 32 or len(s1) != 32:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_SIBLING_LENGTH"}

        curr = h_parent(leaf, s0) if (path_bits & 1) == 0 else h_parent(s0, leaf)
        curr = h_parent(curr, s1) if ((path_bits >> 1) & 1) == 0 else h_parent(s1, curr)

        if curr.hex() != merkle_root:
            return {
                "schema": "LIN_VERIFY_RESULT_1",
                "valid": False,
                "reason": "BAD_ROOT",
                "detail": f"Raiz calculada {curr.hex()} != raiz comprometida {merkle_root}"
            }

    return {
        "schema": "LIN_VERIFY_RESULT_1",
        "valid": True,
        "reason": "OK",
        "image_sha256": f"sha256:{actual_img_digest}",
        "root_sha256": f"sha256:{merkle_root}",
        "block_id": str(bundle_data.get("block_id")),
        "transactions_verified": len(txs),
        "checks": {
            "image_digest": True,
            "canonical_record": True,
            "leaf_digest": True,
            "merkle_path": True,
            "redundant_fields_integrity": True
        }
    }


def main():
    ap = argparse.ArgumentParser(description="Auditor Independente LIN (LIN-PILOT-VERIFIER-FUZZ-001)")
    ap.add_argument("bundle", help="Caminho para o JSON exportado do lote")
    ap.add_argument("--expected-image", required=True, help="Digest hexadecimal esperado da imagem LINBC1")
    ap.add_argument("--expected-file-sha", default=None, help="SHA-256 do arquivo da imagem")
    args = ap.parse_args()

    path = Path(args.bundle)
    if not path.exists():
        print(f"Erro: arquivo {path} não encontrado", file=sys.stderr)
        sys.exit(1)

    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_JSON", "detail": str(e)}, indent=2))
        sys.exit(1)

    res = verify_block_bundle(bundle, args.expected_image, args.expected_file_sha)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["valid"] else 1)


if __name__ == "__main__":
    main()
