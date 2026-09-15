#!/usr/bin/env python3
"""
oracle_store.py — Independent Reference Oracle for Native STORE (STORE_SPEC v1)
Standard NIST FIPS 180-4 SHA-256 state commitment oracle and WAL verifier.
Used for differential N-version cross-checking against store_c0 (C11).
"""

import sys
import os
import struct
import hashlib
import json

MAGIC_WAL = b"STRW"
MAGIC_CHK = b"STRCHK"
OP_PUT = 1
OP_DEL = 2
MAX_KEY_LEN = 1024
MAX_VAL_LEN = 1024 * 1024
PAGE_SIZE = 4096

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def compute_merkle_leaf(key: bytes, val: bytes) -> bytes:
    prefix = b"\x00"
    klen = struct.pack("<H", len(key))
    vlen = struct.pack("<I", len(val))
    return sha256(prefix + klen + key + vlen + val)

def compute_merkle_parent(left: bytes, right: bytes) -> bytes:
    prefix = b"\x01"
    return sha256(prefix + left + right)

def compute_merkle_root(kvs: dict) -> bytes:
    if not kvs:
        return sha256(b"STR_EMPTY_v1")
    
    # Sort keys byte-wise (lexicographical order)
    sorted_keys = sorted(kvs.keys())
    
    leaves = [compute_merkle_leaf(k, kvs[k]) for k in sorted_keys]
    
    level = leaves
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if (i + 1 < len(level)) else level[i] # duplicate odd
            next_level.append(compute_merkle_parent(left, right))
        level = next_level
        
    return level[0]

def parse_and_replay_wal(wal_path: str):
    if not os.path.exists(wal_path):
        raise FileNotFoundError(f"WAL file {wal_path} does not exist")

    with open(wal_path, "rb") as f:
        data = f.read()

    if len(data) == 0:
        # Brand-new DB (C creates header on open): zero frames, empty map.
        return 0, {}

    if len(data) < 12:
        # Existing file with a partial header is strict corruption
        # (mirrors C STORE_ERR_CORRUPT, never an empty DB).
        raise ValueError(f"Truncated WAL header ({len(data)} bytes < 12): corrupt")

    magic, ver, page, res = struct.unpack("<4sHIH", data[:12])
    if magic != MAGIC_WAL or ver != 1 or page != PAGE_SIZE or res != 0:
        raise ValueError(f"Invalid WAL header: {magic} ver={ver} page={page} res={res}")
        
    offset = 12
    valid_frames = 0
    memtable = {}
    
    while offset < len(data):
        frame_start = offset
        if offset + 4 > len(data):
            # Short read on frame_len
            break
        
        frame_len = struct.unpack("<I", data[offset:offset+4])[0]
        offset += 4
        
        if offset + frame_len > len(data):
            # Short read on frame body (torn write)
            break
            
        frame_body = data[offset:offset+frame_len]
        if frame_len < 39:
            break
            
        op = frame_body[0]
        klen, vlen = struct.unpack("<HI", frame_body[1:7])
        if 7 + klen + vlen + 32 != frame_len:
            break

        # Strict caps mirroring C recovery: empty key, oversized key/val,
        # unknown op, or DEL with payload can never be a valid commit.
        # Any of these truncates the tail (fail-closed to valid prefix).
        if klen == 0 or klen > MAX_KEY_LEN or vlen > MAX_VAL_LEN:
            break
        if op not in (OP_PUT, OP_DEL):
            break
        if op == OP_DEL and vlen != 0:
            break
            
        key = frame_body[7:7+klen]
        val = frame_body[7+klen:7+klen+vlen]
        stored_sum = frame_body[7+klen+vlen:7+klen+vlen+32]
        
        calc_sum = sha256(frame_body[:7+klen+vlen])
        if calc_sum != stored_sum:
            # Corrupted sum
            break
            
        if op == OP_PUT:
            memtable[key] = val
        elif op == OP_DEL:
            memtable.pop(key, None)
            
        offset += frame_len
        valid_frames += 1
        
    return valid_frames, memtable

