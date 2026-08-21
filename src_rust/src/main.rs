use std::collections::HashMap;
use std::env;
use std::fs;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct LinFunction {
    pub name: String,
    pub params: Vec<String>,
    pub body: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct LinModule {
    pub header: String,
    pub ops: String,
    pub grammar: String,
    pub functions: Vec<LinFunction>,
    pub exports: Vec<String>,
}

pub fn split_aware(input: &str, delimiter: char) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth_paren = 0;
    let mut depth_brace = 0;
    let mut depth_bracket = 0;
    let mut in_quote: Option<char> = None;
    let mut escape = false;
    let mut start = 0;

    let chars: Vec<char> = input.chars().collect();
    let len = chars.len();

    for i in 0..len {
        let c = chars[i];

        if escape {
            escape = false;
            continue;
        }

        if c == '\\' {
            escape = true;
            continue;
        }

        if let Some(q) = in_quote {
            if c == q {
                in_quote = None;
            }
            continue;
        } else if c == '\'' || c == '"' {
            in_quote = Some(c);
            continue;
        }

        match c {
            '(' => depth_paren += 1,
            ')' => if depth_paren > 0 { depth_paren -= 1; },
            '{' => depth_brace += 1,
            '}' => if depth_brace > 0 { depth_brace -= 1; },
            '[' => depth_bracket += 1,
            ']' => if depth_bracket > 0 { depth_bracket -= 1; },
            _ => {}
        }

        if c == delimiter && depth_paren == 0 && depth_brace == 0 && depth_bracket == 0 && in_quote.is_none() {
            let part: String = chars[start..i].iter().collect();
            let trimmed = part.trim().to_string();
            if !trimmed.is_empty() {
                parts.push(trimmed);
            }
            start = i + 1;
        }
    }

    if start < len {
        let part: String = chars[start..len].iter().collect();
        let trimmed = part.trim().to_string();
        if !trimmed.is_empty() {
            parts.push(trimmed);
        }
    }

    parts
}

pub fn parse_lin_source(content: &str) -> LinModule {
    let mut header = String::new();
    let mut ops = String::new();
    let mut grammar = String::new();
    let mut functions = Vec::new();
    let mut exports = Vec::new();

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("@LIN:") || trimmed.starts_with("@RULEL:") {
            header = trimmed.to_string();
        } else if trimmed.starts_with('^') {
            ops = trimmed.to_string();
        } else if trimmed.starts_with("~G") {
            grammar = trimmed.to_string();
        } else if trimmed.starts_with('!') {
            if let (Some(open_paren), Some(close_paren), Some(open_brace), Some(close_brace)) = 
                (trimmed.find('('), trimmed.find(')'), trimmed.find('{'), trimmed.rfind('}')) 
            {
                if open_paren > 1 && close_paren > open_paren && open_brace > close_paren && close_brace > open_brace {
                    let fn_name = trimmed[1..open_paren].trim().to_string();
                    let params_str = trimmed[open_paren + 1..close_paren].trim();
                    let params = split_aware(params_str, ',');
                    let body = trimmed[open_brace + 1..close_brace].trim().to_string();
                    functions.push(LinFunction { name: fn_name, params, body });
                }
            }
        } else if trimmed.starts_with("=ex{") && trimmed.ends_with('}') {
            let inner = &trimmed[4..trimmed.len() - 1];
            exports = split_aware(inner, ',');
        }
    }

    LinModule { header, ops, grammar, functions, exports }
}

pub struct Scope {
    pub vars: HashMap<String, Value>,
}

impl Scope {
    pub fn new() -> Self {
        Scope { vars: HashMap::new() }
    }
}

// JS ToNumber: returns None when result would be NaN (non-numeric string, array, object)
fn to_js_number(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Null => Some(0.0),
        Value::String(s) => {
            let t = s.trim();
            if t.is_empty() { return Some(0.0); }
            t.parse::<f64>().ok()
        },
        // Single-element array coerces like its sole element; empty = 0; multi = NaN
        Value::Array(arr) => {
            if arr.is_empty() { Some(0.0) }
            else if arr.len() == 1 { to_js_number(&arr[0]) }
            else { None }
        },
        Value::Object(_) => None,
    }
}

