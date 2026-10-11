// Independent rustc oracle: schoolbook in radix 2^64 (not TCB, zero crates).
// EXPERIMENTAL: FullMath width, not CRT/mulmod.
#[path = "u512_rust64_limbs.rs"]
mod limbs;

use limbs::*;
use std::io::{self, BufRead, Write};

fn expect_st(st: i32, want: i32, m: &str) -> i32 {
    if st != want {
        eprintln!("FAIL {m} status={st} want={want}");
        return 1;
    }
    0
}

fn selftest() -> i32 {
    let mut a = zero256();
    let mut b = zero256();
    let mut d = zero256();
    let mut q = zero256();
    let mut rem = zero512();
    let mut n = zero512();
    let mut fail = 0;

    fill_u64(&mut a, 7);
    fill_u64(&mut b, 9);
    fill_u64(&mut d, 2);
    let st = muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n);
    fail |= expect_st(st, 1, "7*9/2");
    if q[0] != 31 || rem[0] != 1 {
        eprintln!("FAIL 7*9/2 words");
        fail = 1;
    }

    a = [u64::MAX; 4];
    b = [u64::MAX; 4];
    let st = mul256(&a, &b, &mut n);
    fail |= expect_st(st, 1, "max*max");
    if n[0] != 1 {
        eprintln!("FAIL max^2 lo");
        fail = 1;
    }
    if n[4] != u64::MAX - 1 {
        eprintln!("FAIL max^2 hi limb4");
        fail = 1;
    }

    a = [0; 4];
    a[3] = 1u64 << 63;
    fill_u64(&mut b, 2);
    fill_u64(&mut d, 3);
    let st = muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n);
    fail |= expect_st(st, 1, "2^255*2/3");
    if q[0] != 0x5555_5555_5555_5555 || q[3] != 0x5555_5555_5555_5555 || rem[0] != 1 {
        eprintln!("FAIL 2^255*2/3 pattern");
        fail = 1;
    }
    if !identity512(&n, &q, &d, &rem) {
        eprintln!("FAIL identity 2^255*2/3");
        fail = 1;
    }

    fill_u64(&mut a, 1);
    fill_u64(&mut b, 1);
    d = [0; 4];
    fail |= expect_st(muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n), -1, "d=0");

    a = [0; 4];
    a[3] = 1u64 << 63;
    fill_u64(&mut b, 2);
    fill_u64(&mut d, 1);
    fail |= expect_st(muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n), -2, "q overflow");

    fill_u64(&mut a, 997000);
    fill_u64(&mut b, 20000);
    fill_u64(&mut d, 10997000);
    let st = muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n);
    fail |= expect_st(st, 1, "getAmountOut");
    if q[0] != 1813 {
        eprintln!("FAIL 1813");
        fail = 1;
    }

    a = [0; 4];
    a[0] = 2;
    b = [0; 4];
    b[3] = 1u64 << 63;
    d = [u64::MAX; 4];
    let st = muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n);
    fail |= expect_st(st, 1, "wrap-borrow");
    if q[0] != 1 || rem[0] != 1 {
        eprintln!("FAIL wrap-borrow words");
        fail = 1;
    }

    let mut a512 = [0u64; 8];
    let mut b512 = [0u64; 8];
    a512[4] = 1;
    b512[..4].copy_from_slice(&[u64::MAX; 4]);
    if !ge_limbs(&a512, &b512) || ge_limbs(&b512, &a512) || !ge_limbs(&a512, &a512) {
        fail = 1;
    }

    let acc: u128 = (u64::MAX as u128) * (u64::MAX as u128) + 2 * (u64::MAX as u128);
    if acc != u128::MAX {
        eprintln!("FAIL carry_fits_u128");
        fail = 1;
    }

    if fail != 0 {
        return 1;
    }
    println!("SELFTEST_PASS rust64 q*d+r==n ge512 carry_fits_u128");
    0
}

fn run_batch() -> i32 {
    let stdin = io::stdin();
    let mut nvec = 0i32;
    for line in stdin.lock().lines() {
        let Ok(line) = line else { return 1 };
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() < 3 {
            continue;
        }
        match parts[0] {
            "GE" => {
                let Some(a) = parse512(parts[1]) else { return 1 };
                let Some(b) = parse512(parts[2]) else { return 1 };
                println!("{}", if ge_limbs(&a, &b) { 1 } else { 0 });
            }
            "MUL" => {
                let Some(a) = parse256(parts[1]) else { return 1 };
                let Some(b) = parse256(parts[2]) else { return 1 };
                let mut n = zero512();
                let st = mul256(&a, &b, &mut n);
                println!("{} {} {}", st, hex256(&lo256(&n)), hex256(&hi256(&n)));
            }
            "MULDIV" => {
                if parts.len() < 4 {
                    return 1;
                }
                let Some(a) = parse256(parts[1]) else { return 1 };
                let Some(b) = parse256(parts[2]) else { return 1 };
                let Some(d) = parse256(parts[3]) else { return 1 };
                let mut q = zero256();
                let mut rem = zero512();
                let mut n = zero512();
                let st = muldiv256(&a, &b, &d, &mut q, &mut rem, &mut n);
                println!("{} {} {}", st, hex256(&q), hex256(&lo256(&rem)));
            }
            _ => {
                let _ = writeln!(io::stderr(), "unknown op {}", parts[0]);
                return 1;
            }
        }
        nvec += 1;
    }
    let _ = writeln!(io::stderr(), "BATCH_N={nvec} RUST64_CONSENSUS");
    0
}

fn main() {
    let mut args = std::env::args();
    let _ = args.next();
    let mode = args.next().unwrap_or_default();
    let code = match mode.as_str() {
        "--self-test" => selftest(),
        "--batch" => run_batch(),
        _ => {
            eprintln!("usage: u512_rust64_oracle --self-test | --batch");
            2
        }
    };
    std::process::exit(code);
}
