use regex::Regex;
use sha2::{Sha256, Digest};
use std::collections::HashMap;
use std::time::Instant;

#[derive(Clone, Debug)]
struct Fn {
    name: String,
    params: String,
    body: String,
}

fn canonicalize(_fn_name: &str, params: &str, body: &str) -> String {
    let mut canon = body.trim().to_string();
    // Collapse whitespace
    let ws_re = Regex::new(r"\s+").unwrap();
    canon = ws_re.replace_all(&canon, " ").to_string();
    
    // Parse params
    let param_list: Vec<&str> = params.split(',').collect();
    let mut clean: Vec<String> = Vec::new();
    for p in param_list {
        let trimmed = p.trim();
        // Remove type annotations (everything after first colon)
        let cleaned = match trimmed.find(':') {
            Some(pos) => &trimmed[..pos],
            None => trimmed,
        };
        if !cleaned.is_empty() {
            clean.push(cleaned.to_string());
        }
    }
    
    // Replace param names with $0, $1, etc.
    for (j, param) in clean.iter().enumerate() {
        let pattern = format!(r"\b{}\b", regex::escape(param));
        let re = Regex::new(&pattern).unwrap();
        let replacement = format!("${}", j);
        canon = re.replace_all(&canon, replacement.as_str()).to_string();
    }
    
    // Normalize quotes and operators
    canon = canon.replace('\'', "\"");
    canon = canon.replace("===", "==");
    canon = canon.replace("!==", "!=");
    
    // Collapse semicolons
    let semi_re = Regex::new(r";\s*").unwrap();
    canon = semi_re.replace_all(&canon, ";").to_string();
    
    format!("({}){}", clean.len(), canon)
}

fn content_hash(fn_name: &str, params: &str, body: &str) -> String {
    let canonical = canonicalize(fn_name, params, body);
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    let result = hasher.finalize();
    hex::encode(&result[..8])
}

fn semantic_equals(fn1: &Fn, fn2: &Fn) -> bool {
    let h1 = content_hash(&fn1.name, &fn1.params, &fn1.body);
    let h2 = content_hash(&fn2.name, &fn2.params, &fn2.body);
    h1 == h2
}

fn build_content_registry(fns: &[Fn]) -> HashMap<String, HashMap<String, String>> {
    let mut registry: HashMap<String, HashMap<String, String>> = HashMap::new();
    for f in fns {
        let hash = content_hash(&f.name, &f.params, &f.body);
        let mut entry = HashMap::new();
        entry.insert("name".to_string(), f.name.clone());
        entry.insert("params".to_string(), f.params.clone());
        entry.insert("hash".to_string(), hash.clone());
        entry.insert("bodyLen".to_string(), (f.body.len()).to_string());
        registry.insert(hash, entry);
    }
    registry
}

fn main() {
    let iterations = 10000;
    
    // Workload
    let workload: Vec<Fn> = vec![
        Fn { name: "canonicalize".into(), params: "fnName,params,body".into(), body: "canon=String(body).trim()".into() },
        Fn { name: "contentHash".into(), params: "fnName,params,body".into(), body: "canonical=canonicalize(fnName,params,body)".into() },
        Fn { name: "semanticEquals".into(), params: "fn1,fn2".into(), body: "h1=contentHash(fn1.name,fn1.params,fn1.body)".into() },
        Fn { name: "buildContentRegistry".into(), params: "prog".into(), body: "registry={};fns=prog.fns".into() },
        Fn { name: "walkAst".into(), params: "node,visitor".into(), body: "if(node==null){return null}".into() },
        Fn { name: "transformAst".into(), params: "node,transformer".into(), body: "if(node==null){return null}".into() },
        Fn { name: "astNode".into(), params: "type,value,children".into(), body: "return ({type:type,value:value})".into() },
        Fn { name: "astFn".into(), params: "name,params,body".into(), body: "return astNode(\"fn\",name,params)".into() },
        Fn { name: "inferEffects".into(), params: "body".into(), body: "effects=[];s=String(body)".into() },
        Fn { name: "checkRefinement".into(), params: "param,constraintText,errors".into(), body: "parts=constraintText.split(\",\")".into() },
    ];
    
    // Phase 1: canonicalize
    println!("=== Phase 1: canonicalize ===");
    let start = Instant::now();
    for _ in 0..iterations {
        for f in &workload {
            canonicalize(&f.name, &f.params, &f.body);
        }
    }
    let elapsed = start.elapsed().as_millis() as f64;
    let total = (iterations * workload.len()) as f64;
    println!("  {} calls: {:.2}ms", total as u64, elapsed);
    println!("  Per call: {:.2}us", elapsed * 1000.0 / total);
    
    // Phase 2: contentHash
    println!("=== Phase 2: contentHash ===");
    let start = Instant::now();
    for _ in 0..iterations {
        for f in &workload {
            content_hash(&f.name, &f.params, &f.body);
        }
    }
    let elapsed = start.elapsed().as_millis() as f64;
    println!("  {} calls: {:.2}ms", total as u64, elapsed);
    println!("  Per call: {:.2}us", elapsed * 1000.0 / total);
    
    // Phase 3: semanticEquals
    println!("=== Phase 3: semanticEquals ===");
    let start = Instant::now();
    for _ in 0..iterations {
        for i in 0..workload.len()-1 {
            semantic_equals(&workload[i], &workload[i+1]);
        }
    }
    let elapsed = start.elapsed().as_millis() as f64;
    let total_se = (iterations * (workload.len() - 1)) as f64;
    println!("  {} calls: {:.2}ms", total_se as u64, elapsed);
    println!("  Per call: {:.2}us", elapsed * 1000.0 / total_se);
    
    // Phase 4: buildContentRegistry
    println!("=== Phase 4: buildContentRegistry ===");
    let start = Instant::now();
    for _ in 0..iterations {
        build_content_registry(&workload);
    }
    let elapsed = start.elapsed().as_millis() as f64;
    println!("  {} calls: {:.2}ms", iterations, elapsed);
    println!("  Per call: {:.2}us", elapsed * 1000.0 / iterations as f64);
    
    // Oracle
    println!("\n=== Oracle: Semantic Output ===");
    println!("Oracle hashes:");
    for f in &workload {
        let hash = content_hash(&f.name, &f.params, &f.body);
        println!("  {}: {}", f.name, hash);
    }
    
    // Determinism
    println!("\n=== Determinism Check ===");
    let oracle1: Vec<String> = workload.iter().map(|f| content_hash(&f.name, &f.params, &f.body)).collect();
    let oracle2: Vec<String> = workload.iter().map(|f| content_hash(&f.name, &f.params, &f.body)).collect();
    println!("  Deterministic: {}", oracle1 == oracle2);
}