fn make_number(f: f64) -> Value {
    if f.is_nan() || f.is_infinite() { return Value::Null; }
    if f.fract() == 0.0 && f >= (i64::MIN as f64) && f <= (i64::MAX as f64) {
        Value::from(f as i64)
    } else if let Some(n) = serde_json::Number::from_f64(f) {
        Value::Number(n)
    } else {
        Value::Null
    }
}

// JS AbstractRelationalComparison: string vs string -> lexicographic; else numeric; NaN -> false
fn js_rel_lt(a: &Value, b: &Value) -> bool {
    if let (Value::String(sa), Value::String(sb)) = (a, b) {
        return sa.as_str() < sb.as_str();
    }
    match (to_js_number(a), to_js_number(b)) {
        (Some(na), Some(nb)) => na < nb,
        _ => false, // NaN comparison = false
    }
}

// JS + operator: toPrimitive then either string-concat or numeric add
fn val_to_primitive_string(v: &Value) -> Option<String> {
    match v {
        Value::String(s) => Some(s.clone()),
        Value::Array(arr) => {
            let parts: Vec<String> = arr.iter().map(|item| match item {
                Value::String(s) => s.clone(),
                Value::Null => String::new(),
                other => other.to_string(),
            }).collect();
            Some(parts.join(","))
        },
        Value::Object(_) => Some("[object Object]".to_string()),
        _ => None,
    }
}

fn js_add(v1: Value, v2: Value) -> Value {
    // If either side toPrimitive gives a string, concatenate
    let ps1 = val_to_primitive_string(&v1);
    let ps2 = val_to_primitive_string(&v2);
    if ps1.is_some() || ps2.is_some() {
        let s1 = ps1.unwrap_or_else(|| match &v1 {
            Value::Bool(b) => b.to_string(),
            Value::Number(n) => n.to_string(),
            Value::Null => String::new(),
            _ => v1.to_string(),
        });
        let s2 = ps2.unwrap_or_else(|| match &v2 {
            Value::Bool(b) => b.to_string(),
            Value::Number(n) => n.to_string(),
            Value::Null => String::new(),
            _ => v2.to_string(),
        });
        return Value::String(format!("{}{}", s1, s2));
    }
    match (to_js_number(&v1), to_js_number(&v2)) {
        (Some(a), Some(b)) => make_number(a + b),
        _ => Value::Null,
    }
}

