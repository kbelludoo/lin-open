// runtime test for generated artifacts/m003-c using rlib
extern crate generated_c;

fn main() {
    // Tuple destructuring tests
    assert_eq!(generated_c::sum_tuple((0, 42)), 42);
    assert_eq!(generated_c::sum_tuple((100, 0)), 100);
    assert_eq!(generated_c::sum_tuple((15, 25)), 40);

    // Struct destructuring tests
    let origin = generated_c::Point { x: 0, y: 0 };
    let y_axis = generated_c::Point { x: 0, y: 15 };
    let x_axis = generated_c::Point { x: 20, y: 0 };
    let diag = generated_c::Point { x: 7, y: 7 };
    let quad = generated_c::Point { x: 3, y: 4 };

    assert_eq!(generated_c::eval_point(origin), "ORIGIN");
    assert_eq!(generated_c::eval_point(y_axis), "Y_AXIS");
    assert_eq!(generated_c::eval_point(x_axis), "X_AXIS");
    assert_eq!(generated_c::eval_point(diag), "DIAGONAL");
    assert_eq!(generated_c::eval_point(quad), "QUADRANT");

    println!("M003_C_ALL_TESTS_PASS");
}
