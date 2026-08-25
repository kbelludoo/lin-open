fn js_equals(v1: &Value, v2: &Value) -> bool {
    if v1 == v2 { return true; }
    let is_null_or_undef = |v: &Value| matches!(v, Value::Null);
    if is_null_or_undef(v1) || is_null_or_undef(v2) {
        return false;
    }
    if let (Some(n1), Some(n2)) = (to_js_number(v1), to_js_number(v2)) {
        return n1 == n2;
    }
    false
}

fn js_rel_lt(a: &Value, b: &Value) -> Option<bool> {
    let psa = val_to_primitive_string(a);
    let psb = val_to_primitive_string(b);
    if let (Some(sa), Some(sb)) = (&psa, &psb) {
        return Some(sa.as_str() < sb.as_str());
    }
    match (to_js_number(a), to_js_number(b)) {
        (Some(na), Some(nb)) => Some(na < nb),
        _ => None,
    }
}
