// Zero-crate rustc auditor for schema 1.14 evidence.json.
// Recomputes LRI1 q*d+r==n with radix-2^64 limbs, binds LCR2/LCR2-full
// mulDiv(fee,rout,den), and SHA-256 (FIPS 180-4) of the LRI1 Merkle tree.
// No LinVM, no gcc, no Python. EXPERIMENTAL FullMath width, not CRT.
#[path = "../../test/oracles/u512_rust64_limbs.rs"]
mod limbs;

use limbs::*;
use std::env;
use std::fs;
use std::process;

const SCHEMA: &str = "LIN_U512_COPROCESSOR_EVIDENCE_1.14";
const RI_LEAF: &[u8] = b"LIN:U512:RI:LEAF:1";
const RI_NODE: &[u8] = b"LIN:U512:RI:NODE:1";
const K: [u32; 64] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

fn rotr(x: u32, n: u32) -> u32 {
    x.rotate_right(n)
}

fn sha256(msg: &[u8]) -> [u8; 32] {
    let mut h = [0x6a09e667u32, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    let bit_len = (msg.len() as u64) * 8;
    let mut buf = msg.to_vec();
    buf.push(0x80);
    while (buf.len() % 64) != 56 {
        buf.push(0);
    }
    buf.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in buf.chunks_exact(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes(chunk[4 * i..4 * i + 4].try_into().unwrap());
        }
        for i in 16..64 {
            let s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
            let s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
        }
        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut hh = h[7];
        for i in 0..64 {
            let s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh.wrapping_add(s1).wrapping_add(ch).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }
    let mut out = [0u8; 32];
    for i in 0..8 {
        out[4 * i..4 * i + 4].copy_from_slice(&h[i].to_be_bytes());
    }
    out
}

fn json_str(text: &str, key: &str) -> Option<String> {
    let pat = format!("\"{key}\"");
    let mut start = 0;
    while let Some(i) = text[start..].find(&pat) {
        let abs = start + i + pat.len();
        let rest = text[abs..].trim_start();
        if let Some(r) = rest.strip_prefix(':') {
            let r = r.trim_start();
            if let Some(r) = r.strip_prefix('"') {
                if let Some(end) = r.find('"') {
                    return Some(r[..end].to_string());
                }
            }
        }
        start = abs;
    }
    None
}

fn json_i64(text: &str, key: &str) -> Option<i64> {
    let pat = format!("\"{key}\"");
    let i = text.find(&pat)?;
    let rest = text[i + pat.len()..].trim_start().strip_prefix(':')?.trim_start();
    let mut e = 0;
    if rest.starts_with('-') {
        e = 1;
    }
    while e < rest.len() && rest.as_bytes()[e].is_ascii_digit() {
        e += 1;
    }
    rest[..e].parse().ok()
}

fn json_objects(text: &str, key: &str) -> Vec<String> {
    let pat = format!("\"{key}\"");
    let Some(i) = text.find(&pat) else { return vec![] };
    let rest = &text[i + pat.len()..];
    let Some(b) = rest.find('[') else { return vec![] };
    let mut depth = 0i32;
    let mut end = None;
    for (k, c) in rest[b..].char_indices() {
        match c {
            '[' => depth += 1,
            ']' => {
                depth -= 1;
                if depth == 0 {
                    end = Some(b + k);
                    break;
                }
            }
            _ => {}
        }
    }
    let Some(end) = end else { return vec![] };
    let body = &rest[b + 1..end];
    let mut out = vec![];
    let mut d = 0i32;
    let mut start = None;
    for (k, c) in body.char_indices() {
        match c {
            '{' => {
                if d == 0 {
                    start = Some(k);
                }
                d += 1;
            }
            '}' => {
                d -= 1;
                if d == 0 {
                    if let Some(s) = start {
                        out.push(body[s..=k].to_string());
                    }
                    start = None;
                }
            }
            _ => {}
        }
    }
    out
}

fn pack_u64_le(dst: &mut [u8], off: usize, v: u64) {
    dst[off..off + 8].copy_from_slice(&v.to_le_bytes());
}

fn pack_i64_le(dst: &mut [u8], off: usize, v: i64) {
    dst[off..off + 8].copy_from_slice(&v.to_le_bytes());
}

fn pack_be32(dst: &mut [u8], off: usize, l: &U256) {
    let mut be = [0u8; 32];
    u64_to_be32(l, &mut be);
    dst[off..off + 32].copy_from_slice(&be);
}

fn lri1_rec(src: &[u8; 32], run_id: u64, vid: u64, n: &U512, d: &U256, q: &U256, r: &U256, steps: u64, status: i64) -> [u8; 240] {
    let mut raw = [0u8; 240];
    raw[0..4].copy_from_slice(b"LRI1");
    raw[4] = 1;
    raw[8..40].copy_from_slice(src);
    pack_u64_le(&mut raw, 40, run_id);
    pack_u64_le(&mut raw, 48, vid);
    pack_be32(&mut raw, 56, &lo256(n));
    pack_be32(&mut raw, 88, &hi256(n));
    pack_be32(&mut raw, 120, d);
    pack_be32(&mut raw, 152, q);
    pack_be32(&mut raw, 184, r);
    pack_u64_le(&mut raw, 216, steps);
    pack_i64_le(&mut raw, 224, status);
    raw
}

fn merkle(recs: &[[u8; 240]]) -> [u8; 32] {
    let mut nodes: Vec<[u8; 32]> = recs
        .iter()
        .map(|r| {
            let mut cat = Vec::with_capacity(RI_LEAF.len() + r.len());
            cat.extend_from_slice(RI_LEAF);
            cat.extend_from_slice(r);
            sha256(&cat)
        })
        .collect();
    while nodes.len() > 1 {
        let mut nxt = vec![];
        let mut i = 0;
        while i < nodes.len() {
            let l = nodes[i];
            let r = if i + 1 < nodes.len() { nodes[i + 1] } else { l };
            let mut cat = Vec::with_capacity(RI_NODE.len() + 64);
            cat.extend_from_slice(RI_NODE);
            cat.extend_from_slice(&l);
            cat.extend_from_slice(&r);
            nxt.push(sha256(&cat));
            i += 2;
        }
        nodes = nxt;
    }
    nodes[0]
}

fn fail(msg: &str) -> i32 {
    println!("FAIL {msg}");
    1
}

fn mul_small(a: &U256, k: u64, out: &mut U256) -> bool {
    let mut kk = zero256();
    fill_u64(&mut kk, k);
    let mut n = zero512();
    if mul256(a, &kk, &mut n) != 1 {
        return true;
    }
    if hi256(&n) != [0; 4] {
        return true;
    }
    *out = lo256(&n);
    false
}

fn main() {
    let path = match env::args().nth(1) {
        Some(p) => p,
        None => {
            eprintln!("usage: verify_u512_rust64 <evidence.json>");
            process::exit(2);
        }
    };
    let abc = sha256(b"abc");
    if hex_of(&abc) != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" {
        process::exit(fail("sha256 fips abc"));
    }
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => process::exit(fail("read")),
    };
    if json_str(&text, "schema").as_deref() != Some(SCHEMA) {
        process::exit(fail("schema"));
    }
    if json_str(&text, "class").as_deref() != Some("EXPERIMENTAL") {
        process::exit(fail("class"));
    }
    let src_hex = json_str(&text, "lin_src").unwrap_or_default();
    let mut src = [0u8; 32];
    if !parse_hex_be(&src_hex, &mut src) {
        process::exit(fail("lin_src"));
    }
    let run_r = json_i64(&text, "lri1_run_id").unwrap_or(5) as u64;
    let want_root = json_str(&text, "lri1_merkle").unwrap_or_default();
    let ri_objs = json_objects(&text, "lri1_leaves");
    if ri_objs.len() < 8 {
        process::exit(fail("need 8 LRI1"));
    }
    let mut recs = vec![];
    for (i, obj) in ri_objs.iter().enumerate() {
        let a = parse256(&json_str(obj, "a").unwrap_or_default());
        let b = parse256(&json_str(obj, "b").unwrap_or_default());
        let d = parse256(&json_str(obj, "d").unwrap_or_default());
        let n = parse512(&json_str(obj, "n").unwrap_or_default());
        let q = parse256(&json_str(obj, "q").unwrap_or_default());
        let r = parse256(&json_str(obj, "r").unwrap_or_default());
        let steps = json_i64(obj, "steps").unwrap_or(0);
        let status = json_i64(obj, "status").unwrap_or(0);
        let (Some(a), Some(b), Some(d), Some(n), Some(q), Some(rlo)) = (a, b, d, n, q, r) else {
            process::exit(fail("lri1 parse"));
        };
        if steps == 0 || status != 1 {
            process::exit(fail("lri1 steps/status"));
        }
        let mut prod = zero512();
        if mul256(&a, &b, &mut prod) != 1 || prod != n {
            process::exit(fail("lri1 n!=a*b"));
        }
        let mut qq = zero256();
        let mut rem = zero512();
        let mut nn = zero512();
        if muldiv256(&a, &b, &d, &mut qq, &mut rem, &mut nn) != 1 {
            process::exit(fail("lri1 muldiv"));
        }
        if qq != q || lo256(&rem) != rlo || nn != n {
            process::exit(fail("lri1 rust64 mismatch"));
        }
        recs.push(lri1_rec(&src, run_r, i as u64, &n, &d, &q, &rlo, steps as u64, status));
    }
    let root = merkle(&recs);
    if hex_of(&root) != want_root {
        process::exit(fail(&format!("lri1 merkle {} != {want_root}", hex_of(&root))));
    }

    let mut n_ex = 0;
    let mut n_ov = 0;
    let mut n_ph = 0;
    for obj in &json_objects(&text, "lcr2_leaves") {
        let cls = json_str(obj, "class").unwrap_or_default();
        if cls != "EXACT_INPUT" && cls != "OVERPAID_INPUT" {
            continue;
        }
        let ain = parse256(&json_str(obj, "ain").unwrap_or_default()).unwrap_or([0; 4]);
        let rin = parse256(&json_str(obj, "rin").unwrap_or_default()).unwrap_or([0; 4]);
        let rout = parse256(&json_str(obj, "rout").unwrap_or_default()).unwrap_or([0; 4]);
        let aout = parse256(&json_str(obj, "aout").unwrap_or_default()).unwrap_or([0; 4]);
        let mut fee = zero256();
        let mut r1000 = zero256();
        if mul_small(&ain, 997, &mut fee) || mul_small(&rin, 1000, &mut r1000) {
            process::exit(fail("lcr2 width"));
        }
        let mut den = zero256();
        if add256(&r1000, &fee, &mut den) {
            process::exit(fail("lcr2 den"));
        }
        let mut q = zero256();
        let mut rem = zero512();
        let mut n = zero512();
        if muldiv256(&fee, &rout, &den, &mut q, &mut rem, &mut n) != 1 || q != aout {
            process::exit(fail("lcr2 mulDiv"));
        }
        if cls == "EXACT_INPUT" {
            n_ex += 1;
        } else {
            n_ov += 1;
        }
    }
    if n_ex < 3 || n_ov < 3 {
        process::exit(fail("lcr2 counts"));
    }

    for obj in &json_objects(&text, "lcr2_full_leaves") {
        let cls = json_str(obj, "class").unwrap_or_default();
        if cls != "PHANTOM_APPROVE" {
            continue;
        }
        let ain = parse256(&json_str(obj, "ain").unwrap_or_default()).unwrap_or([0; 4]);
        let rin = parse256(&json_str(obj, "rin").unwrap_or_default()).unwrap_or([0; 4]);
        let rout = parse256(&json_str(obj, "rout").unwrap_or_default()).unwrap_or([0; 4]);
        let aout = parse256(&json_str(obj, "aout").unwrap_or_default()).unwrap_or([0; 4]);
        let mut fee = zero256();
        let mut r1000 = zero256();
        if mul_small(&ain, 997, &mut fee) || mul_small(&rin, 1000, &mut r1000) {
            process::exit(fail("phantom width"));
        }
        let mut den = zero256();
        if add256(&r1000, &fee, &mut den) {
            process::exit(fail("phantom den"));
        }
        let mut q = zero256();
        let mut rem = zero512();
        let mut n = zero512();
        if muldiv256(&fee, &rout, &den, &mut q, &mut rem, &mut n) != 1 || q != aout {
            process::exit(fail("phantom mulDiv"));
        }
        n_ph += 1;
    }
    if n_ph < 1 {
        process::exit(fail("need PHANTOM_APPROVE"));
    }

    println!("PASS rustc radix-2^64 auditor");
    println!("sha256_fips_abc ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    println!("lri1_rust64_identity {}", ri_objs.len());
    println!("lri1_match {}", want_root);
    println!("lcr2_rust64_bind exact={n_ex} overpaid={n_ov}");
    println!("lcr2_full_phantom {n_ph}");
}
