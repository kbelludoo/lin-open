//! LIN Core Library - Rust Implementation
//! 
//! This module implements the core components of the LIN language:
//! - Parser (LIA/LIN syntax)
//! - AST (Abstract Syntax Tree)
//! - IR (Intermediate Representation)
//! - Type Checker
//! - Semantic Hash
//! - Emitter (code generation for multiple targets)

use serde::{Deserialize, Serialize};
use std::fmt::Write;

/// LIN Header format
pub const LIN_HEADER: &str = "@LIN:L1c:0.2";
pub const LIA_HEADER: &str = "@LIN:L1c:0.2";

/// ============================================================================
/// AST Definitions
/// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Program {
    pub header: String,
    pub schema_flags: SchemaFlags,
    pub sigil_table: SigilTable,
    pub functions: Vec<Function>,
    pub exports: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SchemaFlags {
    pub schema_once: bool,
    pub lossy: bool,
    pub ops: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SigilTable {
    pub question: String,  // ? = if
    pub hash: String,      // # = for
    pub caret: String,     // ^ = ret
    pub colon: String,     // : = else
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Function {
    pub name: String,
    pub params: Vec<String>,
    pub body: String,
}

/// ============================================================================
/// Parser
/// ============================================================================

pub fn parse_lia(source: &str) -> Result<Program, String> {
    let lines: Vec<&str> = source.lines().collect();
    if lines.is_empty() {
        return Err("Empty source".to_string());
    }

    // Parse header
    let header = lines[0].trim();
    if !header.starts_with("@LIN:") && !header.starts_with("@LIA:") && !header.starts_with("@AIL:") {
        return Err(format!("Invalid header: {}", header));
    }

    // Parse second line with flags and sigils
    if lines.len() < 2 {
        return Err("Missing schema/sigil line".to_string());
    }

    let schema_line = lines[1].trim();
    let (schema_flags, sigil_table) = parse_schema_and_sigils(schema_line)?;

    // Parse functions and exports
    let mut functions = Vec::new();
    let mut exports = Vec::new();

    for line in lines.iter().skip(2) {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        if line.starts_with("!") {
            // Function definition
            functions.push(parse_function(line)?);
        } else if line.starts_with("=ex{") {
            // Export statement
            exports = parse_exports(line)?;
        }
    }

    Ok(Program {
        header: header.to_string(),
        schema_flags,
        sigil_table,
        functions,
        exports,
    })
}

fn parse_schema_and_sigils(line: &str) -> Result<(SchemaFlags, SigilTable), String> {
    let mut schema_once = false;
    let mut lossy = false;
    let mut ops = None;
    
    // Parse schema flags
    if line.contains("^schema_once") {
        schema_once = true;
    }
    if line.contains("^lossy=true") {
        lossy = true;
    }
    
    // Extract ops value
    if let Some(ops_start) = line.find("^ops=") {
        let ops_end = line[ops_start..].find(' ').unwrap_or(line.len() - ops_start);
        let ops_value = &line[ops_start + 5..ops_start + ops_end];
        ops = Some(ops_value.to_string());
    }

    // Parse sigil table ~G{?=if #=for ^=ret :else}
    let sigil_table = if let Some(start) = line.find("~G{") {
        if let Some(end) = line[start..].find('}') {
            let sigils = &line[start + 3..start + end];
            parse_sigils(sigils)?
        } else {
            return Err("Unclosed sigil table".to_string());
        }
    } else {
        // Default sigils
        SigilTable {
            question: "if".to_string(),
            hash: "for".to_string(),
            caret: "ret".to_string(),
            colon: "else".to_string(),
        }
    };

    Ok((SchemaFlags { schema_once, lossy, ops }, sigil_table))
}

fn parse_sigils(sigils: &str) -> Result<SigilTable, String> {
    let mut question = "if".to_string();
    let mut hash = "for".to_string();
    let mut caret = "ret".to_string();
    let mut colon = "else".to_string();

    for part in sigils.split_whitespace() {
        if part.starts_with("?=") {
            question = part[2..].to_string();
        } else if part.starts_with("#=") {
            hash = part[2..].to_string();
        } else if part.starts_with("^=") {
            caret = part[2..].to_string();
        } else if part.starts_with(":") {
            colon = part[1..].to_string();
        }
    }

    Ok(SigilTable { question, hash, caret, colon })
}

fn parse_function(line: &str) -> Result<Function, String> {
    // Format: !name(params){body}
    if !line.starts_with("!") {
        return Err("Function must start with !".to_string());
    }

    let rest = &line[1..];
    let paren_start = rest.find('(').ok_or("Missing ( in function")?;
    let paren_end = rest.find(')').ok_or("Missing ) in function")?;
    let brace_start = rest.find('{').ok_or("Missing { in function")?;
    
    // Find matching closing brace
    let mut depth = 1;
    let mut brace_end = None;
    for (i, c) in rest.chars().enumerate().skip(brace_start + 1) {
        if c == '{' {
            depth += 1;
        } else if c == '}' {
            depth -= 1;
            if depth == 0 {
                brace_end = Some(i);
                break;
            }
        }
    }
    let brace_end = brace_end.ok_or("Unclosed function body")?;

    let name = rest[..paren_start].trim().to_string();
    let params_str = &rest[paren_start + 1..paren_end];
    let params: Vec<String> = if params_str.trim().is_empty() {
        Vec::new()
    } else {
        params_str.split(',').map(|s| s.trim().to_string()).collect()
    };
    let body = rest[brace_start + 1..brace_end].to_string();

    Ok(Function { name, params, body })
}

fn parse_exports(line: &str) -> Result<Vec<String>, String> {
    // Format: =ex{name1,name2,...}
    if !line.starts_with("=ex{") {
        return Err("Invalid export statement".to_string());
    }
    
    let start = 4; // Skip "=ex{"
    let end = line.find('}').ok_or("Unclosed export")?;
    let content = &line[start..end];
    
    if content.trim().is_empty() {
        return Ok(Vec::new());
    }
    
    Ok(content.split(',').map(|s| s.trim().to_string()).collect())
}

/// ============================================================================
/// Type Checker (Basic)
/// ============================================================================

pub fn type_check(program: &Program) -> Result<(), String> {
    // Basic validation
    for func in &program.functions {
        if func.name.is_empty() {
            return Err("Function name cannot be empty".to_string());
        }
    }
    Ok(())
}

/// ============================================================================
/// Semantic Hash
/// ============================================================================

pub fn compute_semantic_hash(program: &Program) -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let mut hasher = DefaultHasher::new();
    program.header.hash(&mut hasher);
    for func in &program.functions {
        func.name.hash(&mut hasher);
        func.body.hash(&mut hasher);
    }
    format!("{:x}", hasher.finish())
}

/// ============================================================================
/// Emitter - Code Generation for Multiple Targets
/// ============================================================================

pub enum Target {
    JavaScript,
    TypeScript,
    Python,
    Rust,
    Go,
    C,
}

impl Target {
    pub fn from_str(s: &str) -> Result<Self, String> {
        match s.to_lowercase().as_str() {
            "js" | "javascript" => Ok(Target::JavaScript),
            "ts" | "typescript" => Ok(Target::TypeScript),
            "py" | "python" => Ok(Target::Python),
            "rs" | "rust" => Ok(Target::Rust),
            "go" => Ok(Target::Go),
            "c" => Ok(Target::C),
            _ => Err(format!("Unknown target: {}", s)),
        }
    }
}

pub fn emit_code(program: &Program, target: &Target) -> Result<String, String> {
    match target {
        Target::JavaScript => emit_javascript(program),
        Target::TypeScript => emit_typescript(program),
        Target::Python => emit_python(program),
        Target::Rust => emit_rust_target(program),
        Target::Go => emit_go(program),
        Target::C => emit_c(program),
    }
}

fn emit_javascript(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    // Add LIN header comment
    writeln!(output, "// Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "// Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    
    // Generate functions
    for func in &program.functions {
        let params = func.params.join(", ");
        writeln!(output, "function {}({}) {{", func.name, params).unwrap();
        
        // Simple body translation (placeholder - full implementation would parse the body)
        let body = translate_body_to_js(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "  {}", line).unwrap();
        }
        
        writeln!(output, "}}").unwrap();
        writeln!(output).unwrap();
    }
    
    // Generate exports
    if !program.exports.is_empty() {
        writeln!(output, "module.exports = {{").unwrap();
        for (i, exp) in program.exports.iter().enumerate() {
            let comma = if i < program.exports.len() - 1 { "," } else { "" };
            writeln!(output, "  {}{}", exp, comma).unwrap();
        }
        writeln!(output, "}};").unwrap();
    }
    
    Ok(output)
}

fn emit_typescript(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    writeln!(output, "// Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "// Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    
    for func in &program.functions {
        let params = func.params.join(", ");
        writeln!(output, "export function {}({}): any {{", func.name, params).unwrap();
        
        let body = translate_body_to_js(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "  {}", line).unwrap();
        }
        
        writeln!(output, "}}").unwrap();
        writeln!(output).unwrap();
    }
    
    Ok(output)
}

fn emit_python(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    writeln!(output, "# Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "# Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    
    for func in &program.functions {
        let params = func.params.join(", ");
        writeln!(output, "def {}({}):", func.name, params).unwrap();
        
        let body = translate_body_to_py(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "    {}", line).unwrap();
        }
        writeln!(output).unwrap();
    }
    
    if !program.exports.is_empty() {
        writeln!(output, "__all__ = [{}]", program.exports.iter()
            .map(|s| format!("\"{}\"", s))
            .collect::<Vec<_>>()
            .join(", ")).unwrap();
    }
    
    Ok(output)
}

fn emit_rust_target(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    writeln!(output, "// Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "// Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    
    for func in &program.functions {
        let params = func.params.iter()
            .map(|p| format!("{}: i64", p))
            .collect::<Vec<_>>()
            .join(", ");
        
        writeln!(output, "pub fn {}({}) -> i64 {{", func.name, params).unwrap();
        
        let body = translate_body_to_rust(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "    {}", line).unwrap();
        }
        
        writeln!(output, "}}").unwrap();
        writeln!(output).unwrap();
    }
    
    Ok(output)
}

fn emit_go(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    writeln!(output, "// Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "// Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    writeln!(output, "package main").unwrap();
    writeln!(output).unwrap();
    
    for func in &program.functions {
        let params = func.params.iter()
            .map(|p| format!("{} int64", p))
            .collect::<Vec<_>>()
            .join(", ");
        
        writeln!(output, "func {}({}) int64 {{", func.name, params).unwrap();
        
        let body = translate_body_to_go(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "    {}", line).unwrap();
        }
        
        writeln!(output, "}}").unwrap();
        writeln!(output).unwrap();
    }
    
    Ok(output)
}

fn emit_c(program: &Program) -> Result<String, String> {
    let mut output = String::new();
    
    writeln!(output, "// Generated by LIN Compiler (Rust)").unwrap();
    writeln!(output, "// Source: {}", program.header).unwrap();
    writeln!(output).unwrap();
    
    for func in &program.functions {
        let params = func.params.iter()
            .map(|p| format!("long {}", p))
            .collect::<Vec<_>>()
            .join(", ");
        
        writeln!(output, "long {}({}) {{", func.name, params).unwrap();
        
        let body = translate_body_to_c(&func.body, &program.sigil_table);
        for line in body.lines() {
            writeln!(output, "    {}", line).unwrap();
        }
        
        writeln!(output, "}}").unwrap();
        writeln!(output).unwrap();
    }
    
    Ok(output)
}

// Simple body translation helpers (placeholder implementations)
fn translate_body_to_js(body: &str, _sigils: &SigilTable) -> String {
    // In a full implementation, this would properly parse and translate
    // For now, do basic sigil replacement
    body.replace("^return ", "return ")
        .replace("?(", "if (")
        .replace("#(", "for (")
        .replace("){", ") {")
        .replace(";^", "; return ")
}

fn translate_body_to_py(body: &str, _sigils: &SigilTable) -> String {
    body.replace("^return ", "return ")
        .replace("?(", "if ")
        .replace("#(", "for ")
        .replace("){", ":")
        .replace(";^", "; return ")
}

fn translate_body_to_rust(body: &str, _sigils: &SigilTable) -> String {
    body.replace("^return ", "return ")
        .replace("?(", "if ")
        .replace("#(", "for ")
        .replace("){", ") {")
        .replace(";^", "; return ")
}

fn translate_body_to_go(body: &str, _sigils: &SigilTable) -> String {
    body.replace("^return ", "return ")
        .replace("?(", "if ")
        .replace("#(", "for ")
        .replace("){", ") {")
        .replace(";^", "; return ")
}

fn translate_body_to_c(body: &str, _sigils: &SigilTable) -> String {
    body.replace("^return ", "return ")
        .replace("?(", "if ")
        .replace("#(", "for ")
        .replace("){", ") {")
        .replace(";^", "; return ")
}

/// ============================================================================
/// Tests
/// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_program() {
        let source = "@LIN:L1c:0.2
^schema_once ^lossy=true ^ops=test
~G{?=if #=for ^=ret :else}
!safeCompare(a,b){A=String(a);B=String(b);^A==B}
=ex{safeCompare}";

        let program = parse_lia(source).unwrap();
        assert_eq!(program.header, "@LIN:L1c:0.2");
        assert!(program.schema_flags.schema_once);
        assert!(program.schema_flags.lossy);
        assert_eq!(program.functions.len(), 1);
        assert_eq!(program.functions[0].name, "safeCompare");
        assert_eq!(program.exports, vec!["safeCompare"]);
    }

    #[test]
    fn test_type_check() {
        let source = "@LIN:L1c:0.2
^schema_once
!foo(x){^x+1}
=ex{foo}";

        let program = parse_lia(source).unwrap();
        assert!(type_check(&program).is_ok());
    }

    #[test]
    fn test_emit_javascript() {
        let source = "@LIN:L1c:0.2
^schema_once
!add(a,b){^a+b}
=ex{add}";

        let program = parse_lia(source).unwrap();
        let js = emit_code(&program, &Target::JavaScript).unwrap();
        assert!(js.contains("function add(a, b)"));
        assert!(js.contains("module.exports"));
    }

    #[test]
    fn test_emit_python() {
        let source = "@LIN:L1c:0.2
^schema_once
!add(a,b){^a+b}
=ex{add}";

        let program = parse_lia(source).unwrap();
        let py = emit_code(&program, &Target::Python).unwrap();
        assert!(py.contains("def add(a, b):"));
        assert!(py.contains("__all__"));
    }

    #[test]
    fn test_emit_rust() {
        let source = "@LIN:L1c:0.2
^schema_once
!add(a,b){^a+b}
=ex{add}";

        let program = parse_lia(source).unwrap();
        let rs = emit_code(&program, &Target::Rust).unwrap();
        assert!(rs.contains("pub fn add(a: i64, b: i64) -> i64"));
    }

    #[test]
    fn test_semantic_hash() {
        let source = "@LIN:L1c:0.2
^schema_once
!foo(x){^x+1}
=ex{foo}";

        let program = parse_lia(source).unwrap();
        let hash1 = compute_semantic_hash(&program);
        let hash2 = compute_semantic_hash(&program);
        assert_eq!(hash1, hash2); // Same program = same hash
    }
}
