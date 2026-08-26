// runtime test for generated artifacts/m004-b using rlib
extern crate generated_m004b;

fn main() {
    // 1. Direct module call from bundled dependency
    assert_eq!(generated_m004b::math_helper::square(4), 16);
    assert_eq!(generated_m004b::math_helper::cube(3), 27);

    // 2. Imported symbols from dependency
    assert_eq!(generated_m004b::square(5), 25);
    assert_eq!(generated_m004b::cube(2), 8);

    // 3. Composite inter-file function
    // calculatePowerSum(3) = 3^2 + 3^3 = 9 + 27 = 36
    assert_eq!(generated_m004b::calculate_power_sum(3), 36);

    // 4. Qualified function call
    assert_eq!(generated_m004b::qualified_square(10), 100);

    println!("M004_B_ALL_TESTS_PASS");
}
