import re

with open('src_rust/src/main.rs', 'r') as f:
    content = f.read()

# Replace js_equals
js_equals_new = """fn js_equals(v1: &Value, v2: &Value) -> bool {
    if v1 == v2 { return true; }
    let is_null_or_undef = |v: &Value| matches!(v, Value::Null);
    if is_null_or_undef(v1) || is_null_or_undef(v2) {
        return false;
    }
    if let (Some(n1), Some(n2)) = (to_js_number(v1), to_js_number(v2)) {
        return n1 == n2;
    }
    false
}"""
content = re.sub(r'fn js_equals\(v1: &Value, v2: &Value\) -> bool \{.*?\n\}', js_equals_new, content, flags=re.DOTALL)

# Replace js_rel_lt
js_rel_lt_new = """fn js_rel_lt(a: &Value, b: &Value) -> Option<bool> {
    let psa = val_to_primitive_string(a);
    let psb = val_to_primitive_string(b);
    if let (Some(sa), Some(sb)) = (&psa, &psb) {
        return Some(sa.as_str() < sb.as_str());
    }
    match (to_js_number(a), to_js_number(b)) {
        (Some(na), Some(nb)) => Some(na < nb),
        _ => None,
    }
}"""
content = re.sub(r'fn js_rel_lt\(a: &Value, b: &Value\) -> bool \{.*?\n\}', js_rel_lt_new, content, flags=re.DOTALL)

# Replace eval_expr
eval_expr_new = """pub fn eval_expr(expr: &str, scope: &mut Scope, module: &LinModule) -> Value {
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
        return Value::Bool(!js_rel_lt(&rv, &lv).unwrap_or(true));
    }
    if let Some(pos) = find_binary_op(s, ">=") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 2..], scope, module);
        return Value::Bool(!js_rel_lt(&lv, &rv).unwrap_or(true));
    }
    if let Some(pos) = find_binary_op(s, "<") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        return Value::Bool(js_rel_lt(&lv, &rv).unwrap_or(false));
    }
    if let Some(pos) = find_binary_op(s, ">") {
        let lv = eval_expr(&s[..pos], scope, module);
        let rv = eval_expr(&s[pos + 1..], scope, module);
        return Value::Bool(js_rel_lt(&rv, &lv).unwrap_or(false));
    }

    if let Some(pos) = find_binary_op(s, "+") {
        let v1 = eval_expr(&s[..pos], scope, module);
        let v2 = eval_expr(&s[pos + 1..], scope, module);
        return js_add(v1, v2);
    }
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

    if s.starts_with('!') {
        let inner_val = eval_expr(&s[1..], scope, module);
        return Value::Bool(!is_truthy(&inner_val));
    }

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

    if s == "true" { return Value::Bool(true); }
    if s == "false" { return Value::Bool(false); }
    if s == "null" || s == "undefined" { return Value::Null; }

    if (s.starts_with('\\'') && s.ends_with('\\'') && s.len() >= 2) || 
       (s.starts_with('"') && s.ends_with('"') && s.len() >= 2) {
        return Value::String(s[1..s.len() - 1].to_string());
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

    if let Some(val) = scope.vars.get(s) {
        return val.clone();
    }

    Value::String(s.to_string())
}"""
content = re.sub(r'pub fn eval_expr\(expr: &str, scope: &mut Scope, module: &LinModule\) -> Value \{.*?\nfn js_equals', eval_expr_new + '\n\nfn js_equals', content, flags=re.DOTALL)

# Replace find_binary_op
find_binary_op_new = """fn find_binary_op(s: &str, op: &str) -> Option<usize> {
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

        if c == '\\\\' {
            escape = true;
            continue;
        }

        if let Some(q) = in_quote {
            if c == q { in_quote = None; }
            continue;
        } else if c == '\\'' || c == '"' {
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

                if op == "-" || op == "+" {
                    let mut is_unary = false;
                    let mut j = i;
                    while j > 0 {
                        j -= 1;
                        if !chars[j].is_whitespace() {
                            let prev = chars[j];
                            if "+-*/%<>=!&|([{},?:".contains(prev) {
                                is_unary = true;
                            }
                            break;
                        }
                    }
                    if j == 0 && (i == 0 || chars[0].is_whitespace()) {
                        is_unary = true;
                    }
                    if is_unary {
                        continue;
                    }
                }
                
                return Some(i);
            }
        }
    }
    None
}"""
content = re.sub(r'fn find_binary_op\(s: &str, op: &str\) -> Option<usize> \{.*?\n\}', find_binary_op_new, content, flags=re.DOTALL)

with open('src_rust/src/main.rs', 'w') as f:
    f.write(content)
