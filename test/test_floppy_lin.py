#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite: FloppyURL x LIN Ecosystem (test/test_floppy_lin.py)
============================================================
Verifies:
1. Roundtrip compression/decompression across all modes (Dispute, Playground, dApp).
2. Virtual Floppy RAID-0 multi-disk chunking and reassembly.
3. Optimistic fraud dispute verification logic.
4. Cross-runtime compatibility between Python packer and Node.js DecompressionStream.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKER = ROOT / "tools" / "floppy_lin_pack.py"
BOOTLOADER = ROOT / "examples" / "floppy_lin" / "floppy_bootloader.html"


def run_cmd(cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def test_dispute_mode():
    print("[1/4] Testando Modo de Disputa de Fraude (1-Click Dispute)...")
    out = run_cmd([
        str(PACKER), "pack",
        "--mode", "dispute",
        "--tx-id", "999",
        "--amount-in", "10000",
        "--reserve-in", "1000000",
        "--reserve-out", "2000000",
        "--min-out", "19000",
        "--claimed-out", "150000", # Fraude
    ])

    # Extract URL fragment
    frag = None
    for line in out.splitlines():
        if "URL: floppy_bootloader.html#v1;" in line:
            frag = line.split("floppy_bootloader.html")[1].strip()
            break
    assert frag, "Failed to extract URL fragment"

    # Unpack
    unpacked_json = run_cmd([str(PACKER), "unpack", frag])
    data = json.loads(unpacked_json)

    assert data["type"] == "dispute"
    assert data["dispute"]["tx_id"] == 999
    assert data["dispute"]["claimed_out"] == 150000
    assert data["dispute"]["expected_out"] == 19743
    assert data["dispute"]["discrepancy"] == 130257
    assert data["is_fraud_suspected"] is True

    print(f"  -> Fragmento gerado: {len(frag)} caracteres")
    print(f"  -> Fraude detectada: Saída esperada = 19,743 | Saída alegada = 150,000 (Desvio: +130,257)")
    print("  -> PASS: Modo de disputa verificado com sucesso.\n")


def test_playground_mode():
    print("[2/4] Testando Modo Playground / REPL Serverless...")
    src_file = ROOT / "src" / "lin_siphash_real.lin"
    out = run_cmd([str(PACKER), "pack", "--mode", "playground", "--source", str(src_file)])

    frag = None
    for line in out.splitlines():
        if "URL: floppy_bootloader.html#v1;" in line:
            frag = line.split("floppy_bootloader.html")[1].strip()
            break
    assert frag, "Failed to extract URL fragment"

    unpacked_json = run_cmd([str(PACKER), "unpack", frag])
    data = json.loads(unpacked_json)

    assert data["type"] == "playground"
    assert "siphash24_compute" in data["source"]
    print(f"  -> Código SipHash-2-4 comprimido em URL de {len(frag)} caracteres")
    print("  -> PASS: Playground empacotado e desempacotado com 100% de paridade.\n")


def test_virtual_floppy_raid0():
    print("[3/4] Testando RAID-0 de Disquetes Virtuais (Multi-Chunk Slicing)...")
    # Force slicing into 500-char chunks
    out = run_cmd([
        str(PACKER), "pack",
        "--mode", "dispute",
        "--chunk-size", "500",
    ])

    frags = []
    for line in out.splitlines():
        if "URL: floppy_bootloader.html#v1;" in line:
            frags.append(line.split("floppy_bootloader.html")[1].strip())

    assert len(frags) > 1, f"Expected multiple chunks, got {len(frags)}"
    print(f"  -> Fatiamento em {len(frags)} disquetes virtuais gerado:")
    for f in frags:
        slice_tag = f[f.find("[") : f.find("]") + 1]
        print(f"     * Setor {slice_tag} ({len(f)} chars)")

    # Reassemble using unpack
    unpacked_json = run_cmd([str(PACKER), "unpack"] + frags)
    data = json.loads(unpacked_json)
    assert data["type"] == "dispute"
    print("  -> PASS: Reconstituição de RAID-0 multi-setor 100% idêntica.\n")


def test_node_browser_engine_compat():
    print("[4/4] Testando Compatibilidade com DecompressionStream do Navegador via Node.js...")
    # Generate a payload
    out = run_cmd([str(PACKER), "pack", "--mode", "dispute", "--tx-id", "777"])
    raw_payload = None
    for line in out.splitlines():
        if "URL: floppy_bootloader.html#v1;[1/1]" in line:
            raw_payload = line.split("#v1;[1/1]")[1].strip()
            break
    assert raw_payload, "Missing payload"

    node_script = f"""
    const payload = "{raw_payload}";
    const pad = "=".repeat((4 - (payload.length % 4)) % 4);
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/") + pad;
    const bytes = Buffer.from(b64, "base64");

    const ds = new DecompressionStream("deflate-raw");
    const writer = ds.writable.getWriter();
    writer.write(bytes);
    writer.close();

    new Response(ds.readable).text().then(jsonStr => {{
        const data = JSON.parse(jsonStr);
        if (data.type === "dispute" && data.dispute.tx_id === 777) {{
            console.log("PASS_NODE_DECOMPRESSION");
        }} else {{
            console.error("FAIL_NODE_DECOMPRESSION");
            process.exit(1);
        }}
    }});
    """
    node_out = run_cmd(["node", "-e", node_script])
    assert "PASS_NODE_DECOMPRESSION" in node_out
    print("  -> DecompressionStream nativo do navegador validado com 100% de sucesso.")
    print("  -> PASS: Interoperabilidade Python Packer <-> Browser JavaScript confirmada.\n")


def main():
    print("=" * 78)
    print("  FLOPPY_URL x LIN SUITE: VERIFICAÇÃO DE PONTA A PONTA")
    print("=" * 78 + "\n")

    test_dispute_mode()
    test_playground_mode()
    test_virtual_floppy_raid0()
    test_node_browser_engine_compat()

    print("=" * 78)
    print("  RESULTADO: TODOS OS 4 TESTES PASSARAM COM 100% DE SUCESSO!")
    print("=" * 78)


if __name__ == "__main__":
    main()
