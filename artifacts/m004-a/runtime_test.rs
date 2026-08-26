// runtime test for generated artifacts/m004-a using rlib
extern crate generated_m004a;

fn main() {
    // 1. Direct use from module
    assert_eq!(generated_m004a::MathOps::add(10, 20), 30);
    assert_eq!(generated_m004a::MathOps::multiply(6, 7), 42);

    // 2. Re-exported symbols via use
    assert_eq!(generated_m004a::add(5, 15), 20);
    assert_eq!(generated_m004a::multiply(3, 4), 12);

    // 3. Composite function using imported symbols
    assert_eq!(generated_m004a::compute(2, 3), 11); // (2+3) + (2*3) = 5 + 6 = 11

    // 4. Qualified function call within body
    assert_eq!(generated_m004a::qualified_compute(4, 5), 20);

    println!("M004_A_ALL_TESTS_PASS");
}
