// Radix-2^64 schoolbook limbs. Not TCB.
// 4 x u64 = 256 bits, 8 x u64 = 512 bits.
// Carry of a*b+acc fits exactly in u128:
//   (2^64-1)^2 + 2(2^64-1) = 2^128-1.
// Independent of LIN 16-bit limbs and of C11 radix-2^32.

#![allow(dead_code)]

pub type U256 = [u64; 4];
pub type U512 = [u64; 8];

pub fn zero256() -> U256 {
    [0; 4]
}
pub fn zero512() -> U512 {
    [0; 8]
}

fn hexval(c: u8) -> i32 {
    match c {
        b'0'..=b'9' => (c - b'0') as i32,
        b'a'..=b'f' => (c - b'a' + 10) as i32,
        b'A'..=b'F' => (c - b'A' + 10) as i32,
        _ => -1,
    }
}

pub fn parse_hex_be(s: &str, out: &mut [u8]) -> bool {
    for b in out.iter_mut() {
        *b = 0;
    }
    let t = s.trim();
    let t = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")).unwrap_or(t);
    if t.len() > out.len() * 2 {
        return false;
    }
    let bytes = t.as_bytes();
    for (i, &c) in bytes.iter().rev().enumerate() {
        let v = hexval(c);
        if v < 0 {
            return false;
        }
        let idx = out.len() - 1 - (i / 2);
        if (i & 1) == 0 {
            out[idx] = v as u8;
        } else {
            out[idx] |= (v as u8) << 4;
        }
    }
    true
}

pub fn be_to_u64(be: &[u8], limbs: &mut [u64]) {
    for l in limbs.iter_mut() {
        *l = 0;
    }
    let nbe = be.len();
    for i in 0..limbs.len() {
        let end = nbe.saturating_sub(8 * i);
        if end == 0 {
            break;
        }
        let start = end.saturating_sub(8);
        let mut v = 0u64;
        for &b in &be[start..end] {
            v = (v << 8) | (b as u64);
        }
        limbs[i] = v;
    }
}

pub fn u64_to_be32(l: &U256, be: &mut [u8; 32]) {
    *be = [0; 32];
    for i in 0..4 {
        let o = 32 - 8 * (i + 1);
        let v = l[i];
        be[o] = (v >> 56) as u8;
        be[o + 1] = (v >> 48) as u8;
        be[o + 2] = (v >> 40) as u8;
        be[o + 3] = (v >> 32) as u8;
        be[o + 4] = (v >> 24) as u8;
        be[o + 5] = (v >> 16) as u8;
        be[o + 6] = (v >> 8) as u8;
        be[o + 7] = v as u8;
    }
}

pub fn hex_of(p: &[u8]) -> String {
    const H: &[u8] = b"0123456789abcdef";
    let mut s = String::with_capacity(p.len() * 2);
    for &b in p {
        s.push(H[(b >> 4) as usize] as char);
        s.push(H[(b & 15) as usize] as char);
    }
    s
}

pub fn is_zero(l: &[u64]) -> bool {
    l.iter().all(|&x| x == 0)
}

pub fn ge_limbs(a: &[u64], b: &[u64]) -> bool {
    for j in (0..a.len()).rev() {
        if a[j] > b[j] {
            return true;
        }
        if a[j] < b[j] {
            return false;
        }
    }
    true
}

pub fn mul256(a: &U256, b: &U256, n: &mut U512) -> i32 {
    *n = [0; 8];
    for i in 0..4 {
        let mut carry = 0u128;
        for j in 0..4 {
            let k = i + j;
            let t = (n[k] as u128) + (a[i] as u128) * (b[j] as u128) + carry;
            n[k] = t as u64;
            carry = t >> 64;
        }
        let mut k = i + 4;
        while k < 8 && carry != 0 {
            let t = (n[k] as u128) + carry;
            n[k] = t as u64;
            carry = t >> 64;
            k += 1;
        }
        if carry != 0 {
            return -2;
        }
    }
    1
}

