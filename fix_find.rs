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

                if op == "-" || op == "+" {
                    // Check if previous non-whitespace char is an operator or open bracket
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
}
