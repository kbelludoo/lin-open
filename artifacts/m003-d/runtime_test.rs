// runtime test for generated artifacts/m003-d using rlib
extern crate generated_d;

fn main() {
    // 1. AstNode classification via match destructuring and guards
    let ident_node = generated_d::AstNode {
        kind: generated_d::AstKind::Ident,
        name: "myVar".to_string(),
        value: 0,
    };
    assert_eq!(generated_d::classify_ast_node(ident_node), "IDENT:myVar");

    let lit_node = generated_d::AstNode {
        kind: generated_d::AstKind::Literal,
        name: "".to_string(),
        value: 123,
    };
    assert_eq!(generated_d::classify_ast_node(lit_node), "LITERAL:123");

    let binop_pos = generated_d::AstNode {
        kind: generated_d::AstKind::BinaryOp,
        name: "+".to_string(),
        value: 10,
    };
    assert_eq!(generated_d::classify_ast_node(binop_pos), "BINOP_POS:+");

    let binop_zero = generated_d::AstNode {
        kind: generated_d::AstKind::BinaryOp,
        name: "-".to_string(),
        value: 0,
    };
    assert_eq!(generated_d::classify_ast_node(binop_zero), "BINOP:-");

    let match_node = generated_d::AstNode {
        kind: generated_d::AstKind::MatchBlock,
        name: "".to_string(),
        value: 0,
    };
    assert_eq!(generated_d::classify_ast_node(match_node), "MATCH");

    // 2. Type Unification via tuple match
    assert_eq!(generated_d::unify_types_with_match("int".to_string(), "int".to_string()), "int");
    assert_eq!(generated_d::unify_types_with_match("any".to_string(), "bool".to_string()), "bool");
    assert_eq!(generated_d::unify_types_with_match("str".to_string(), "any".to_string()), "str");
    assert_eq!(generated_d::unify_types_with_match("int".to_string(), "float".to_string()), "float");
    assert_eq!(generated_d::unify_types_with_match("float".to_string(), "int".to_string()), "float");
    assert_eq!(generated_d::unify_types_with_match("str".to_string(), "int".to_string()), "any");

    // 3. Param Type Inference via multi-pattern match
    assert_eq!(generated_d::infer_param_type_with_match("count".to_string()), "int");
    assert_eq!(generated_d::infer_param_type_with_match("name".to_string()), "str");
    assert_eq!(generated_d::infer_param_type_with_match("ok".to_string()), "bool");
    assert_eq!(generated_d::infer_param_type_with_match("items".to_string()), "list");
    assert_eq!(generated_d::infer_param_type_with_match("config".to_string()), "map");
    assert_eq!(generated_d::infer_param_type_with_match("handler".to_string()), "fn");
    assert_eq!(generated_d::infer_param_type_with_match("unknown".to_string()), "any");

    println!("M003_D_ALL_TESTS_PASS");
}
