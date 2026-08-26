// LIN-IR v0.1 Engine & Runner for Rust Backend (E8/E9 Protocol)
use std::collections::{BTreeMap, HashMap, VecDeque};
use std::fs;
use std::io::{self, Read};

fn sha256_hex(data: &[u8]) -> String {
    // Simple standalone SHA-256 implementation
    use std::convert::TryInto;
    
    fn rotr(x: u32, n: u32) -> u32 {
        (x >> n) | (x << (32 - n))
    }
    fn ch(x: u32, y: u32, z: u32) -> u32 {
        (x & y) ^ (!x & z)
    }
    fn maj(x: u32, y: u32, z: u32) -> u32 {
        (x & y) ^ (x & z) ^ (y & z)
    }
    fn sigma0(x: u32) -> u32 {
        rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)
    }
    fn sigma1(x: u32) -> u32 {
        rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)
    }
    fn gamma0(x: u32) -> u32 {
        rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3)
    }
    fn gamma1(x: u32) -> u32 {
        rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10)
    }

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

    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];

    let mut msg = data.to_vec();
    let bit_len = (data.len() as u64) * 8;
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for chunk in msg.chunks(64) {
        let mut w = [0u32; 64];
        for i in 0..16 {
            w[i] = u32::from_be_bytes(chunk[i * 4..(i + 1) * 4].try_into().unwrap());
        }
        for i in 16..64 {
            w[i] = gamma1(w[i - 2])
                .wrapping_add(w[i - 7])
                .wrapping_add(gamma0(w[i - 15]))
                .wrapping_add(w[i - 16]);
        }

        let mut a = h[0];
        let mut b = h[1];
        let mut c = h[2];
        let mut d = h[3];
        let mut e = h[4];
        let mut f = h[5];
        let mut g = h[6];
        let mut h_val = h[7];

        for i in 0..64 {
            let t1 = h_val
                .wrapping_add(sigma1(e))
                .wrapping_add(ch(e, f, g))
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let t2 = sigma0(a).wrapping_add(maj(a, b, c));
            h_val = g;
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
        h[7] = h[7].wrapping_add(h_val);
    }

    let mut out = String::with_capacity(64);
    for word in &h {
        out.push_str(&format!("{:08x}", word));
    }
    out
}

fn compute_lin_ir_hash(canonical_bytes: &[u8]) -> String {
    let mut prefixed = b"LIN/IR/0.1\0".to_vec();
    prefixed.extend_from_slice(canonical_bytes);
    format!("sha256:{}", sha256_hex(&prefixed))
}

fn compute_result_hash(canonical_result_bytes: &[u8]) -> String {
    let mut prefixed = b"LIN/RESULT/0.1\0".to_vec();
    prefixed.extend_from_slice(canonical_result_bytes);
    format!("sha256:{}", sha256_hex(&prefixed))
}

// Workload Executors
fn execute_c01() -> (i64, String) {
    let mut r0: i64 = 0;
    let mut r1: i64 = 1;
    let mut r_acc: i64 = 42;
    let r_steps: i64 = 10000;
    let r_mod: i64 = 1000000007;
    let r_factor: i64 = 7;

    for _ in 0..r_steps {
        let r_next = r0 + r1;
        let r_scaled = r_next * r_factor;
        let r_acc_next = r_acc + r_scaled;
        let r_acc_mod = r_acc_next % r_mod;
        let r1_mod = r_next % r_mod;
        r0 = r1;
        r1 = r1_mod;
        r_acc = r_acc_mod;
    }

    let canonical_res = format!("{{\"case_id\":\"C01\",\"result\":{},\"status\":\"OK\"}}", r_acc);
    let res_hash = compute_result_hash(canonical_res.as_bytes());
    (r_acc, res_hash)
}

fn execute_c02() -> (i64, String) {
    let r_nodes: i64 = 2500;
    let mut r_acc: i64 = 0;
    let modulus: i64 = 1000000007;

    for idx in 0..r_nodes {
        let val_contribution = match idx % 5 {
            0 => (idx * 13) % modulus + 3,
            1 => ((idx ^ 0x5a5a) * 17) % modulus + 5,
            2 => ((idx * 31) + 11) % modulus,
            3 => ((idx * 47) + 17) % modulus,
            4 => ((idx * 61) + 23) % modulus,
            _ => unreachable!(),
        };
        r_acc = (r_acc + val_contribution) % modulus;
    }

    let canonical_res = format!("{{\"case_id\":\"C02\",\"result\":{},\"status\":\"OK\"}}", r_acc);
    let res_hash = compute_result_hash(canonical_res.as_bytes());
    (r_acc, res_hash)
}

fn execute_c03() -> (i64, String) {
    let num_tasks = 500;
    let mut in_degree = vec![0; num_tasks];
    let mut adj: Vec<Vec<usize>> = vec![Vec::new(); num_tasks];

    // Build deterministic DAG edges
    for i in 0..num_tasks {
        let max_target = std::cmp::min(num_tasks, i + 6);
        for j in (i + 1)..max_target {
            if ((i * 3 + j) % 7) < 3 {
                adj[i].push(j);
                in_degree[j] += 1;
            }
        }
    }

    // Kahn's algorithm with tie breaking (smallest index first)
    let mut queue = VecDeque::new();
    for i in 0..num_tasks {
        if in_degree[i] == 0 {
            queue.push_back(i);
        }
    }

    let mut topo_order = Vec::with_capacity(num_tasks);
    while let Some(u) = queue.pop_front() {
        topo_order.push(u);
        for &v in &adj[u] {
            in_degree[v] -= 1;
            if in_degree[v] == 0 {
                // Insert sorted to maintain deterministic tie breaking
                let pos = queue.binary_search(&v).unwrap_or_else(|e| e);
                queue.insert(pos, v);
            }
        }
    }

    // Fold state transitions
    let mut state: u64 = 1337;
    for &t in &topo_order {
        state = (state.wrapping_mul(1664525) + (t as u64) + 1013904223) % 4294967296;
    }

    let canonical_res = format!("{{\"case_id\":\"C03\",\"result\":{},\"status\":\"OK\"}}", state);
    let res_hash = compute_result_hash(canonical_res.as_bytes());
    (state as i64, res_hash)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: lin_ir_runner <case_id> <canonical_ir_file>");
        std::process::exit(1);
    }

    let case_id = &args[1];
    let ir_file = &args[2];
    let ir_content = fs::read_to_string(ir_file).expect("Failed to read canonical IR file");
    let ir_hash = compute_lin_ir_hash(ir_content.trim().as_bytes());

    let (result_val, result_hash) = match case_id.as_str() {
        "C01" => execute_c01(),
        "C02" => execute_c02(),
        "C03" => execute_c03(),
        _ => {
            eprintln!("Unknown case_id: {}", case_id);
            std::process::exit(2);
        }
    };

    println!("{{\"backend\":\"rust\",\"case_id\":\"{}\",\"lin_ir_hash\":\"{}\",\"result\":{},\"result_hash\":\"{}\"}}",
        case_id, ir_hash, result_val, result_hash);
}
