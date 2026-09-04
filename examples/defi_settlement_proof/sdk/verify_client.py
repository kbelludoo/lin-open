#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditor / Cliente Independente Zero-Knowledge / Zero-Trust
Requisitos:
  - Python 3 padrão (sem dependência de Zig, C0, LinVM ou compiladores)
  - Valida o lote exportado em JSON pelo LINSettlementSDK
  - Verifica o hash da imagem LINBC1 contra o digest esperado
  - Verifica a consistência de cada folha binária canônica
  - Reconstrói os caminhos Merkle e valida contra a raiz do bloco
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


def verify_block_bundle(bundle_path: Path, expected_image_digest: str) -> bool:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))

    # 1. Conferir o digest da imagem declarada
    actual_img_digest = data.get("image_loader_digest")
    if actual_img_digest != expected_image_digest:
        print(f"[REJEIÇÃO] Digest da imagem executada ({actual_img_digest}) não coincide com o esperado ({expected_image_digest})")
        return False

    merkle_root = data.get("merkle_root_sha256")
    txs = data.get("transactions", [])
    if len(txs) != 4:
        print(f"[REJEIÇÃO] Bloco com número incorreto de transações ({len(txs)})")
        return False

    print(f"[*] Auditando Bloco #{data.get('block_id')} | Raiz: {merkle_root}")
    print(f"[*] Imagem de Bytecode Verificada: {actual_img_digest}")

    def h_parent(l: bytes, r: bytes) -> bytes:
        return hashlib.sha256(l + r).digest()

    for idx, tx in enumerate(txs):
        raw_rec = bytes.fromhex(tx["raw_record_hex"])
        if len(raw_rec) != 72:
            print(f"[REJEIÇÃO] Tamanho inválido do registro da tx #{tx['tx_id']}: {len(raw_rec)} bytes")
            return False

        # Valida que o registro binário tem os mesmos campos e o digest correto da imagem
        img_in_rec = raw_rec[0:32].hex()
        if img_in_rec != actual_img_digest:
            print(f"[REJEIÇÃO] Digest dentro do registro da tx #{tx['tx_id']} adulterado")
            return False

        leaf = hashlib.sha256(raw_rec).digest()
        if leaf.hex() != tx["leaf_hash_hex"]:
            print(f"[REJEIÇÃO] Hash da folha da tx #{tx['tx_id']} inconsistente")
            return False

        # Validação do caminho de prova Merkle
        proof = tx["merkle_proof"]
        s0 = bytes.fromhex(proof["sibling0_hex"])
        s1 = bytes.fromhex(proof["sibling1_hex"])
        path_bits = proof["path_bits"]

        curr = h_parent(leaf, s0) if (path_bits & 1) == 0 else h_parent(s0, leaf)
        curr = h_parent(curr, s1) if ((path_bits >> 1) & 1) == 0 else h_parent(s1, curr)

        if curr.hex() != merkle_root:
            print(f"[REJEIÇÃO] Caminho Merkle da tx #{tx['tx_id']} não reconstrói a raiz do bloco")
            return False

        print(f"  -> Tx #{tx['tx_id']} ({tx['status']}): Prova Merkle VÁLIDA")

    print("[✔] Bloco completamente auditado e íntegro!")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Auditor Independente de Lotes LIN Settlement")
    ap.add_argument("bundle", help="Caminho do arquivo JSON do lote exportado")
    ap.add_argument("--expected-image", required=True, help="Digest hexadecimal esperado da imagem LINBC1")
    args = ap.parse_args()

    ok = verify_block_bundle(Path(args.bundle), args.expected_image)
    sys.exit(0 if ok else 1)
