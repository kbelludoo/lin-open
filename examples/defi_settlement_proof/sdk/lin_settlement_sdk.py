#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN Settlement SDK (Protótipo de Engenharia)
Escopo técnico delimitado:
  - Carrega a imagem congelada LINBC1 e executa swaps via lin_bc1_run
  - Serializa registros canônicos de 72 bytes associando a imagem ao output
  - Constrói a árvore Merkle SHA-256 (256 bits) para blocos de 4 swaps
  - Exporta lote completo (raiz, folhas e caminhos de prova) para arquivo JSON
  - Fornece validador independente desacoplado do ambiente de execução

Ressalva Epistêmica (R5):
  - A raiz Merkle comprova integridade e compromisso pós-execução do lote.
  - Não confere privacidade nem substitui provas de conhecimento zero (ZK).
  - A garantia de integridade depende da cadeia de custódia e publicação das folhas.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LINSettlementSDK:
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self.root = Path(repo_root)

        self.lin_bc1_run = self.root / "transpile" / "c" / "bin" / "lin_bc1_run"
        self.image_path = self.root / "examples" / "defi_settlement_proof" / "settlement_engine.linbc"

        if not self.lin_bc1_run.exists():
            raise FileNotFoundError(f"Binário {self.lin_bc1_run} não encontrado. Execute 'make c0'.")
        if not self.image_path.exists():
            raise FileNotFoundError(f"Imagem {self.image_path} não encontrada. Execute lin_c0 image.")

        self.file_sha256 = hashlib.sha256(self.image_path.read_bytes()).hexdigest()
        self.img_digest_32b = self._fetch_image_digest()

    def _fetch_image_digest(self) -> bytes:
        # Executa uma chamada sonda para capturar o digest do loader linbc1:img:
        cmd = [str(self.lin_bc1_run), str(self.image_path), "settle_swap", "1000", "100000", "200000", "1970"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Falha ao sondar imagem LinVM: {p.stderr}")
        for token in p.stdout.split():
            if token.startswith("img_sha256="):
                return bytes.fromhex(token.split("=")[1].strip('"'))
        raise RuntimeError("Não foi possível obter img_sha256 da saída do lin_bc1_run")

    def execute_swap(self, tx_id: int, amount_in: int, reserve_in: int, reserve_out: int, min_out: int) -> Dict[str, Any]:
        cmd = [
            str(self.lin_bc1_run), str(self.image_path), "settle_swap",
            str(amount_in), str(reserve_in), str(reserve_out), str(min_out)
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Erro de execução LinVM: {p.stderr}")

        val, steps, executed_digest = None, None, None
        for token in p.stdout.split():
            if token.startswith("result="):
                val = int(token.split("=")[1])
            elif token.startswith("steps="):
                steps = int(token.split("=")[1])
            elif token.startswith("img_sha256="):
                executed_digest = token.split("=")[1].strip('"')

        if val is None or steps is None or executed_digest is None:
            raise RuntimeError("Saída malformada do executor LINBC1")

        status = 1 if val >= 0 else -1
        record_bytes = self.pack_leaf_record(tx_id, amount_in, val, steps, status)
        leaf_hash = hashlib.sha256(record_bytes).digest()

        return {
            "tx_id": tx_id,
            "amount_in": amount_in,
            "reserve_in": reserve_in,
            "reserve_out": reserve_out,
            "min_out": min_out,
            "out_val": val,
            "steps": steps,
            "status": "APPROVED" if status == 1 else "REJECTED_SLIPPAGE",
            "status_code": status,
            "raw_record_hex": record_bytes.hex(),
            "leaf_hash_hex": leaf_hash.hex()
        }

    def pack_leaf_record(self, tx_id: int, amount_in: int, out_val: int, steps: int, status: int) -> bytes:
        raw = bytearray(72)
        raw[0:32] = self.img_digest_32b
        struct.pack_into("<Q", raw, 32, tx_id)
        struct.pack_into("<Q", raw, 40, amount_in)
        struct.pack_into("<q", raw, 48, out_val)
        struct.pack_into("<Q", raw, 56, steps)
        struct.pack_into("<q", raw, 64, status)
        return bytes(raw)

    def build_block_bundle(self, block_id: int, swaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(swaps) != 4:
            raise ValueError("O lote deve conter exatamente 4 transações para a árvore Merkle binária")

        leaf_bytes = [bytes.fromhex(sw["leaf_hash_hex"]) for sw in swaps]

        def h_parent(left: bytes, right: bytes) -> bytes:
            return hashlib.sha256(left + right).digest()

        n0 = h_parent(leaf_bytes[0], leaf_bytes[1])
        n1 = h_parent(leaf_bytes[2], leaf_bytes[3])
        root = h_parent(n0, n1)

        proofs = [
            {"sibling0_hex": leaf_bytes[1].hex(), "sibling1_hex": n1.hex(), "path_bits": 0b00},
            {"sibling0_hex": leaf_bytes[0].hex(), "sibling1_hex": n1.hex(), "path_bits": 0b01},
            {"sibling0_hex": leaf_bytes[3].hex(), "sibling1_hex": n0.hex(), "path_bits": 0b10},
            {"sibling0_hex": leaf_bytes[2].hex(), "sibling1_hex": n0.hex(), "path_bits": 0b11},
        ]

        tx_entries = []
        for i, sw in enumerate(swaps):
            entry = dict(sw)
            entry["merkle_proof"] = proofs[i]
            tx_entries.append(entry)

        return {
            "block_id": block_id,
            "image_file_sha256": self.file_sha256,
            "image_loader_digest": self.img_digest_32b.hex(),
            "merkle_root_sha256": root.hex(),
            "transactions": tx_entries
        }

    @staticmethod
    def verify_transaction_proof(tx_entry: Dict[str, Any], expected_root_hex: str) -> bool:
        proof = tx_entry["merkle_proof"]
        leaf = bytes.fromhex(tx_entry["leaf_hash_hex"])
        s0 = bytes.fromhex(proof["sibling0_hex"])
        s1 = bytes.fromhex(proof["sibling1_hex"])
        path_bits = proof["path_bits"]

        # Recalcula a folha a partir do registro binário bruto para garantir integridade
        recalculated_leaf = hashlib.sha256(bytes.fromhex(tx_entry["raw_record_hex"])).digest()
        if recalculated_leaf != leaf:
            return False

        def h_parent(l: bytes, r: bytes) -> bytes:
            return hashlib.sha256(l + r).digest()

        curr = h_parent(leaf, s0) if (path_bits & 1) == 0 else h_parent(s0, leaf)
        curr = h_parent(curr, s1) if ((path_bits >> 1) & 1) == 0 else h_parent(s1, curr)

        return curr.hex() == expected_root_hex


if __name__ == "__main__":
    print("Testando LIN Settlement SDK...")
    sdk = LINSettlementSDK()
    txs = [
        sdk.execute_swap(1001, 1000, 100000, 200000, 1970),
        sdk.execute_swap(1002, 2500, 100000, 200000, 4800),
        sdk.execute_swap(1003, 5000, 100000, 200000, 9900), # Rejeição
        sdk.execute_swap(1004, 1200, 150000, 300000, 2300)
    ]
    bundle = sdk.build_block_bundle(1, txs)
    print("Bloco construído com sucesso! Raiz Merkle:", bundle["merkle_root_sha256"])

    # Teste de verificação independente da Tx 1001
    ok = sdk.verify_transaction_proof(bundle["transactions"][0], bundle["merkle_root_sha256"])
    print("Validação independente de prova:", "OK" if ok else "FALHA")
