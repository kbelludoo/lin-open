# ===----------------------------------------------------------------------=== #
# Lin-Audit Ethereum — Pure Mojo Reference Verifier
# Milestone 1 (M1-A): Bit-exact Keccak-256 and Transaction Hash Recalculation
#
# ZERO Python imports. Pure typed Mojo implementation.
# Trajectory: Python Legacy -> Pure Mojo -> Normative LinVM
# ===----------------------------------------------------------------------=== #

from std.sys import argv

def parse_hex_char(c: String) -> Int:
    if c == "0": return 0
    if c == "1": return 1
    if c == "2": return 2
    if c == "3": return 3
    if c == "4": return 4
    if c == "5": return 5
    if c == "6": return 6
    if c == "7": return 7
    if c == "8": return 8
    if c == "9": return 9
    if c == "a" or c == "A": return 10
    if c == "b" or c == "B": return 11
    if c == "c" or c == "C": return 12
    if c == "d" or c == "D": return 13
    if c == "e" or c == "E": return 14
    if c == "f" or c == "F": return 15
    return -1

def hex_to_bytes(hex_str: String) -> List[UInt8]:
    var s = hex_str
    var start = 0
    if s.byte_length() >= 2 and s[byte=0] == "0" and (s[byte=1] == "x" or s[byte=1] == "X"):
        start = 2
    
    var out = List[UInt8]()
    var i = start
    var n = s.byte_length()
    while i + 1 < n:
        var h = parse_hex_char(String(s[byte=i]))
        var l = parse_hex_char(String(s[byte=i+1]))
        if h < 0 or l < 0:
            break
        out.append(UInt8((h << 4) | l))
        i += 2
    return out^

def rol64(x: UInt64, n: Int) -> UInt64:
    var shift = n & 63
    if shift == 0:
        return x
    return (x << UInt64(shift)) | (x >> UInt64(64 - shift))

def keccak_f1600(mut state: List[UInt64]):
    var rc: List[UInt64] = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008
    ]
    var rho: List[Int] = [
        0, 1, 62, 28, 27,
        36, 44, 6, 55, 20,
        3, 10, 43, 25, 39,
        41, 45, 15, 21, 8,
        18, 2, 61, 56, 14
    ]
    for ir in range(24):
        # 1. Theta
        var c = List[UInt64]()
        for x in range(5):
            c.append(state[x] ^ state[x+5] ^ state[x+10] ^ state[x+15] ^ state[x+20])
        var d = List[UInt64]()
        for x in range(5):
            d.append(c[(x+4)%5] ^ rol64(c[(x+1)%5], 1))
        for y in range(5):
            for x in range(5):
                state[x + 5*y] = state[x + 5*y] ^ d[x]
        
        # 2. Rho & Pi
        var b = List[UInt64]()
        for _ in range(25):
            b.append(0)
        for y in range(5):
            for x in range(5):
                b[y + 5*((2*x + 3*y)%5)] = rol64(state[x + 5*y], rho[x + 5*y])
        
        # 3. Chi
        for y in range(5):
            for x in range(5):
                state[x + 5*y] = b[x + 5*y] ^ ((~b[((x+1)%5) + 5*y]) & b[((x+2)%5) + 5*y])
        
        # 4. Iota
        state[0] = state[0] ^ rc[ir]

def keccak256(data: List[UInt8]) -> List[UInt8]:
    """
    Computes Ethereum Keccak-256 over raw input bytes.
    Rate = 136 bytes, Capacity = 512 bits.
    Padding = 0x01 ... 0x80 (NOT NIST SHA3-256 0x06).
    """
    var state = List[UInt64]()
    for _ in range(25):
        state.append(0)
    
    var rate_bytes = 136
    var msg_len = len(data)
    var pad_len = rate_bytes - (msg_len % rate_bytes)
    
    var padded = List[UInt8]()
    for i in range(msg_len):
        padded.append(data[i])
    
    if pad_len == 1:
        padded.append(0x81)
    else:
        padded.append(0x01)
        for _ in range(pad_len - 2):
            padded.append(0x00)
        padded.append(0x80)
    
    var total_len = len(padded)
    for block_start in range(0, total_len, rate_bytes):
        for i in range(17):
            var lane: UInt64 = 0
            for b in range(8):
                var byte_val = UInt64(padded[block_start + i*8 + b])
                lane = lane | (byte_val << UInt64(b * 8))
            state[i] = state[i] ^ lane
        keccak_f1600(state)
    
    var digest = List[UInt8]()
    for i in range(32):
        var lane_idx = i // 8
        var byte_offset = i % 8
        var b = UInt8((state[lane_idx] >> UInt64(byte_offset * 8)) & 0xFF)
        digest.append(b)
    return digest^

def bytes_to_hex(b: List[UInt8]) -> String:
    var hex_chars = "0123456789abcdef"
    var res = String("0x")
    for i in range(len(b)):
        var val = Int(b[i])
        res += hex_chars[byte=(val >> 4)]
        res += hex_chars[byte=(val & 0x0F)]
    return res

def main():
    var args = argv()
    var raw_hex = String("")
    var claimed_hash = String("")
    
    var i = 1
    while i < len(args):
        if args[i] == "--raw" and i + 1 < len(args):
            raw_hex = args[i+1]
            i += 2
        elif args[i] == "--claimed" and i + 1 < len(args):
            claimed_hash = args[i+1]
            i += 2
        elif args[i] == "tx-hash":
            i += 1
        else:
            i += 1
            
    if raw_hex.byte_length() == 0:
        print("Usage: mojo run tools/lin_audit_tx.mojo --raw <hex> [--claimed <hash>]")
        return
        
    var raw_bytes = hex_to_bytes(raw_hex)
    var digest = keccak256(raw_bytes)
    var recomputed = bytes_to_hex(digest)
    
    var matches = True
    if claimed_hash.byte_length() > 0:
        matches = (recomputed == claimed_hash)
        
    print("{")
    print('  "engine": "mojo_pure_m1_a",')
    print('  "raw_bytes_len": ' + String(len(raw_bytes)) + ",")
    print('  "recomputed_hash": "' + recomputed + '",')
    if claimed_hash.byte_length() > 0:
        print('  "claimed_hash": "' + claimed_hash + '",')
        print('  "hash_matches": ' + ("true" if matches else "false") + ",")
    print('  "verdict": "' + ("PASS" if matches else "FAIL") + '"')
    print("}")
