// runtime test for generated artifacts/m003-b using rlib
extern crate generated_b;

fn main() {
    // Literal multi-match test
    assert_eq!(generated_b::classify_status(200), "SUCCESS");
    assert_eq!(generated_b::classify_status(201), "SUCCESS");
    assert_eq!(generated_b::classify_status(404), "CLIENT_ERROR");
    assert_eq!(generated_b::classify_status(503), "SERVER_ERROR");
    assert_eq!(generated_b::classify_status(999), "UNKNOWN");

    // Guard test
    assert_eq!(generated_b::evaluate_score(95), "EXCELLENT");
    assert_eq!(generated_b::evaluate_score(75), "GOOD");
    assert_eq!(generated_b::evaluate_score(55), "PASS");
    assert_eq!(generated_b::evaluate_score(40), "FAIL");

    // Boolean match test
    assert_eq!(generated_b::match_bool(true), 1);
    assert_eq!(generated_b::match_bool(false), 0);

    println!("M003_B_ALL_TESTS_PASS");
}