pub fn div512(n: &U512, d: &U256, q: &mut U256, rem: &mut U512) -> i32 {
    *q = [0; 4];
    *rem = [0; 8];
    if is_zero(d) {
        return -1;
    }
    for bit in (0..512).rev() {
        let limb = bit >> 6;
        let pos = bit & 63;
        let mut carry = ((n[limb] >> pos) & 1) as u128;
        for j in 0..8 {
            let t = ((rem[j] as u128) << 1) + carry;
            rem[j] = t as u64;
            carry = t >> 64;
        }
        if carry != 0 {
            return -2;
        }
        let mut ge = 0i32;
        for j in (0..8).rev() {
            let dj = if j < 4 { d[j] } else { 0 };
            if rem[j] > dj {
                ge = 1;
                break;
            }
            if rem[j] < dj {
                ge = -1;
                break;
            }
        }
        if ge >= 0 {
            if bit >= 256 {
                return -2;
            }
            q[limb] |= 1u64 << pos;
            let mut borrow = 0u128;
            for j in 0..8 {
                let dj = if j < 4 { d[j] as u128 } else { 0 };
                let sub = dj + borrow;
                if (rem[j] as u128) < sub {
                    rem[j] = ((1u128 << 64) + (rem[j] as u128) - sub) as u64;
                    borrow = 1;
                } else {
                    rem[j] = ((rem[j] as u128) - sub) as u64;
                    borrow = 0;
                }
            }
        }
    }
    1
}

pub fn identity512(n: &U512, q: &U256, d: &U256, rem: &U512) -> bool {
    let mut qd = [0u64; 8];
    if mul256(q, d, &mut qd) != 1 {
        return false;
    }
    let mut carry = 0u128;
    for i in 0..8 {
        let t = (qd[i] as u128) + (rem[i] as u128) + carry;
        qd[i] = t as u64;
        carry = t >> 64;
    }
    if carry != 0 {
        return false;
    }
    if qd != *n {
        return false;
    }
    let mut dext = [0u64; 8];
    dext[..4].copy_from_slice(d);
    !ge_limbs(rem, &dext)
}

pub fn muldiv256(a: &U256, b: &U256, d: &U256, q: &mut U256, rem: &mut U512, n: &mut U512) -> i32 {
    let st = mul256(a, b, n);
    if st != 1 {
        return st;
    }
    let st = div512(n, d, q, rem);
    if st != 1 {
        return st;
    }
    if !identity512(n, q, d, rem) {
        return -2;
    }
    1
}

pub fn fill_u64(l: &mut U256, v: u64) {
    *l = [0; 4];
    l[0] = v;
}

pub fn parse256(s: &str) -> Option<U256> {
    let mut be = [0u8; 32];
    if !parse_hex_be(s, &mut be) {
        return None;
    }
    let mut l = [0u64; 4];
    be_to_u64(&be, &mut l);
    Some(l)
}

pub fn parse512(s: &str) -> Option<U512> {
    let mut be = [0u8; 64];
    if !parse_hex_be(s, &mut be) {
        return None;
    }
    let mut l = [0u64; 8];
    be_to_u64(&be, &mut l);
    Some(l)
}

pub fn hex256(l: &U256) -> String {
    let mut be = [0u8; 32];
    u64_to_be32(l, &mut be);
    hex_of(&be)
}

pub fn lo256(n: &U512) -> U256 {
    [n[0], n[1], n[2], n[3]]
}
pub fn hi256(n: &U512) -> U256 {
    [n[4], n[5], n[6], n[7]]
}

pub fn add256(a: &U256, b: &U256, out: &mut U256) -> bool {
    let mut carry = 0u128;
    for i in 0..4 {
        let t = (a[i] as u128) + (b[i] as u128) + carry;
        out[i] = t as u64;
        carry = t >> 64;
    }
    carry != 0
}

pub fn eq256(a: &U256, b: &U256) -> bool {
    a == b
}
