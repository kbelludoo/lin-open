#!/usr/bin/env python3
"""content_hash module - Python variant for SELF-OPTIMIZE-03"""

import re
import hashlib
import time
import json

def canonicalize(fn_name, params, body):
    """Canonicalize function representation for consistent hashing."""
    canon = body.strip()
    # Collapse whitespace
    canon = re.sub(r'\s+', ' ', canon)
    
    # Parse params
    param_list = params.split(',')
    clean = []
    for p in param_list:
        cleaned = p.strip().split(':')[0].strip()
        if cleaned:
            clean.append(cleaned)
    
    # Replace param names with $0, $1, etc.
    for j, param in enumerate(clean):
        pattern = r'\b' + re.escape(param) + r'\b'
        canon = re.sub(pattern, f'${j}', canon)
    
    # Normalize quotes and operators
    canon = canon.replace("'", '"')
    canon = canon.replace('===', '==')
    canon = canon.replace('!==', '!=')
    
    # Collapse semicolons
    canon = re.sub(r';\s*', ';', canon)
    
    return f'({len(clean)}){canon}'


def content_hash(fn_name, params, body):
    """Compute content hash for function."""
    canonical = canonicalize(fn_name, params, body)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]


def semantic_equals(fn1, fn2):
    """Check if two functions are semantically equivalent."""
    h1 = content_hash(fn1['name'], fn1['params'], fn1['body'])
    h2 = content_hash(fn2['name'], fn2['params'], fn2['body'])
    return h1 == h2


def build_content_registry(fns):
    """Build content registry from list of functions."""
    registry = {}
    for fn in fns:
        hash_val = content_hash(fn['name'], fn['params'], fn['body'])
        registry[hash_val] = {
            'name': fn['name'],
            'params': fn['params'],
            'hash': hash_val,
            'bodyLen': len(fn.get('body', ''))
        }
    return registry


def main():
    iterations = 10000
    
    # Workload (same as MJS and Rust)
    workload = [
        {'name': 'canonicalize', 'params': 'fnName,params,body', 'body': 'canon=String(body).trim()'},
        {'name': 'contentHash', 'params': 'fnName,params,body', 'body': 'canonical=canonicalize(fnName,params,body)'},
        {'name': 'semanticEquals', 'params': 'fn1,fn2', 'body': 'h1=contentHash(fn1.name,fn1.params,fn1.body)'},
        {'name': 'buildContentRegistry', 'params': 'prog', 'body': 'registry={};fns=prog.fns'},
        {'name': 'walkAst', 'params': 'node,visitor', 'body': 'if(node==null){return null}'},
        {'name': 'transformAst', 'params': 'node,transformer', 'body': 'if(node==null){return null}'},
        {'name': 'astNode', 'params': 'type,value,children', 'body': 'return ({type:type,value:value})'},
        {'name': 'astFn', 'params': 'name,params,body', 'body': 'return astNode("fn",name,params)'},
        {'name': 'inferEffects', 'params': 'body', 'body': 'effects=[];s=String(body)'},
        {'name': 'checkRefinement', 'params': 'param,constraintText,errors', 'body': 'parts=constraintText.split(",")'},
    ]
    
    # Phase 1: canonicalize
    print('=== Phase 1: canonicalize ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for fn in workload:
            canonicalize(fn['name'], fn['params'], fn['body'])
    elapsed = (time.perf_counter() - start) * 1000
    total = iterations * len(workload)
    print(f'  {total} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total:.2f}us')
    
    # Phase 2: contentHash
    print('=== Phase 2: contentHash ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for fn in workload:
            content_hash(fn['name'], fn['params'], fn['body'])
    elapsed = (time.perf_counter() - start) * 1000
    print(f'  {total} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total:.2f}us')
    
    # Phase 3: semanticEquals
    print('=== Phase 3: semanticEquals ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for i in range(len(workload) - 1):
            semantic_equals(workload[i], workload[i + 1])
    elapsed = (time.perf_counter() - start) * 1000
    total_se = iterations * (len(workload) - 1)
    print(f'  {total_se} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total_se:.2f}us')
    
    # Phase 4: buildContentRegistry
    print('=== Phase 4: buildContentRegistry ===')
    start = time.perf_counter()
    for _ in range(iterations):
        build_content_registry(workload)
    elapsed = (time.perf_counter() - start) * 1000
    print(f'  {iterations} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / iterations:.2f}us')
    
    # Oracle
    print('\n=== Oracle: Semantic Output ===')
    print('Oracle hashes:')
    for fn in workload:
        hash_val = content_hash(fn['name'], fn['params'], fn['body'])
        print(f'  {fn["name"]}: {hash_val}')
    
    # Determinism
    print('\n=== Determinism Check ===')
    oracle1 = [content_hash(fn['name'], fn['params'], fn['body']) for fn in workload]
    oracle2 = [content_hash(fn['name'], fn['params'], fn['body']) for fn in workload]
    print(f'  Deterministic: {oracle1 == oracle2}')


if __name__ == '__main__':
    main()