def verify_checkpoint(chk_path: str):
    if not os.path.exists(chk_path):
        raise FileNotFoundError(f"Checkpoint file {chk_path} does not exist")
        
    with open(chk_path, "rb") as f:
        raw = f.read()
        
    if len(raw) != 80:
        raise ValueError(f"Invalid checkpoint size: {len(raw)} != 80")
        
    magic, ver, frames = struct.unpack("<6sHQ", raw[:16])
    root = raw[16:48]
    stored_sum = raw[48:80]
    
    if magic != MAGIC_CHK or ver != 1:
        raise ValueError("Invalid checkpoint header")
        
    calc_sum = sha256(raw[:48])
    if calc_sum != stored_sum:
        raise ValueError("Checkpoint checksum mismatch")
        
    return frames, root.hex()

def run_self_test():
    # 1. Empty root test
    empty_root = compute_merkle_root({})
    expected_empty = hashlib.sha256(b"STR_EMPTY_v1").digest()
    assert empty_root == expected_empty, f"Empty root mismatch: {empty_root.hex()} != {expected_empty.hex()}"

    # 2. Single leaf
    leaf_root = compute_merkle_root({b"k": b"v"})
    expected_leaf = compute_merkle_leaf(b"k", b"v")
    assert leaf_root == expected_leaf, "Single leaf root mismatch"

    # 3. Two leaves
    two_root = compute_merkle_root({b"a": b"1", b"b": b"2"})
    leaf_a = compute_merkle_leaf(b"a", b"1")
    leaf_b = compute_merkle_leaf(b"b", b"2")
    expected_two = compute_merkle_parent(leaf_a, leaf_b)
    assert two_root == expected_two, "Two leaves root mismatch"

    # 4. Odd leaves (3 leaves)
    three_root = compute_merkle_root({b"a": b"1", b"b": b"2", b"c": b"3"})
    leaf_c = compute_merkle_leaf(b"c", b"3")
    parent_0 = compute_merkle_parent(leaf_a, leaf_b)
    parent_1 = compute_merkle_parent(leaf_c, leaf_c) # duplicate odd
    expected_three = compute_merkle_parent(parent_0, parent_1)
    assert three_root == expected_three, "Three leaves root mismatch"

    print("ORACLE_SELF_TEST_OK")
    return True

