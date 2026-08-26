// runtime test for generated artifacts/real-world-001 using rlib
extern crate realworld_calc;

fn main() {
    // 1. Addition: 10 + 20 = 30
    assert_eq!(realworld_calc::run_add(10, 20), "RESULT:30");

    // 2. Multiplication: 6 * 7 = 42
    assert_eq!(realworld_calc::run_mul(6, 7), "RESULT:42");

    // 3. Subtraction: 100 - 35 = 65
    assert_eq!(realworld_calc::run_sub(100, 35), "RESULT:65");

    // 4. Division: 84 / 2 = 42
    assert_eq!(realworld_calc::run_div(84, 2), "RESULT:42");

    // 5. Division by zero: should return error string
    assert_eq!(realworld_calc::run_div(10, 0), "ERROR:DIV_BY_ZERO");

    println!("REAL_WORLD_CALC_ALL_TESTS_PASS");
}
