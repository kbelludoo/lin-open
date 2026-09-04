#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIN Settlement SDK (Normativo: LIN-PILOT-VERIFIER-FUZZ-001)
Registro Canônico de 112 bytes com Prefixos de Domínio:
  - Folha: SHA256("LIN:LEAF:1" || registro_112_bytes)
  - Nó:    SHA256("LIN:NODE:1" || left_32_bytes || right_32_bytes)
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


DOM_LEAF = b"LIN:LEAF:1"
DOM_NODE = b"LIN:NODE:1"
SCHEMA_ID = b"LCR1"
SCHEMA_VERSION = 1
PROFILE_LINVM1 = 1


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
        cmd = [str(self.lin_bc1_run), str(self.image_path), "settle_swap", "1000", "100000", "200000", "1970"]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Falha ao sondar imagem LinVM: {p.stderr}")
        for token in p.stdout.split():
            if token.startswith("img_sha256="):
                return bytes.fromhex(token.split("=")[1].strip('"'))
        raise RuntimeError("Não foi possível obter img_sha256 da saída do lin_bc1_run")

    def execute_swap(self, run_id: int, tx_id: int, amount_in: int, reserve_in: int, reserve_out: int, min_out: int) -> Dict[str, Any]:
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
        record_bytes = self.pack_leaf_record_112(run_id, tx_id, amount_in, reserve_in, reserve_out, min_out, val, steps, status)
        leaf_hash = hashlib.sha256(DOM_LEAF + record_bytes).digest()

        return {
            "run_id": run_id,
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

    def pack_leaf_record_112(self, run_id: int, tx_id: int, amount_in: int, reserve_in: int, reserve_out: int, min_out: int, out_val: int, steps: int, status: int) -> bytes:
        raw = bytearray(112)
        raw[0:4] = SCHEMA_ID                       # offset 0..3: ASCII LCR1
        raw[4] = SCHEMA_VERSION                    # offset 4: u8 = 1
        raw[5] = PROFILE_LINVM1                    # offset 5: u8 = 1
        raw[6:8] = b"\x00\x00"                     # offset 6..7: reserved u16 = 0
        raw[8:40] = self.img_digest_32b            # offset 8..39: image_digest (32 bytes)
        struct.pack_into("<Q", raw, 40, run_id)    # offset 40..47: u64 LE
        struct.pack_into("<Q", raw, 48, tx_id)     # offset 48..55: u64 LE
        struct.pack_into("<q", raw, 56, amount_in) # offset 56..63: i64 LE
        struct.pack_into("<q", raw, 64, reserve_in)# offset 64..71: i64 LE
        struct.pack_into("<q", raw, 72, reserve_out)# offset 72..79: i64 LE
        struct.pack_into("<q", raw, 80, min_out)   # offset 80..87: i64 LE
        struct.pack_into("<q", raw, 88, out_val)   # offset 88..95: i64 LE
        struct.pack_into("<Q", raw, 96, steps)     # offset 96..103: u64 LE
        struct.pack_into("<q", raw, 104, status)   # offset 104..111: i64 LE
        return bytes(raw)

    def build_block_bundle(self, block_id: int, swaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(swaps) != 4:
            raise ValueError("O lote deve conter exatamente 4 transações para a árvore Merkle binária")

        leaf_bytes = [bytes.fromhex(sw["leaf_hash_hex"]) for sw in swaps]

        def h_parent(left: bytes, right: bytes) -> bytes:
            return hashlib.sha256(DOM_NODE + left + right).digest()

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
            "schema": "LIN_SETTLEMENT_BUNDLE_1.0",
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

        # Recalcula a folha com o prefixo de domínio LIN:LEAF:1
        recalculated_leaf = hashlib.sha256(DOM_LEAF + bytes.fromhex(tx_entry["raw_record_hex"])).digest()
        if recalculated_leaf != leaf:
            return False

        def h_parent(l: bytes, r: bytes) -> bytes:
            return hashlib.sha256(DOM_NODE + l + r).digest()

        curr = h_parent(leaf, s0) if (path_bits & 1) == 0 else h_parent(s0, leaf)
        curr = h_parent(curr, s1) if ((path_bits >> 1) & 1) == 0 else h_parent(s1, curr)

        return curr.hex() == expected_root_hex