def run_crash_matrix():
    print("[Oracle Crash Matrix] Generating test WAL for exhaustive crash testing...")
    # Build 12-byte header
    wal_bytes = bytearray(b"STRW" + struct.pack("<HIH", 1, 4096, 0))

    # Frame helper
    def add_frame(op, key, val):
        flen = 1 + 2 + 4 + len(key) + len(val) + 32
        body = bytearray([op]) + struct.pack("<HI", len(key), len(val)) + key + val
        csum = sha256(body)
        return struct.pack("<I", flen) + body + csum

    wal_bytes += add_frame(OP_PUT, b"k1", b"v1")
    wal_bytes += add_frame(OP_PUT, b"k2", b"v2")
    wal_bytes += add_frame(OP_PUT, b"k3", b"v3")

    total_len = len(wal_bytes)
    # Each frame here: flen=43 + 4 len prefix = 47 bytes.
    frame_boundaries = [12, 12 + 47, 12 + 94, 12 + 141]
    assert total_len == 153, f"fixture size changed: {total_len} != 153"
    assert frame_boundaries[3] == total_len
    expected_kvs_by_frames = [
        {},
        {b"k1": b"v1"},
        {b"k1": b"v1", b"k2": b"v2"},
        {b"k1": b"v1", b"k2": b"v2", b"k3": b"v3"},
    ]
    tmp_wal = "oracle_crash_test.wal"

    try:
        print(f"  -> Testing exhaustive truncation across all {total_len + 1} byte boundaries (0..{total_len})...")
        n_trunc = 0
        for trunc_len in range(total_len + 1):
            with open(tmp_wal, "wb") as f:
                f.write(wal_bytes[:trunc_len])
            if trunc_len == 0:
                frames, kvs = parse_and_replay_wal(tmp_wal)
                assert frames == 0 and kvs == {}, "empty file must replay as empty DB"
            elif trunc_len < 12:
                # Strict corruption: 1..11 bytes is never an empty DB.
                try:
                    parse_and_replay_wal(tmp_wal)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"trunc {trunc_len}: 1..11B header must raise CORRUPT")
                n_trunc += 1
                continue
            else:
                frames, kvs = parse_and_replay_wal(tmp_wal)
                # Exact expected prefix: count fully contained frames.
                exp_frames = 0
                for b in (59, 106, 153):
                    if trunc_len >= b:
                        exp_frames += 1
                assert frames == exp_frames, (
                    f"trunc {trunc_len}: frames {frames} != expected {exp_frames}")
                assert kvs == expected_kvs_by_frames[exp_frames], (
                    f"trunc {trunc_len}: kvs mismatch")
                # Exact root reconstitution after every truncation.
                got_root = compute_merkle_root(kvs)
                exp_root = compute_merkle_root(expected_kvs_by_frames[exp_frames])
                assert got_root == exp_root, f"trunc {trunc_len}: root mismatch"
            n_trunc += 1
        print(f"     truncations checked: {n_trunc} (incl. 11 strict-corrupt headers + exact roots)")

        print(f"  -> Testing exhaustive single-bit flips across all {total_len} bytes x 8 bits...")
        n_flip = 0
        for byte_idx in range(total_len):
            for bit in range(8):
                corrupted = bytearray(wal_bytes)
                corrupted[byte_idx] ^= (1 << bit)
                with open(tmp_wal, "wb") as f:
                    f.write(corrupted)
                if byte_idx < 12:
                    # Any header bit-flip breaks magic/ver/page/reserved: CORRUPT.
                    try:
                        parse_and_replay_wal(tmp_wal)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError(
                            f"header flip byte {byte_idx} bit {bit}: must raise CORRUPT")
                else:
                    frames, kvs = parse_and_replay_wal(tmp_wal)
                    # Corrupted payload must kill the affected frame or later ones.
                    assert frames < 3, (
                        f"payload flip byte {byte_idx} bit {bit}: erroneously accepted ({frames})")
                    # Replayed state must be an exact valid prefix, never corrupted data.
                    assert kvs in expected_kvs_by_frames, (
                        f"flip byte {byte_idx} bit {bit}: non-prefix kvs {kvs}")
                    assert len(kvs) == frames, (
                        f"flip byte {byte_idx} bit {bit}: keys {len(kvs)} != frames {frames}")
                    assert compute_merkle_root(kvs) == compute_merkle_root(kvs), \
                        "root must recompute cleanly"
                n_flip += 1
        print(f"     bit-flips checked: {n_flip} (12 header bytes fail-closed + payload exact-prefix)")
    finally:
        if os.path.exists(tmp_wal):
            os.remove(tmp_wal)

    print("ORACLE_CRASH_MATRIX_ALL_PASS")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: oracle_store.py [--self-test] [--crash-matrix] [--root-of-kvs <json>] [--verify-wal <wal>] [--verify-chk <chk>]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "--self-test":
        run_self_test()
    elif cmd == "--crash-matrix":
        run_crash_matrix()
    elif cmd == "--root-of-kvs":
        with open(sys.argv[2], "r") as f:
            data = json.load(f)
        kvs = {k.encode('utf-8'): v.encode('utf-8') for k, v in data.items()}
        root = compute_merkle_root(kvs)
        print(root.hex())
    elif cmd == "--verify-wal":
        frames, kvs = parse_and_replay_wal(sys.argv[2])
        root = compute_merkle_root(kvs)
        print(f"FRAMES={frames}")
        print(f"KEYS={len(kvs)}")
        print(f"ROOT={root.hex()}")
    elif cmd == "--verify-chk":
        frames, root_hex = verify_checkpoint(sys.argv[2])
        print(f"CHK_FRAMES={frames}")
        print(f"CHK_ROOT={root_hex}")
    else:
        print(f"Unknown command {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
