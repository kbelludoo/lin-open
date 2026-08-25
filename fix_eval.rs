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

    // 0. Curto-Circuito Lógico (&&, ||)
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

    // 1. Comparações (==, !=, <=, >=, <, >)
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

    // 2. Adição (+): JS semantics via js_add
    if let Some(pos) = find_binary_op(s, "+") {
        let v1 = eval_expr(&s[..pos], scope, module);
        let v2 = eval_expr(&s[pos + 1..], scope, module);
        return js_add(v1, v2);
    }
    // 3. Subtração (-) e outras aritméticas
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

    // Unary prefix
    if s.starts_with('!') {
        let inner_val = eval_expr(&s[1..], scope, module);
        return Value::Bool(!is_truthy(&inner_val));
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

    // Literals and variables
    if s == "true" { return Value::Bool(true); }
    if s == "false" { return Value::Bool(false); }
    if s == "null" || s == "undefined" { return Value::Null; }

    if (s.starts_with('\'') && s.ends_with('\'') && s.len() >= 2) || 
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
}
