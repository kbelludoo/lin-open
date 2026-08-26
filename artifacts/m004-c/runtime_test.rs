// runtime test for generated artifacts/m004-c using rlib
extern crate generated_m004c;

fn main() {
    // 1. Direct call inside module boundary
    assert_eq!(generated_m004c::Storage::readEntry("token".to_string()), "ENTRY:token");
    assert_eq!(generated_m004c::Storage::writeEntry("user".to_string(), "k".to_string()), "STORED:user=k");

    // 2. Caller consuming granted capabilities
    assert_eq!(generated_m004c::query_data("session_id".to_string()), "ENTRY:session_id");
    assert_eq!(generated_m004c::save_data("mode".to_string(), "strict".to_string()), "STORED:mode=strict");

    println!("M004_C_ALL_TESTS_PASS");
}
