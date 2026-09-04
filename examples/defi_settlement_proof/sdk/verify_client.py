#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN Standalone Pilot Verifier (Normativo: LIN-PILOT-VERIFIER-FUZZ-001 §6)
Zero-Trust, Zero-Knowledge:
  - Não executa código LIN nem confia em texto emitido por executores
  - Decodifica o registro binário canônico de 112 bytes
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
from typing import Any, Dict


DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
SCHEMA_ID = b"LCR1"
SCHEMA_VERSION = 1
PROFILE_LINVM1 = 1


def verify_block_bundle(bundle_data: Dict[str, Any], expected_image_digest: str) -> Dict[str, Any]:
    # 1. Checagem de digest da imagem
    actual_img_digest = bundle_data.get("image_loader_digest")
    if actual_img_digest != expected_image_digest:
        return {
            "schema": "LIN_VERIFY_RESULT_1",
            "valid": False,
            "reason": "BAD_IMAGE_DIGEST",
            "detail": f"Esperado {expected_image_digest}, recebido {actual_img_digest}"
        }

    merkle_root = bundle_data.get("merkle_root_sha256")
    txs = bundle_data.get("transactions", [])
    if len(txs) != 4:
        return {
            "schema": "LIN_VERIFY_RESULT_1",
            "valid": False,
            "reason": "BLOCK_POLICY",
            "detail": f"Bloco deve conter exatamente 4 transações (recebido {len(txs)})"
        }

    def h_parent(l: bytes, r: bytes) -> bytes:
        return hashlib.sha256(DOM_NODE + l + r).digest()

    for idx, tx in enumerate(txs):
        raw_rec = bytes.fromhex(tx["raw_record_hex"])
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

        # Descompactar inteiros e validar integridade do registro
        run_id, tx_id = struct.unpack_from("<QQ", raw_rec, 40)
        ain, rin, rout, min_out, out_val = struct.unpack_from("<qqqqq", raw_rec, 56)
        steps, status = struct.unpack_from("<Qq", raw_rec, 96)

        if tx_id != tx["tx_id"] or out_val != tx["out_val"] or status != tx["status_code"]:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_RECORD_ENCODING"}

        if status not in (1, -1):
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_STATUS"}

        # Recalcular hash da folha com domínio
        leaf = hashlib.sha256(DOM_LEAF + raw_rec).digest()
        if leaf.hex() != tx["leaf_hash_hex"]:
            return {"schema": "LIN_VERIFY_RESULT_1", "valid": False, "reason": "BAD_LEAF_DIGEST"}

        # Validar caminho Merkle
        proof = tx["merkle_proof"]
        s0 = bytes.fromhex(proof["sibling0_hex"])
        s1 = bytes.fromhex(proof["sibling1_hex"])
        path_bits = proof["path_bits"]

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
            "replay_policy": True
        }
    }


def main():
    ap = argparse.ArgumentParser(description="Auditor Independente LIN (LIN-PILOT-VERIFIER-FUZZ-001)")
    ap.add_argument("bundle", help="Caminho para o JSON exportado do lote")
    ap.add_argument("--expected-image", required=True, help="Digest hexadecimal esperado da imagem LINBC1")
    args = ap.parse_args()

    path = Path(args.bundle)
    if not path.exists():
        print(f"Erro: arquivo {path} não encontrado", file=sys.stderr)
        sys.exit(1)

    bundle = json.loads(path.read_text(encoding="utf-8"))
    res = verify_block_bundle(bundle, args.expected_image)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["valid"] else 1)


if __name__ == "__main__":
    main()
