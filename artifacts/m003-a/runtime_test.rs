// runtime test for generated artifacts/m003-a using rlib
extern crate generated;

fn main() {
    let some_val = generated::Option::Some(42);
    let none_val: generated::Option<i32> = generated::Option::None;
    
    assert_eq!(generated::unwrap_or(some_val.clone(), 0), 42);
    assert_eq!(generated::unwrap_or(none_val.clone(), 99), 99);
    assert_eq!(generated::is_some(some_val), true);
    assert_eq!(generated::is_some(none_val), false);
    
    println!("M003_A_ALL_TESTS_PASS");
}