pub fn eval_expr(expr: &str, scope: &mut Scope, module: &LinModule) -> Value {
    let mut s = expr.trim();
    if s.is_empty() { return Value::Null; }

    while s.starts_with('(') && s.ends_with(')') {
        let mut depth = 0;
        let mut fully_enclosed = true;
        for (idx, ch) in s.chars().enumerate() {
            if ch == '(' { depth += 1; }
            else if ch == ')' {
                depth -= 1;
                if depth == 0 && idx < s.len() - 1 {
                    fully_enclosed = false;
                    break;
                }
            }
        }
        if fully_enclosed && depth == 0 {
            s = s[1..s.len() - 1].trim();
        } else {
            break;
        }
    }

    if s == "true" { return Value::Bool(true); }
    if s == "false" { return Value::Bool(false); }
    if s == "null" || s == "undefined" { return Value::Null; }

    if s.starts_with('!') && !s.starts_with("!=") {
        let inner_val = eval_expr(&s[1..], scope, module);
        return Value::Bool(!is_truthy(&inner_val));
    }

    // String literal: only match if it's a properly enclosed literal
    // (no unescaped inner quotes of the same type)
    if s.len() >= 2 {
        let q = s.chars().next().unwrap();
        if (q == '\'' || q == '"') && s.ends_with(q) {
            // Verify no unescaped inner quote of same type
            let inner = &s[1..s.len()-1];
            let mut escape = false;
            let mut valid = true;
            for c in inner.chars() {
                if escape { escape = false; continue; }
                if c == '\\' { escape = true; continue; }
                if c == q { valid = false; break; }
            }
            if valid {
                return Value::String(inner.to_string());
            }
        }
    }

    if let Ok(n) = s.parse::<i64>() {
        return Value::from(n);
    }
    if let Ok(f) = s.parse::<f64>() {
        if let Some(v) = serde_json::Number::from_f64(f) {
            return Value::Number(v);
        }
    }

    if s.starts_with('[') && s.ends_with(']') {
        let inner = &s[1..s.len() - 1].trim();
        if inner.is_empty() { return Value::Array(Vec::new()); }
        let items: Vec<Value> = split_aware(inner, ',')
            .iter()
            .map(|item| eval_expr(item, scope, module))
            .collect();
        return Value::Array(items);
    }

    if s == "{}" {
        return Value::Object(serde_json::Map::new());
    }

    // 0. Curto-Circuito Lógico (&&, ||) com retorno do valor exato
    if let Some(pos) = find_binary_op(s, "||") {
        let v1 = eval_expr(&s[..pos], scope, module);
        if is_truthy(&v1) { return v1; }
        return eval_expr(&s[pos + 2..], scope, module);
    }
    if let Some(pos) = find_binary_op(s, "&&") {
        let v1 = eval_expr(&s[..pos], scope, module);
        if !is_truthy(&v1) { return v1; }
        return eval_expr(&s[pos + 2..], scope, module);
    }

    // 1. Comparações (==, !=, <=, >=, <, >) com coerção de tipos
    if let Some(pos) = find_binary_op(s, "==") {
        let v1 = eval_expr(&s[..pos], scope, module);
        let v2 = eval_expr(&s[pos + 2..], scope, module);
        return Value::Bool(js_equals(&v1, &v2));
    }
    if let Some(pos) = find_binary_op(s, "!=") {
        let v1 = eval_expr(&s[..pos], scope, module);
        let v2 = eval_expr(&s[pos + 2..], scope, module);
        return Value::Bool(!js_equals(&v1, &v2));
    }
    if let Some(pos) = find_binary_op(s, "<=") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 2..], scope, module);
        return Value::Bool(!js_rel_lt(&rv, &lv) && js_rel_lt(&lv, &rv) || lv == rv || {
            // JS <=: !(rv < lv) but if either is NaN, false
            match (to_js_number(&lv), to_js_number(&rv)) {
                (Some(a), Some(b)) => a <= b,
                _ => if let (Value::String(sa), Value::String(sb)) = (&lv, &rv) { sa <= sb } else { false },
            }
        });
    }
    if let Some(pos) = find_binary_op(s, ">=") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 2..], scope, module);
        return Value::Bool(match (to_js_number(&lv), to_js_number(&rv)) {
            (Some(a), Some(b)) => a >= b,
            _ => if let (Value::String(sa), Value::String(sb)) = (&lv, &rv) { sa.as_str() >= sb.as_str() } else { false },
        });
    }
    if let Some(pos) = find_binary_op(s, "<") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        return Value::Bool(js_rel_lt(&lv, &rv));
    }
    if let Some(pos) = find_binary_op(s, ">") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        return Value::Bool(js_rel_lt(&rv, &lv));
    }

    // 2. Adição (+): JS semantics via js_add (string-concat or numeric, NaN->null)
    if let Some(pos) = find_binary_op(s, "+") {
        let v1 = eval_expr(&s[..pos], scope, module);
        let v2 = eval_expr(&s[pos + 1..], scope, module);
        return js_add(v1, v2);
    }

    // 3. Subtração (-): NaN-aware
    if let Some(pos) = find_binary_op(s, "-") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        match (to_js_number(&lv), to_js_number(&rv)) {
            (Some(a), Some(b)) => return make_number(a - b),
            _ => return Value::Null,
        }
    }
    if let Some(pos) = find_binary_op(s, "*") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        match (to_js_number(&lv), to_js_number(&rv)) {
            (Some(a), Some(b)) => return make_number(a * b),
            _ => return Value::Null,
        }
    }
    if let Some(pos) = find_binary_op(s, "/") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        match (to_js_number(&lv), to_js_number(&rv)) {
            (Some(a), Some(b)) => {
                if b == 0.0 { return Value::Null; }
                return make_number(a / b);
            },
            _ => return Value::Null,
        }
    }
    if let Some(pos) = find_binary_op(s, "%") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        match (to_js_number(&lv), to_js_number(&rv)) {
            (Some(a), Some(b)) => {
                if b == 0.0 { return Value::Null; }
                return make_number(a % b);
            },
            _ => return Value::Null,
        }
    }

    // Dynamic Indexing: arr[0]
    if s.ends_with(']') {
        let mut depth = 0;
        let mut open_idx = None;
        let bytes = s.as_bytes();
        for i in (0..bytes.len()).rev() {
            if bytes[i] == b']' { depth += 1; }
            else if bytes[i] == b'[' {
                depth -= 1;
                if depth == 0 {
                    open_idx = Some(i);
                    break;
                }
            }
        }
        if let Some(open_br) = open_idx {
            if open_br > 0 {
                let target_val = eval_expr(&s[..open_br], scope, module);
                let key_val = eval_expr(&s[open_br + 1..s.len() - 1], scope, module);
                match target_val {
                    Value::Array(arr) => {
                        if let Some(idx) = key_val.as_i64() {
                            if idx >= 0 && (idx as usize) < arr.len() {
                                return arr[idx as usize].clone();
                            }
                        }
                        return Value::Null;
                    },
                    Value::Object(map) => {
                        let k = match key_val {
                            Value::String(st) => st,
                            _ => key_val.to_string(),
                        };
                        return map.get(&k).cloned().unwrap_or(Value::Null);
                    },
                    _ => return Value::Null,
                }
            }
        }
    }

    // Dot property
    if let Some((target_expr, prop)) = s.split_once('.') {
        let target_val = eval_expr(target_expr, scope, module);
        if prop == "length" {
            match target_val {
                Value::Array(arr) => return Value::from(arr.len() as i64),
                Value::String(str_val) => return Value::from(str_val.len() as i64),
                _ => return Value::from(0),
            }
        }
        if let Value::Object(map) = target_val {
            return map.get(prop).cloned().unwrap_or(Value::Null);
        }
        return Value::Null;
    }

    if let Some(val) = scope.vars.get(s) {
        return val.clone();
    }

    Value::String(s.to_string())
}

