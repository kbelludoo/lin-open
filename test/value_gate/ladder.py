#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 pin, L3 frontend REJ_*, and overclaim cuts for the value gate."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
C0 = ROOT / "transpile" / "c" / "bin" / "lin_c0"
SOL_LIN = ROOT / "src" / "lin_from_solidity.lin"
UNI_PIN = ROOT / "test" / "fixtures" / "external_proof" / "UniswapV2Library.sol"
PIN_SHA = "4f83e9334f833568fa47b36e9ceca435f6c2962760a0596b043c4e538d0fd9f2"
C4_ROOT = "a6d17453df142262535f2ea3e4a554c6de75bfae256f39124f6f01ff769afd57"

REJ_CODES = (
    "REJ_SOLIDITY_PAYABLE",
    "REJ_SOLIDITY_STATE",
    "REJ_SOLIDITY_ENV",
    "REJ_SOLIDITY_INLINE_ASM",
    "REJ_SOLIDITY_STORAGE",
    "REJ_SOLIDITY_EVENT",
    "REJ_SOLIDITY_NON_PURE",
)


def sol_reason(sig: str, body: str) -> str:
    """Cleanroom mirror of src/lin_from_solidity.lin::sol_reason."""
    if "payable" in sig:
        return "REJ_SOLIDITY_PAYABLE"
    if "msg.value" in body or "msg.sender" in body:
        return "REJ_SOLIDITY_STATE"
    if "block.timestamp" in body:
        return "REJ_SOLIDITY_ENV"
    if "assembly" in body:
        return "REJ_SOLIDITY_INLINE_ASM"
    if "mapping" in body or "storage" in sig:
        return "REJ_SOLIDITY_STORAGE"
    if "emit " in body:
        return "REJ_SOLIDITY_EVENT"
    if "pure" in sig:
        return "OK"
    if "view" in sig:
        return "OK_VIEW"
    return "REJ_SOLIDITY_NON_PURE"


def l1_pin() -> tuple[str, str]:
    if not UNI_PIN.exists():
        return "FAIL", f"missing pin {UNI_PIN} — L1 cannot exist without V3"
    digest = hashlib.sha256(UNI_PIN.read_bytes()).hexdigest()
    if digest != PIN_SHA:
        return "FAIL", f"pin mismatch: got {digest}, want {PIN_SHA}"
    return "PASS", (
        f"V3 pin UniswapV2Library.sol sha256:{digest[:8]}... "
        "Local pin only. Live GitHub --fetch is make rationalist-proof FETCH=1; "
        "this gate does not substitute L1-live."
    )


def l3_frontend(run) -> tuple[str, str]:
    src = SOL_LIN.read_text(encoding="utf-8")
    missing = [c for c in REJ_CODES if c not in src]
    if missing:
        return "FAIL", f"sol_reason table missing {missing}"
    cases = [
        ("function mint() external payable returns (bool)",
         "require(msg.value > 0); return true;", "REJ_SOLIDITY_PAYABLE"),
        ("function getAmountOut(uint a, uint b, uint c) internal pure returns (uint)",
         "return a;", "OK"),
        ("function rate() internal view returns (uint)",
         "return cash;", "OK_VIEW"),
        ("function poke() public returns (uint)",
         "emit Foo(); return 1;", "REJ_SOLIDITY_EVENT"),
    ]
    for sig, body, want in cases:
        got = sol_reason(sig, body)
        if got != want:
            return "FAIL", f"sol_reason({sig!r}) got {got} want {want}"
    rc, out = run([str(C0), "info", str(SOL_LIN)])
    if rc != 0:
        return "FAIL", f"lin_c0 info failed: {out}"
    m = re.search(r"\.coverage\{ total=(\d+) eligible=(\d+) rejected=(\d+) \}", out)
    if not m:
        return "FAIL", f"cannot parse coverage:\n{out}"
    total, eligible, rejected = (int(x) for x in m.groups())
    if eligible != 0 or rejected != total or total < 1:
        return "FAIL", (
            f"default vm must refuse sol_from_sol (eligible=0), "
            f"got total={total} eligible={eligible} rejected={rejected}"
        )
    if "VM_REJ_STRING_LITERAL" not in out and "VM_REJ_RETURN_NOT_INT" not in out:
        return "FAIL", "expected VM_REJ_* on Solidity frontend"
    if "sol_from_sol" not in out:
        return "FAIL", "sol_from_sol missing from info"
    return "PASS", (
        f"sol_from_sol fail-closed: C0 eligible=0 ({rejected}/{total} VM_REJ_*); "
        "REJ_SOLIDITY_* table intact. Rejecting high is the coprocessor receipt. "
        "A general Solidity transpiler remains NOT-PROVEN."
    )


def cut_overclaims() -> tuple[str, str]:
    """Fail if reviewer-facing files still sell the four poison claims."""
    hits = []
    rsa = (ROOT / "docs" / "events" / "EVENT_RSA_CRYPTANALYSIS_001.rulel").read_text(encoding="utf-8")
    if "Quebra Histórica" in rsa or "CERTIFIED_CRYPTOGRAPHIC_BREAK" in rsa:
        hits.append("RSA event still sold as historical break")
    if "TOY" not in rsa:
        hits.append("RSA event missing TOY label")
    bounties = (ROOT / "src" / "lin_high_value_bounties.lin").read_text(encoding="utf-8")
    if "High-Value Bounty Target" in bounties or "Zero-Trust High-Value" in bounties:
        hits.append("LayerZero/bounties module still sold as bounty")
    if "TOY" not in bounties:
        hits.append("bounties module missing TOY label")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    gpu_pass = None
    for line in readme.splitlines():
        if "GPU AMM Co-processor" in line and "PASS" in line:
            gpu_pass = line
            break
    if gpu_pass and ("1.17M" in gpu_pass or "1,17M" in gpu_pass):
        hits.append("README PASS row still quotes 1.17M (kernel peak sold as capability)")
    if "$1.8T" in readme and "FALSE AS STATED" not in readme:
        hits.append("README still sells volume as savings")
    sob = (ROOT / "docs" / "UNISWAP_V2_SOBERANO_LIN_SUPERIORIDADE.md").read_text(encoding="utf-8")
    if "39.000×" in sob or "39000×" in sob:
        hits.append("SOBERANO doc still compares kernel 1.17M to L1 TPS")
    if hits:
        return "FAIL", "; ".join(hits)
    return "PASS", (
        "Cut: RSA~2^36 not historical; LayerZero module is TOY; "
        "1.17M absent from README PASS (peak kernel only); $1.8T stays FALSE AS STATED"
    )
