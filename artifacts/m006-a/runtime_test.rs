extern crate m006a_gate;

fn main() {
    let div = m006a_gate::run_tests();
    assert_eq!(div, 5, "safeDiv(10,2) should be 5");
    assert_eq!(m006a_gate::safe_div(10, 2), 5);
    assert_eq!(m006a_gate::classify(1), 10);
    assert_eq!(m006a_gate::classify(2), 20);
    assert_eq!(m006a_gate::classify(9), 0, "wildcard arm should match");
    println!("M006_A_ALL_TESTS_PASS");
}
