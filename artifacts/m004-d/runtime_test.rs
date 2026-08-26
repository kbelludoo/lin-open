// runtime test for generated artifacts/m004-d using rlib
extern crate generated_m004d;

fn main() {
    // 1. AstModule + ParserModule + SemanticModule + EmitterModule pipeline
    let valid_fn = generated_m004d::compile_pipeline("calculateScore".to_string(), 42);
    assert_eq!(valid_fn, "pub fn calculateScore() {}");

    let valid_mod = generated_m004d::compile_module_pipeline("MathUtils".to_string(), 10);
    assert_eq!(valid_mod, "pub mod MathUtils {}");

    // Invalid lines (<= 0) should be rejected by SemanticModule
    let invalid_fn = generated_m004d::compile_pipeline("broken".to_string(), 0);
    assert_eq!(invalid_fn, "ERROR_INVALID_NODE");

    // Direct access to submodules
    let node = generated_m004d::AstModule::createNode(
        generated_m004d::AstModule::NodeKind::Function,
        "testDirect".to_string(),
        1,
    );
    assert_eq!(generated_m004d::SemanticModule::validateNode(node.clone()), true);
    assert_eq!(generated_m004d::EmitterModule::emitRustDeclaration(node), "pub fn testDirect() {}");

    println!("M004_D_ALL_TESTS_PASS");
}
