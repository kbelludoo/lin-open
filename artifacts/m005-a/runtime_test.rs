// runtime test for generated artifacts/m005-a using rlib
extern crate generated_m005a;

fn main() {
    // Verify reachable functionality computes accurately
    assert_eq!(generated_m005a::live_compute(12, 30), 42);
    assert_eq!(generated_m005a::ActiveMath::usedAdd(100, 200), 300);

    println!("M005_A_ALL_TESTS_PASS");
}