fn js_equals(v1: &Value, v2: &Value) -> bool {
    if v1 == v2 { return true; }
    if let (Some(n1), Some(n2)) = (to_js_number(v1), to_js_number(v2)) {
        return n1 == n2;
    }
    false
}

fn is_truthy(val: &Value) -> bool {
    match val {
        Value::Bool(b) => *b,
        Value::Null => false,
        Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(_) => true,
    }
}

fn find_binary_op(s: &str, op: &str) -> Option<usize> {
    let mut depth_paren = 0;
    let mut depth_brace = 0;
    let mut depth_bracket = 0;
    let mut in_quote: Option<char> = None;
    let mut escape = false;

    let chars: Vec<char> = s.chars().collect();
    let op_chars: Vec<char> = op.chars().collect();
    let len = chars.len();
    let op_len = op_chars.len();

    for i in (0..len).rev() {
        let c = chars[i];

        if escape {
            escape = false;
            continue;
        }

        if c == '\\' {
            escape = true;
            continue;
        }

        if let Some(q) = in_quote {
            if c == q { in_quote = None; }
            continue;
        } else if c == '\'' || c == '"' {
            in_quote = Some(c);
            continue;
        }

        match c {
            ')' => depth_paren += 1,
            '(' => if depth_paren > 0 { depth_paren -= 1; },
            '}' => depth_brace += 1,
            '{' => if depth_brace > 0 { depth_brace -= 1; },
            ']' => depth_bracket += 1,
            '[' => if depth_bracket > 0 { depth_bracket -= 1; },
            _ => {}
        }

        if depth_paren == 0 && depth_brace == 0 && depth_bracket == 0 && in_quote.is_none() && i + op_len <= len {
            if chars[i..i + op_len] == op_chars[..] {
                if op == "<" && i + 1 < len && chars[i + 1] == '=' { continue; }
                if op == ">" && i + 1 < len && chars[i + 1] == '=' { continue; }
                if op == "=" && (i > 0 && chars[i - 1] == '=' || i + 1 < len && chars[i + 1] == '=') { continue; }
                if op == "!" && i + 1 < len && chars[i + 1] == '=' { continue; }

                // Skip unary - and + (when preceded by an operator, open bracket, or start)
                if op == "-" || op == "+" {
                    let prev_non_ws = (0..i).rev().find(|&j| !chars[j].is_whitespace());
                    let is_unary = match prev_non_ws {
                        None => true, // start of expression
                        Some(j) => "+-*/%<>=!&|([{,;".contains(chars[j]),
                    };
                    if is_unary { continue; }
                }

                return Some(i);
            }
        }
    }
    None
}

