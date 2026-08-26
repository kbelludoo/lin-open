//! LIN CLI - Command Line Interface
//! 
//! Provides CLI commands for:
//! - parse: Parse LIA/LIN source to AST
//! - check: Type checking and validation
//! - hash: Compute semantic hash
//! - emit: Compile to target languages (js, ts, py, rs, go, c)

use lin_core::{parse_lia, type_check, compute_semantic_hash, emit_code, Target};
use std::env;
use std::fs;

fn print_usage() {
    eprintln!("LIN Compiler (Rust implementation)");
    eprintln!();
    eprintln!("Usage: lin_cli <command> [options]");
    eprintln!();
    eprintln!("Commands:");
    eprintln!("  parse <file>                 Parse LIA/LIN file and print AST");
    eprintln!("  check <file>                 Run type checker");
    eprintln!("  hash <file>                  Compute semantic hash");
    eprintln!("  emit <file> --target <lang>  Compile to target language");
    eprintln!("                               Targets: js, ts, py, rs, go, c");
    eprintln!("  help                         Show this help message");
}

fn main() {
    let args: Vec<String> = env::args().collect();
    
    if args.len() < 2 {
        print_usage();
        std::process::exit(1);
    }

    let command = &args[1];
    
    match command.as_str() {
        "parse" => {
            if args.len() < 3 {
                eprintln!("Error: Missing file argument");
                print_usage();
                std::process::exit(1);
            }
            cmd_parse(&args[2]);
        }
        "check" => {
            if args.len() < 3 {
                eprintln!("Error: Missing file argument");
                print_usage();
                std::process::exit(1);
            }
            cmd_check(&args[2]);
        }
        "hash" => {
            if args.len() < 3 {
                eprintln!("Error: Missing file argument");
                print_usage();
                std::process::exit(1);
            }
            cmd_hash(&args[2]);
        }
        "emit" => {
            if args.len() < 5 {
                eprintln!("Error: Missing arguments");
                eprintln!("Usage: lin_cli emit <file> --target <lang>");
                print_usage();
                std::process::exit(1);
            }
            let file = &args[2];
            let target_str = if args[3] == "--target" { &args[4] } else { &args[3] };
            cmd_emit(file, target_str);
        }
        "help" | "--help" | "-h" => {
            print_usage();
        }
        _ => {
            eprintln!("Unknown command: {}", command);
            print_usage();
            std::process::exit(1);
        }
    }
}

fn cmd_parse(filepath: &str) {
    let source = match fs::read_to_string(filepath) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Error reading file {}: {}", filepath, e);
            std::process::exit(1);
        }
    };

    match parse_lia(&source) {
        Ok(program) => {
            println!("{}", serde_json::to_string_pretty(&program).unwrap());
        }
        Err(e) => {
            eprintln!("Parse error: {}", e);
            std::process::exit(1);
        }
    }
}

fn cmd_check(filepath: &str) {
    let source = match fs::read_to_string(filepath) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Error reading file {}: {}", filepath, e);
            std::process::exit(1);
        }
    };

    match parse_lia(&source) {
        Ok(program) => {
            match type_check(&program) {
                Ok(_) => {
                    println!("✓ Type check passed");
                }
                Err(e) => {
                    eprintln!("Type check error: {}", e);
                    std::process::exit(1);
                }
            }
        }
        Err(e) => {
            eprintln!("Parse error: {}", e);
            std::process::exit(1);
        }
    }
}

fn cmd_hash(filepath: &str) {
    let source = match fs::read_to_string(filepath) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Error reading file {}: {}", filepath, e);
            std::process::exit(1);
        }
    };

    match parse_lia(&source) {
        Ok(program) => {
            let hash = compute_semantic_hash(&program);
            println!("{}", hash);
        }
        Err(e) => {
            eprintln!("Parse error: {}", e);
            std::process::exit(1);
        }
    }
}

fn cmd_emit(filepath: &str, target_str: &str) {
    let source = match fs::read_to_string(filepath) {
        Ok(content) => content,
        Err(e) => {
            eprintln!("Error reading file {}: {}", filepath, e);
            std::process::exit(1);
        }
    };

    let target = match Target::from_str(target_str) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("Error: {}", e);
            eprintln!("Available targets: js, ts, py, rs, go, c");
            std::process::exit(1);
        }
    };

    match parse_lia(&source) {
        Ok(program) => {
            match emit_code(&program, &target) {
                Ok(code) => {
                    println!("{}", code);
                }
                Err(e) => {
                    eprintln!("Emission error: {}", e);
                    std::process::exit(1);
                }
            }
        }
        Err(e) => {
            eprintln!("Parse error: {}", e);
            std::process::exit(1);
        }
    }
}
