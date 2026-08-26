use sha2::{Sha256, Digest};
use hex;

fn canonicalize(fn_name: &str, params: &str, body: &str) -> String {
    let mut canon = body.trim().to_string();
    canon = regex::Regex::new(r"\s+").unwrap().replace_all(&canon, " ").to_string();
    
    let param_list: Vec<&str> = params.split(',')
        .map(|p| p.trim().split(':').next().unwrap().trim())
        .filter(|p| !p.is_empty())
        .collect();
    
    for (j, p) in param_list.iter().enumerate() {
        let re = regex::Regex::new(&format!(r"\b{}\b", regex::escape(p))).unwrap();
        let replacement = format!("$\{\}", j);
        canon = re.replace_all(&canon, &replacement).to_string();
    }
    
    canon = canon.replace(''', """);
    canon = canon.replace("===", "===").replace("!==", "!==");
    canon = regex::Regex::new(r";\s*").unwrap().replace_all(&canon, ";").to_string();
    
    format!("({}){}", param_list.len(), canon)
}

fn content_hash(fn_name: &str, params: &str, body: &str) -> String {
    let canonical = canonicalize(fn_name, params, body);
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    let result = hasher.finalize();
    hex::encode(&result[..8])
}

fn main() {
    println!("{}", content_hash("add", "a,b", "^a+b"));
}