pub fn execute_statement_block(stmts: &[String], scope: &mut Scope, module: &LinModule) -> Result<Option<Value>, String> {
    for stmt in stmts {
        if stmt.starts_with('^') {
            let ret_expr = &stmt[1..];
            return Ok(Some(eval_expr(ret_expr, scope, module)));
        }

        if stmt.starts_with("#(") {
            let chars: Vec<char> = stmt.chars().collect();
            let mut depth_p = 0;
            let mut loop_hdr_end = None;
            for (idx, &c) in chars.iter().enumerate() {
                if c == '(' { depth_p += 1; }
                else if c == ')' {
                    depth_p -= 1;
                    if depth_p == 0 {
                        loop_hdr_end = Some(idx);
                        break;
                    }
                }
            }

            if let Some(loop_end) = loop_hdr_end {
                let loop_header: String = chars[2..loop_end].iter().collect();
                let loop_parts = split_aware(&loop_header, ';');
                if loop_parts.len() == 3 {
                    let init_expr = &loop_parts[0];
                    let cond_expr = &loop_parts[1];
                    let step_expr = &loop_parts[2];

                    if let Some((v, val)) = init_expr.split_once('=') {
                        let initial_val = eval_expr(val, scope, module);
                        scope.vars.insert(v.trim().to_string(), initial_val);
                    }

                    if let (Some(body_start), Some(body_end)) = (stmt.find('{'), stmt.rfind('}')) {
                        let inner_stmts = split_aware(&stmt[body_start + 1..body_end], ';');

                        while is_truthy(&eval_expr(cond_expr, scope, module)) {
                            if let Some(val) = execute_statement_block(&inner_stmts, scope, module)? {
                                return Ok(Some(val));
                            }

                            if step_expr.ends_with("++") {
                                let v = &step_expr[..step_expr.len() - 2].trim();
                                let cur = scope.vars.get(*v).and_then(|val| val.as_i64()).unwrap_or(0);
                                scope.vars.insert(v.to_string(), Value::from(cur + 1));
                            } else if let Some((v, expr)) = step_expr.split_once('=') {
                                let val = eval_expr(expr, scope, module);
                                scope.vars.insert(v.trim().to_string(), val);
                            }
                        }
                    }
                }
                continue;
            }
        }

        if let Some((var_name, expr)) = stmt.split_once('=') {
            let val = eval_expr(expr, scope, module);
            scope.vars.insert(var_name.trim().to_string(), val);
        }
    }

    Ok(None)
}

pub fn execute_generic_lin_function(func: &LinFunction, args: &[Value], module: &LinModule) -> Result<Value, String> {
    let mut scope = Scope::new();

    for (i, param_name) in func.params.iter().enumerate() {
        let val = args.get(i).cloned().unwrap_or(Value::Null);
        scope.vars.insert(param_name.clone(), val);
    }

    let stmts = split_aware(&func.body, ';');
    let result = execute_statement_block(&stmts, &mut scope, module)?;

    Ok(result.unwrap_or(Value::Null))
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() >= 4 && args[1] == "call" {
        let file_path = &args[2];
        let fn_name = &args[3];
        let args_json = if args.len() > 4 { &args[4] } else { "[]" };

        let content = fs::read_to_string(file_path).unwrap_or_else(|e| {
            eprintln!("{{\"ok\": false, \"error\": \"Failed to read file: {}\"}}", e);
            std::process::exit(1);
        });

        let module = parse_lin_source(&content);
        let parsed_args: Vec<Value> = serde_json::from_str(args_json).unwrap_or_default();

        let func = module.functions.iter().find(|f| f.name == *fn_name)
            .ok_or_else(|| format!("Function '{}' not found in LIN module", fn_name));

        match func {
            Ok(f) => {
                match execute_generic_lin_function(f, &parsed_args, &module) {
                    Ok(val) => {
                        println!("{}", serde_json::to_string(&val).unwrap());
                    },
                    Err(e) => {
                        eprintln!("{{\"ok\": false, \"error\": \"Execution error: {}\"}}", e);
                        std::process::exit(1);
                    }
                }
            },
            Err(e) => {
                eprintln!("{{\"ok\": false, \"error\": \"{}\"}}", e);
                std::process::exit(1);
            }
        }
        return;
    }

    if args.len() > 1 && args[1] == "--test-suite" {
        println!("Lin Generic Evaluator Core OK");
        return;
    }

    eprintln!("Usage: lin_rust call <file.lin> <fn_name> '<args_json>'");
}
