#!/usr/bin/env python3
"""
LIN-CRYPTO-001: Independent GSM A5/1 External Verifier
Zero internal solver dependencies — purely verifies recovered state against 128-bit vector.
"""

import sys
import json

R1_MASK = 0x07FFFF  # 19 bits
R2_MASK = 0x3FFFFF  # 22 bits
R3_MASK = 0x7FFFFF  # 23 bits

def lfsr_step_r1(r):
    fb = ((r >> 18) ^ (r >> 17) ^ (r >> 16) ^ (r >> 13)) & 1
    return ((r << 1) & R1_MASK) | fb

def lfsr_step_r2(r):
    fb = ((r >> 21) ^ (r >> 20)) & 1
    return ((r << 1) & R2_MASK) | fb

def lfsr_step_r3(r):
    fb = ((r >> 22) ^ (r >> 21) ^ (r >> 20) ^ (r >> 7)) & 1
    return ((r << 1) & R3_MASK) | fb

def clock_majority(b1, b2, b3):
    return (b1 & b2) | (b1 & b3) | (b2 & b3)

def a51_clock(r1, r2, r3):
    b1 = (r1 >> 8) & 1
    b2 = (r2 >> 10) & 1
    b3 = (r3 >> 10) & 1
    maj = clock_majority(b1, b2, b3)

    if b1 == maj:
        r1 = lfsr_step_r1(r1)
    if b2 == maj:
        r2 = lfsr_step_r2(r2)
    if b3 == maj:
        r3 = lfsr_step_r3(r3)

    out_bit = ((r1 >> 18) ^ (r2 >> 21) ^ (r3 >> 22)) & 1
    return r1, r2, r3, out_bit

def verify_a51_candidate(r1, r2, r3, expected_search_u64, expected_val_u64):
    cur_r1, cur_r2, cur_r3 = r1, r2, r3
    
    # 1. Check Search Window (bits 0..63)
    search_matches = 0
    for i in range(64):
        cur_r1, cur_r2, cur_r3, bit = a51_clock(cur_r1, cur_r2, cur_r3)
        expected_bit = (expected_search_u64 >> i) & 1
        if bit == expected_bit:
            search_matches += 1

    # 2. Check Validation Window (bits 64..127)
    val_matches = 0
    for i in range(64):
        cur_r1, cur_r2, cur_r3, bit = a51_clock(cur_r1, cur_r2, cur_r3)
        expected_bit = (expected_val_u64 >> i) & 1
        if bit == expected_bit:
            val_matches += 1

    is_valid = (search_matches == 64 and val_matches == 64)
    return is_valid, search_matches, val_matches

if __name__ == "__main__":
    print("=========================================================================")
    print("   LIN-CRYPTO-001 INDEPENDENT VERIFIER (CLEANROOM EXTERNAL TOOL)        ")
    print("=========================================================================")

    # Test sample
    r1_test = 0x02B4C6
    r2_test = 0x15A9E3
    r3_test = 0x5D8A2F

    # Generate test stream
    r1, r2, r3 = r1_test, r2_test, r3_test
    search_u64 = 0
    for i in range(64):
        r1, r2, r3, bit = a51_clock(r1, r2, r3)
        search_u64 |= (bit << i)
    val_u64 = 0
    for i in range(64):
        r1, r2, r3, bit = a51_clock(r1, r2, r3)
        val_u64 |= (bit << i)

    # 1. Test Exact Candidate
    ok_exact, s_m, v_m = verify_a51_candidate(r1_test, r2_test, r3_test, search_u64, val_u64)
    print(f"[*] Candidate A (Exact State) : Search={s_m}/64, Val={v_m}/64 -> {'VALID [PASS]' if ok_exact else 'INVALID [FAIL]'}")

    # 2. Test Mutated Near-Miss Candidate
    ok_miss, s_m2, v_m2 = verify_a51_candidate(r1_test, r2_test, r3_test ^ 1, search_u64, val_u64)
    print(f"[*] Candidate B (Near-Miss)   : Search={s_m2}/64, Val={v_m2}/64 -> {'INVALID [REJECTED]' if not ok_miss else 'VALID [BUG]'}")

    if ok_exact and not ok_miss:
        print("\n[✔] INDEPENDENT VERIFIER: ALL CRITERIA PASS_CLEAN")
        sys.exit(0)
    else:
        print("\n[✘] INDEPENDENT VERIFIER: FAILED")
        sys.exit(1)
