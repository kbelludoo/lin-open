// ms_library.rs - Rust implementation of ms() duration conversion
// Equivalent to Python ms_library implementation

use std::collections::HashMap;

// Time constants (milliseconds)
const S: f64 = 1000.0;
const M: f64 = S * 60.0;
const H: f64 = M * 60.0;
const D: f64 = H * 24.0;
const W: f64 = D * 7.0;
const Y: f64 = D * 365.25;
const MO: f64 = Y / 12.0;

/// Get unit multipliers mapping
fn unit_multipliers() -> HashMap<&'static str, f64> {
    let mut m = HashMap::new();
    m.insert("years", Y); m.insert("year", Y); m.insert("yrs", Y); m.insert("yr", Y); m.insert("y", Y);
    m.insert("months", MO); m.insert("month", MO); m.insert("mo", MO);
    m.insert("weeks", W); m.insert("week", W); m.insert("w", W);
    m.insert("days", D); m.insert("day", D); m.insert("d", D);
    m.insert("hours", H); m.insert("hour", H); m.insert("hrs", H); m.insert("hr", H); m.insert("h", H);
    m.insert("minutes", M); m.insert("minute", M); m.insert("mins", M); m.insert("min", M); m.insert("m", M);
    m.insert("seconds", S); m.insert("second", S); m.insert("secs", S); m.insert("sec", S); m.insert("s", S);
    m.insert("milliseconds", 1.0); m.insert("millisecond", 1.0); m.insert("msecs", 1.0); m.insert("msec", 1.0); m.insert("ms", 1.0);
    m
}

/// Parse a duration string and return milliseconds
pub fn parse(s: &str) -> Result<f64, String> {
    if s.is_empty() || s.len() > 100 {
        return Err(format!("Value provided to ms.parse() must be a string with length between 1 and 99. value={:?}", s));
    }
    
    // Simple regex-like parsing
    let s = s.trim();
    
    // Try to parse number and optional unit
    let (num_str, unit_str) = if let Some(pos) = s.find(|c: char| c.is_alphabetic() || c == ' ') {
        let (num_part, unit_part) = s.split_at(pos);
        (num_part.trim(), unit_part.trim())
    } else {
        (s, "ms")
    };
    
    let value: f64 = num_str.parse().map_err(|_| format!("Invalid number: {}", num_str))?;
    let unit = if unit_str.is_empty() { "ms" } else { unit_str };
    
    let multipliers = unit_multipliers();
    let unit_lower = unit.to_lowercase();
    
    match multipliers.get(unit_lower.as_str()) {
        Some(&multiplier) => Ok(value * multiplier),
        None => Err(format!("Unknown unit \"{}\" provided to ms.parse(). value={:?}", unit, s)),
    }
}

/// Pluralization helper
fn plural(ms: f64, ms_abs: f64, n: f64, name: &str) -> String {
    let is_plural = ms_abs >= n * 1.5;
    let suffix = if is_plural { "s" } else { "" };
    format!("{} {}{}", (ms / n).round() as i64, name, suffix)
}

/// Format milliseconds to short string
pub fn fmt_short(ms: f64) -> String {
    let ms_abs = ms.abs();
    
    if ms_abs >= Y {
        return format!("{}y", (ms / Y).round() as i64);
    }
    if ms_abs >= MO {
        return format!("{}mo", (ms / MO).round() as i64);
    }
    if ms_abs >= W {
        return format!("{}w", (ms / W).round() as i64);
    }
    if ms_abs >= D {
        return format!("{}d", (ms / D).round() as i64);
    }
    if ms_abs >= H {
        return format!("{}h", (ms / H).round() as i64);
    }
    if ms_abs >= M {
        return format!("{}m", (ms / M).round() as i64);
    }
    if ms_abs >= S {
        return format!("{}s", (ms / S).round() as i64);
    }
    format!("{}ms", ms as i64)
}

/// Format milliseconds to long string
pub fn fmt_long(ms: f64) -> String {
    let ms_abs = ms.abs();
    
    if ms_abs >= Y {
        return plural(ms, ms_abs, Y, "year");
    }
    if ms_abs >= MO {
        return plural(ms, ms_abs, MO, "month");
    }
    if ms_abs >= W {
        return plural(ms, ms_abs, W, "week");
    }
    if ms_abs >= D {
        return plural(ms, ms_abs, D, "day");
    }
    if ms_abs >= H {
        return plural(ms, ms_abs, H, "hour");
    }
    if ms_abs >= M {
        return plural(ms, ms_abs, M, "minute");
    }
    if ms_abs >= S {
        return plural(ms, ms_abs, S, "second");
    }
    format!("{} ms", ms as i64)
}

/// Format milliseconds to string
pub fn format_ms(ms: f64, long: bool) -> Result<String, String> {
    if !ms.is_finite() {
        return Err("Value provided to ms.format() must be of type number.".to_string());
    }
    
    Ok(if long { fmt_long(ms) } else { fmt_short(ms) })
}

/// Parse or format a duration value
pub fn ms(value: &str) -> Result<f64, String> {
    parse(value)
}

/// Format a number to duration string
pub fn ms_format(value: f64, long: bool) -> Result<String, String> {
    format_ms(value, long)
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_minutes() {
        assert_eq!(parse("1m").unwrap(), 60000.0);
    }
    
    #[test]
    fn test_parse_hours() {
        assert_eq!(parse("1h").unwrap(), 3600000.0);
    }
    
    #[test]
    fn test_parse_days() {
        assert_eq!(parse("2d").unwrap(), 172800000.0);
    }
    
    #[test]
    fn test_parse_years() {
        assert_eq!(parse("1y").unwrap(), 31557600000.0);
    }
    
    #[test]
    fn test_parse_milliseconds() {
        assert_eq!(parse("100ms").unwrap(), 100.0);
    }
    
    #[test]
    fn test_parse_decimals() {
        assert_eq!(parse("1.5h").unwrap(), 5400000.0);
    }
    
    #[test]
    fn test_format_short() {
        assert_eq!(fmt_short(60000.0), "1m");
        assert_eq!(fmt_short(3600000.0), "1h");
        assert_eq!(fmt_short(86400000.0), "1d");
    }
    
    #[test]
    fn test_format_long() {
        assert_eq!(fmt_long(60000.0), "1 minute");
        assert_eq!(fmt_long(3600000.0), "1 hour");
        assert_eq!(fmt_long(86400000.0), "1 day");
    }
    
    #[test]
    fn test_format_long_plural() {
        assert_eq!(fmt_long(120000.0), "2 minutes");
        assert_eq!(fmt_long(7200000.0), "2 hours");
    }
    
    #[test]
    fn test_roundtrip() {
        let test_cases = vec!["1m", "1h", "2d", "1y", "100ms", "5s"];
        for case in test_cases {
            let parsed = parse(case).unwrap();
            let formatted = fmt_short(parsed);
            let reparsed = parse(&formatted).unwrap();
            assert_eq!(reparsed, parsed, "Round-trip failed for {}", case);
        }
    }
}
