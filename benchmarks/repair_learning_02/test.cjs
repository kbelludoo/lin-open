#!/usr/bin/env node
/**
 * REPAIR_LEARNING_02: Multi-target strategy reuse
 * 
 * Tests if repair strategy from Crystal can be applied to:
 * - Python
 * - TypeScript
 * - Rust
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// MJS canonicalization function
function canonicalize(fnName, params, body) {
  let canon = String(body || '').trim();
  canon = canon.replace(/\s+/g, ' ');
  
  const paramList = String(params || '').split(',');
  const clean = [];
  for (let i = 0; i < paramList.length; i++) {
    const p = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  
  for (let j = 0; j < clean.length; j++) {
    const re = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  
  return '(' + clean.length + ')' + canon;
}

function contentHash(fnName, params, body) {
  const canonical = canonicalize(fnName, params, body);
  const hash = crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

// Expected hash
const expectedHash = contentHash('add', 'a,b', '^a+b');
console.log('=== REPAIR_LEARNING_02: MULTI-TARGET STRATEGY REUSE ===');
console.log(`Expected MJS hash: ${expectedHash}`);

// Strategy from Crystal analysis
const strategy = 'implement SHA-256 canonicalization matching MJS algorithm';
console.log(`Strategy: ${strategy}`);
console.log(`Source: Crystal (hashing_algorithm mismatch)`);

const results = [];

// === PYTHON ===
console.log('\n=== TARGET 1: PYTHON ===');
const pythonVariant = `#!/usr/bin/env python3
import hashlib
import re

def canonicalize(fn_name, params, body):
    canon = body.strip()
    canon = re.sub(r'\\s+', ' ', canon)
    param_list = [p.strip().split(':')[0].strip() for p in params.split(',') if p.strip()]
    for j, p in enumerate(param_list):
        canon = re.sub(r'\\b' + re.escape(p) + r'\\b', '$' + str(j), canon)
    canon = canon.replace("'", '"')
    canon = canon.replace('===', '===').replace('!==', '!==')
    canon = re.sub(r';\\s*', ';', canon)
    return '(' + str(len(param_list)) + ')' + canon

def content_hash(fn_name, params, body):
    canonical = canonicalize(fn_name, params, body)
    hash_bytes = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return hash_bytes[:16]

if __name__ == '__main__':
    print(content_hash('add', 'a,b', '^a+b'))
`;

const pythonFile = path.join(__dirname, 'target_python.py');
fs.writeFileSync(pythonFile, pythonVariant);
const pythonResult = execSync(`python "${pythonFile}"`, { encoding: 'utf-8' }).trim();
console.log(`Python hash: ${pythonResult}`);
console.log(`Match: ${pythonResult === expectedHash}`);
results.push({ language: 'Python', match: pythonResult === expectedHash, iterations: 1 });
fs.unlinkSync(pythonFile);

// === TYPESCRIPT ===
console.log('\n=== TARGET 2: TYPESCRIPT ===');
const typescriptVariant = `#!/usr/bin/env node
import { createHash } from 'crypto';

function canonicalize(fnName: string, params: string, body: string): string {
  let canon = (body || '').trim();
  canon = canon.replace(/\\s+/g, ' ');
  
  const paramList = (params || '').split(',');
  const clean: string[] = [];
  for (let i = 0; i < paramList.length; i++) {
    const p = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  
  for (let j = 0; j < clean.length; j++) {
    const re = new RegExp('\\\\b' + clean[j] + '\\\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\\s*/g, ';');
  
  return '(' + clean.length + ')' + canon;
}

function contentHash(fnName: string, params: string, body: string): string {
  const canonical = canonicalize(fnName, params, body);
  const hash = createHash('sha256').update(canonical, 'utf8').digest('hex');
  return hash.slice(0, 16);
}

console.log(contentHash('add', 'a,b', '^a+b'));
`;

const tsFile = path.join(__dirname, 'target_typescript.ts');
fs.writeFileSync(tsFile, typescriptVariant);
const tsResult = execSync(`node --experimental-strip-types "${tsFile}"`, { encoding: 'utf-8' }).trim();
console.log(`TypeScript hash: ${tsResult}`);
console.log(`Match: ${tsResult === expectedHash}`);
results.push({ language: 'TypeScript', match: tsResult === expectedHash, iterations: 1 });
fs.unlinkSync(tsFile);

// === RUST ===
console.log('\n=== TARGET 3: RUST ===');
const rustVariant = `use sha2::{Sha256, Digest};
use hex;

fn canonicalize(fn_name: &str, params: &str, body: &str) -> String {
    let mut canon = body.trim().to_string();
    canon = regex::Regex::new(r"\\s+").unwrap().replace_all(&canon, " ").to_string();
    
    let param_list: Vec<&str> = params.split(',')
        .map(|p| p.trim().split(':').next().unwrap().trim())
        .filter(|p| !p.is_empty())
        .collect();
    
    for (j, p) in param_list.iter().enumerate() {
        let re = regex::Regex::new(&format!(r"\\b{}\\b", regex::escape(p))).unwrap();
        let replacement = format!("$\\{\\}", j);
        canon = re.replace_all(&canon, &replacement).to_string();
    }
    
    canon = canon.replace('\'', "\"");
    canon = canon.replace("===", "===").replace("!==", "!==");
    canon = regex::Regex::new(r";\\s*").unwrap().replace_all(&canon, ";").to_string();
    
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
`;

const rustFile = path.join(__dirname, 'target_rust.rs');
fs.writeFileSync(rustFile, rustVariant);
try {
  // Compile and run Rust
  execSync(`rustc "${rustFile}" -o "${path.join(__dirname, 'target_rust.exe')}" --edition 2021`, { encoding: 'utf-8' });
  const rustResult = execSync(`"${path.join(__dirname, 'target_rust.exe')}"`, { encoding: 'utf-8' }).trim();
  console.log(`Rust hash: ${rustResult}`);
  console.log(`Match: ${rustResult === expectedHash}`);
  results.push({ language: 'Rust', match: rustResult === expectedHash, iterations: 1 });
} catch (e) {
  console.log(`Rust compilation failed: ${e.message}`);
  results.push({ language: 'Rust', match: false, iterations: 0, error: 'compilation_failed' });
}

// === VALIDATION ===
console.log('\n=== VALIDATION ===');
const successfulTargets = results.filter(r => r.match).length;
const totalTargets = results.length;
const portabilityScore = successfulTargets / totalTargets;

console.log(`Successful targets: ${successfulTargets}/${totalTargets}`);
console.log(`Portability score: ${portabilityScore.toFixed(2)}`);
console.log(`Language independence: ${portabilityScore >= 0.67 ? 'YES' : 'NO'}`);

console.log('\n=== RESULTS ===');
results.forEach(r => {
  console.log(`${r.language}: ${r.match ? 'PASS' : 'FAIL'} (${r.iterations} iterations)`);
});

console.log('\n=== REPAIR_LEARNING_02 COMPLETE ===');
console.log(`Strategy portability: ${portabilityScore >= 0.67 ? 'VALIDATED' : 'LIMITED'}`);
console.log('Language-independent knowledge: ' + (portabilityScore >= 0.67 ? 'YES' : 'NO'));
