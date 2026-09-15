#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FloppyURL x LIN Packer (tools/floppy_lin_pack.py)
================================================
Encodes LIN source code, LINBC1 bytecode, and cryptographic dispute records
into zero-byte, self-booting URL hash fragments (#v1;[1/N]<payload>) using
raw DEFLATE compression and RFC 4648 §5 Base64URL encoding.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compress_deflate_raw(data: bytes) -> bytes:
    """Compress with raw DEFLATE (wbits=-15, no zlib header/checksum) for browser DecompressionStream."""
    c = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    return c.compress(data) + c.flush()


def decompress_deflate_raw(compressed: bytes) -> bytes:
    """Decompress raw DEFLATE bytes."""
    return zlib.decompress(compressed, -15)


def b64url_encode(data: bytes) -> str:
    """Base64URL encoding without padding (RFC 4648 §5)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(s: str) -> bytes:
    """Base64URL decoding with padding restored."""
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def pack_payload(payload_obj: dict, chunk_size: int = 0) -> list[str]:
    """Serializes, compresses, and returns a list of #v1;[i/N]<payload> fragments."""
    json_bytes = json.dumps(payload_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    compressed = compress_deflate_raw(json_bytes)
    b64 = b64url_encode(compressed)

    if chunk_size <= 0 or len(b64) <= chunk_size:
        # Single virtual floppy
        return [f"#v1;[1/1]{b64}"]

    # Multi-disk RAID-0 virtual floppy slicing
    chunks = []
    total_len = len(b64)
    n_chunks = (total_len + chunk_size - 1) // chunk_size
    for i in range(n_chunks):
        part = b64[i * chunk_size : (i + 1) * chunk_size]
        chunks.append(f"#v1;[{i + 1}/{n_chunks}]{part}")
    return chunks


def unpack_payload(fragments: list[str]) -> dict:
    """Reassembles, decodes, and decompresses virtual floppy fragments."""
    # Parse fragment headers
    parts_map: dict[int, tuple[int, str]] = {}
    for frag in fragments:
        frag = frag.strip()
        if frag.startswith("#"):
            frag = frag[1:]
        if not frag.startswith("v1;["):
            raise ValueError(f"Invalid fragment header: {frag[:20]}")
        
        idx_end = frag.find("]")
        if idx_end == -1:
            raise ValueError("Malformed fragment slice notation")
        
        slice_info = frag[4:idx_end]
        curr_str, total_str = slice_info.split("/")
        curr_idx = int(curr_str)
        total_idx = int(total_str)
        chunk_data = frag[idx_end + 1 :]
        parts_map[curr_idx] = (total_idx, chunk_data)

    if not parts_map:
        raise ValueError("No valid fragments provided")

    first_total = next(iter(parts_map.values()))[0]
    if len(parts_map) != first_total:
        raise ValueError(f"Missing fragments: received {len(parts_map)} of {first_total}")

    # Assemble in order
    full_b64 = "".join(parts_map[i][1] for i in range(1, first_total + 1))
    compressed = b64url_decode(full_b64)
    raw_json = decompress_deflate_raw(compressed).decode("utf-8")
    return json.loads(raw_json)


def build_dispute_payload(
    tx_id: int,
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    min_out: int,
    claimed_out: int,
    claimed_status: int,
    bytecode_file: Path | None = None,
    source_file: Path | None = None,
) -> dict:
    """Constructs a self-contained optimistic fraud dispute payload."""
    bytecode_b64 = ""
    source_text = ""
    img_sha256 = ""

    if bytecode_file and bytecode_file.exists():
        bc_bytes = bytecode_file.read_bytes()
        bytecode_b64 = base64.b64encode(bc_bytes).decode("ascii")
        img_sha256 = hashlib.sha256(bc_bytes).hexdigest()

    if source_file and source_file.exists():
        source_text = source_file.read_text(encoding="utf-8")

    # Canonical Uniswap V2 math oracle for expected result
    in_fee = amount_in * 997
    num = in_fee * reserve_out
    den = (reserve_in * 1000) + in_fee
    expected_out = (num // den) if den > 0 else 0
    expected_status = 1 if expected_out >= min_out else -1

    is_fraud = (claimed_out != expected_out) or (claimed_status != expected_status)

    return {
        "type": "dispute",
        "version": "1.0",
        "title": f"LinSwap AMM Settlement Dispute (Tx #{tx_id})",
        "timestamp": 1726410000,
        "is_fraud_suspected": is_fraud,
        "dispute": {
            "tx_id": tx_id,
            "inputs": [amount_in, reserve_in, reserve_out, min_out],
            "claimed_out": claimed_out,
            "claimed_status": claimed_status,
            "expected_out": expected_out,
            "expected_status": expected_status,
            "discrepancy": claimed_out - expected_out,
            "img_sha256": img_sha256,
        },
        "bytecode_b64": bytecode_b64,
        "source": source_text,
    }


def build_playground_payload(source_file: Path) -> dict:
    """Constructs a shareable LIN Playground / REPL payload."""
    source_text = source_file.read_text(encoding="utf-8")
    return {
        "type": "playground",
        "version": "1.0",
        "title": f"LIN Playground: {source_file.name}",
        "source": source_text,
        "inputs": [21],
    }


def main():
    parser = argparse.ArgumentParser(description="FloppyURL x LIN Zero-Byte Packer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Pack command
    pack_parser = subparsers.add_parser("pack", help="Pack LIN source or dispute into FloppyURL")
    pack_parser.add_argument("--mode", choices=["dispute", "playground", "dapp"], default="playground")
    pack_parser.add_argument("--source", type=Path, help="Path to .lin source file")
    pack_parser.add_argument("--bytecode", type=Path, help="Path to .linbc1 bytecode file")
    pack_parser.add_argument("--base-url", default="floppy_bootloader.html", help="Base HTML file or URL")
    pack_parser.add_argument("--chunk-size", type=int, default=0, help="Max chunk size for virtual floppies")
    
    # Dispute arguments
    pack_parser.add_argument("--tx-id", type=int, default=1042)
    pack_parser.add_argument("--amount-in", type=int, default=10000)
    pack_parser.add_argument("--reserve-in", type=int, default=1000000)
    pack_parser.add_argument("--reserve-out", type=int, default=2000000)
    pack_parser.add_argument("--min-out", type=int, default=19000)
    pack_parser.add_argument("--claimed-out", type=int, default=150000, help="Simulate fraudulent claimed output")
    pack_parser.add_argument("--claimed-status", type=int, default=1)

    # Unpack command
    unpack_parser = subparsers.add_parser("unpack", help="Unpack and verify a FloppyURL fragment")
    unpack_parser.add_argument("fragment", nargs="+", help="URL fragment(s) to decode")

    args = parser.parse_args()

    if args.command == "pack":
        if args.mode == "dispute":
            bc = args.bytecode or (ROOT / "examples/defi_settlement_proof/settlement_engine.linbc")
            src = args.source or (ROOT / "examples/defi_settlement_proof/settlement_engine.lin")
            payload = build_dispute_payload(
                tx_id=args.tx_id,
                amount_in=args.amount_in,
                reserve_in=args.reserve_in,
                reserve_out=args.reserve_out,
                min_out=args.min_out,
                claimed_out=args.claimed_out,
                claimed_status=args.claimed_status,
                bytecode_file=bc,
                source_file=src,
            )
        elif args.mode == "playground":
            src = args.source or (ROOT / "src/lin_siphash_real.lin")
            payload = build_playground_payload(src)
        elif args.mode == "dapp":
            bc = args.bytecode or (ROOT / "examples/defi_settlement_proof/settlement_engine.linbc")
            src = args.source or (ROOT / "examples/defi_settlement_proof/settlement_engine.lin")
            payload = {
                "type": "dapp",
                "version": "1.0",
                "title": "LinSwap Sovereign AMM (Uniswap V2 x*y=k)",
                "source": src.read_text(encoding="utf-8") if src.exists() else "",
                "bytecode_b64": base64.b64encode(bc.read_bytes()).decode("ascii") if bc.exists() else "",
            }

        fragments = pack_payload(payload, chunk_size=args.chunk_size)
        print("=" * 78)
        print("  FLOPPY_URL x LIN PACKER: GENERATED SELF-BOOTING URLS")
        print("=" * 78)
        print(f"  Mode:            {payload['type'].upper()}")
        print(f"  Payload Title:   {payload.get('title')}")
        print(f"  Virtual Disks:   {len(fragments)} disk(s)")
        print(f"  Compression:     Raw DEFLATE (wbits=-15) + Base64URL (RFC 4648 §5)")

        for i, frag in enumerate(fragments):
            full_url = f"{args.base_url}{frag}"
            print(f"\n  [Disk {i+1}/{len(fragments)}] Length: {len(full_url)} chars")
            print(f"  URL: {full_url}")

        print("\n" + "=" * 78)

    elif args.command == "unpack":
        payload = unpack_payload(args.fragment)
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
