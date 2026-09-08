#!/usr/bin/env python3
"""
gen_test.py — Generates test/forge-gas/test/Gas.t.sol from real Ethereum mainnet dataset.
Binds real Merkle root for EVM swap records and LCR2 canonical binary receipt root.
"""
import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = REPO_ROOT / "test" / "pilot_harness" / "mainnet_real_swaps_2000.json"
OUT_TEST = Path(__file__).resolve().parent / "test" / "Gas.t.sol"

def leaf(rin, rout, ain, aout):
    return hashlib.sha256(
        rin.to_bytes(32, 'big') +
        rout.to_bytes(32, 'big') +
        ain.to_bytes(32, 'big') +
        aout.to_bytes(32, 'big')
    ).digest()

def root_of(ls):
    cur = list(ls)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            l = cur[i]
            r = cur[i+1] if i+1 < len(cur) else cur[i]
            nxt.append(hashlib.sha256(l + r).digest())
        cur = nxt
    return cur[0]

def proof(ls, index):
    pf = []
    idx = index
    cur = list(ls)
    while len(cur) > 1:
        if len(cur) % 2 == 1:
            cur = cur + [cur[-1]]
        pf.append(cur[idx ^ 1])
        nxt = []
        for i in range(0, len(cur), 2):
            nxt.append(hashlib.sha256(cur[i] + cur[i+1]).digest())
        cur = nxt
        idx //= 2
    return pf

def main():
    if not DATASET_PATH.exists():
        print(f"[-] Dataset not found: {DATASET_PATH}")
        sys.exit(1)

    swaps = json.load(open(DATASET_PATH))
    leaves = [leaf(s["reserve_in"], s["reserve_out"], s["amount_in"], s["expected_out_real"]) for s in swaps]
    root = root_of(leaves)

    s0 = swaps[0]
    p0 = proof(leaves, 0)

    # Ensure LCR2 receipt exists
    manifest_path = Path("/tmp/batch_receipt_2000.json")
    bin_path = Path("/tmp/batch_records_2000.bin")
    if not (manifest_path.exists() and bin_path.exists()):
        cmd = [
            sys.executable,
            str(REPO_ROOT / "tools" / "emit_batch_receipt.py"),
            "--dataset", str(DATASET_PATH),
            "--out-manifest", str(manifest_path),
            "--out-bin", str(bin_path)
        ]
        subprocess.run(cmd, check=True)

    man = json.load(open(manifest_path))
    rec = open(bin_path, "rb").read()
    RL = man["record_bytes"]
    N = man["count"]
    r0 = rec[0:RL]
    lleaves = [hashlib.sha256(b"LIN:LEAF:1" + rec[i*RL:(i+1)*RL]).digest() for i in range(N)]

    def lproof(ls, index):
        pf = []
        idx = index
        cur = list(ls)
        while len(cur) > 1:
            if len(cur) % 2 == 1:
                cur = cur + [cur[-1]]
            pf.append(cur[idx ^ 1])
            nxt = []
            for i in range(0, len(cur), 2):
                nxt.append(hashlib.sha256(b"LIN:NODE:1" + cur[i] + cur[i+1]).digest())
            cur = nxt
            idx //= 2
        return pf

    lp0 = lproof(lleaves, 0)

    b32 = lambda b: "bytes32(0x" + b.hex() + ")"
    arr = lambda ps: "[" + ", ".join(b32(p) for p in ps) + "]"

    sol = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "contracts/LinReceiptVerifier.sol";

contract GasTest {
    bytes32 constant EVM_ROOT = bytes32(0xROOTHEX);
    bytes32 constant LCR2_ROOT = bytes32(0xLCR2HEX);
    event Log(string name, uint256 gasUsed);

    function _v() internal returns (LinReceiptVerifier) {
        return new LinReceiptVerifier();
    }

    function testDeploy() public {
        uint256 g0 = gasleft();
        LinReceiptVerifier v = _v();
        emit Log("deploy", g0 - gasleft());
        assert(address(v) != address(0));
    }

    function testVerifyConstantProduct() public {
        LinReceiptVerifier v = _v();
        uint256 g0 = gasleft();
        bool ok = v.verifyConstantProduct(RIN, ROUT, AIN, AOUT);
        emit Log("verifyConstantProduct", g0 - gasleft());
        assert(ok);
    }

    function testVerifySwapInclusion() public {
        LinReceiptVerifier v = _v();
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = PROOFARR;
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        bytes32 lf = v.computeSwapLeaf(RIN, ROUT, AIN, AOUT);
        uint256 g0 = gasleft();
        bool ok = v.verifySwapInclusion(lf, pf, 0, EVM_ROOT);
        emit Log("verifySwapInclusion", g0 - gasleft());
        assert(ok);
    }

    function testSettleBatch() public {
        LinReceiptVerifier v = _v();
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 1,
            swapCount: 2000,
            merkleRoot: EVM_ROOT,
            kernelSourceHash: bytes32(0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        uint256 g0 = gasleft();
        assert(v.settleBatch(h));
        emit Log("settleBatch", g0 - gasleft());
    }

    function testSettleBatchWithProof() public {
        LinReceiptVerifier v = _v();
        LinReceiptVerifier.BatchHeader memory h = LinReceiptVerifier.BatchHeader({
            batchId: 2,
            swapCount: 2000,
            merkleRoot: EVM_ROOT,
            kernelSourceHash: bytes32(0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa),
            timestamp: 1725700000,
            sequencer: address(this)
        });
        LinReceiptVerifier.SwapRecord memory spot = LinReceiptVerifier.SwapRecord({
            reserveIn: RIN,
            reserveOut: ROUT,
            amountIn: AIN,
            amountOut: AOUT
        });
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = PROOFARR;
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        uint256 g0 = gasleft();
        assert(v.settleBatchWithInclusionProof(h, spot, pf, 0));
        emit Log("settleBatchWithProof", g0 - gasleft());
    }

    function testVerifyLCR2Inclusion() public {
        LinReceiptVerifier v = _v();
        bytes memory record = hex"R0HEX";
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = LPROOFARR;
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        uint256 g0 = gasleft();
        bool ok = v.verifyLCR2Inclusion(record, pf, 0, LCR2_ROOT);
        emit Log("verifyLCR2Inclusion", g0 - gasleft());
        assert(ok);
    }

    function testTamperedProofFails() public {
        LinReceiptVerifier v = _v();
        bytes32[] memory pf = new bytes32[](11);
        bytes32[11] memory hard = PROOFARR;
        for (uint i = 0; i < 11; i++) pf[i] = hard[i];
        pf[0] = bytes32(0x0000000000000000000000000000000000000000000000000000000000000001);
        bytes32 lf = v.computeSwapLeaf(RIN, ROUT, AIN, AOUT);
        assert(!v.verifySwapInclusion(lf, pf, 0, EVM_ROOT));
    }
}
"""
    sol = sol.replace("ROOTHEX", root.hex()).replace("LCR2HEX", man["merkle_root"])
    sol = sol.replace("RIN", str(s0["reserve_in"])).replace("ROUT", str(s0["reserve_out"]))
    sol = sol.replace("AIN", str(s0["amount_in"])).replace("AOUT", str(s0["expected_out_real"]))
    sol = sol.replace("LPROOFARR", arr(lp0)).replace("PROOFARR", arr(p0)).replace("R0HEX", r0.hex())
    OUT_TEST.write_text(sol)
    print(f"[+] Successfully generated {OUT_TEST}")

if __name__ == "__main__":
    main()
