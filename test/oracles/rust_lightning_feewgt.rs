// Independent Rust oracle for rust-lightning v0.2.7 fee_for_weight.
// Mirrors the published wrapping formula and the LIN remainder-ceil lift.
// Not linked into the LIN compiler TCB. Algorithm license: Apache-2.0 OR MIT.
use std::env;

const KW: i64 = 1000;
const FLOOR: i64 = 253;
const U32_MAX: i64 = 4_294_967_295;
const I64_MAX: i64 = i64::MAX;

fn prod_ok(a: i64, b: i64) -> bool {
    if a < 0 || b < 0 {
        return false;
    }
    if a == 0 || b == 0 {
        return true;
    }
    b <= I64_MAX / a
}

fn ceil_div(num: i64, den: i64) -> i64 {
    if den <= 0 || num < 0 {
        return 0;
    }
    let q = num / den;
    let r = num - q * den;
    if r == 0 { q } else { q + 1 }
}

fn lin_fee(feerate: i64, weight: i64) -> i64 {
    if feerate < 0 || feerate > U32_MAX || weight <= 0 {
        return 0;
    }
    if !prod_ok(feerate, weight) {
        return 0;
    }
    ceil_div(feerate * weight, KW)
}

fn lin_feerate(fee_sat: i64, weight: i64) -> i64 {
    if fee_sat < 0 || weight <= 0 {
        return 0;
    }
    if !prod_ok(fee_sat, KW) {
        return U32_MAX;
    }
    let q = (fee_sat * KW) / weight;
    if q > U32_MAX { U32_MAX } else { q }
}

fn lin_bounded(est: i64) -> i64 {
    if est < 0 || est > U32_MAX {
        return 0;
    }
    if est < FLOOR { FLOOR } else { est }
}

fn rust_fee(feerate: u64, weight: u64) -> u64 {
    (feerate.wrapping_mul(weight).wrapping_add(999)) / 1000
}

fn selftest() -> i32 {
    if lin_fee(253, 440) != 112 {
        return 1;
    }
    if lin_fee(1, 1001) != 2 {
        return 2;
    }
    if lin_fee(4294967295, 2147483649) != 0 {
        return 3;
    }
    if rust_fee(253, 440) != 112 {
        return 4;
    }
    if lin_bounded(100) != 253 {
        return 5;
    }
    0
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: rust_lightning_feewgt selftest|fee r w|feerate f w|bounded e|rust-fee r w");
        std::process::exit(2);
    }
    match args[1].as_str() {
        "selftest" => {
            let rc = selftest();
            if rc != 0 {
                println!("FAIL {rc}");
                std::process::exit(1);
            }
            println!("PASS");
        }
        "fee" => println!("{}", lin_fee(args[2].parse().unwrap(), args[3].parse().unwrap())),
        "feerate" => println!("{}", lin_feerate(args[2].parse().unwrap(), args[3].parse().unwrap())),
        "bounded" => println!("{}", lin_bounded(args[2].parse().unwrap())),
        "rust-fee" => {
            let r: u64 = args[2].parse().unwrap();
            let w: u64 = args[3].parse().unwrap();
            println!("{}", rust_fee(r, w));
        }
        _ => std::process::exit(2),
    }
}
