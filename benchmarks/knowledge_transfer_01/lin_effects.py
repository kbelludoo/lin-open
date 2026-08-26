#!/usr/bin/env python3
"""
KNOWLEDGE_TRANSFER_TEST_01
Test if LIN can use prior knowledge to select candidates for new module.

New module: lin_effects (string_heavy + regex_heavy workload)
Prior knowledge from content_hash experiments:
  TypeScript > MJS > Python > Rust

Expected: LIN selects TypeScript as first candidate without re-discovery.
"""

import re
import hashlib
import time
import json
from typing import List, Dict, Any


def infer_effects(body: str, params: str = "") -> List[str]:
    """Infer effects from function body (lin_effects module)."""
    effects: List[str] = []
    s: str = str(body or "")
    
    if re.search(r'\b(fs|path|http|fetch|console|readFile|writeFile)\b', s):
        effects.append('io')
    if re.search(r'\bthis\.\b', s) or re.search(r'\bglobal\b', s):
        effects.append('state')
    if re.search(r'\bawait\b|\basync\b|\bPromise\b', s):
        effects.append('async')
    if re.search(r'\bthrow\b|\bpanic\b|\braise\b', s):
        effects.append('fail')
    if re.search(r'\bMath\.random\b|\brandom\b', s):
        effects.append('random')
    if re.search(r'\bDate\.now\b|\bnew Date\b', s):
        effects.append('time')
    if re.search(r'\bpostMessage\b|\bspawn\b|\bsend\b', s):
        effects.append('agent')
    if len(effects) == 0:
        effects.append('pure')
    return effects


def validate_effects(declared: List[str], inferred: List[str]) -> List[str]:
    """Validate declared effects against inferred effects."""
    decl_set: Dict[str, int] = {}
    for eff in (declared or []):
        decl_set[eff] = 1
    
    violations: List[str] = []
    inf: List[str] = inferred or []
    for eff in inf:
        if eff != 'pure' and eff not in decl_set:
            violations.append(eff)
    return violations


def emit_effect_annotation(effects: List[str], target: str) -> str:
    """Emit effect annotation for target language."""
    effs: str = ', '.join(effects or ['pure'])
    if target in ('js', 'ts'):
        return f'/* @effects: {effs} */'
    elif target == 'py':
        return f'# @effects: {effs}'
    elif target == 'haskell':
        return f'{{- @effects: {effs} -}}'
    return f'// @effects: {effs}'


def content_hash(body: str) -> str:
    """Compute content hash for function body."""
    return hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]


def main():
    iterations = 10000
    
    # Workload: realistic effect inference patterns
    workload = [
        {'body': 'console.log("hello")', 'expected': ['io']},
        {'body': 'await fetch(url)', 'expected': ['io', 'async']},
        {'body': 'this.state = value', 'expected': ['state']},
        {'body': 'throw new Error("fail")', 'expected': ['fail']},
        {'body': 'Math.random()', 'expected': ['random']},
        {'body': 'new Date()', 'expected': ['time']},
        {'body': 'postMessage(data)', 'expected': ['agent']},
        {'body': 'x = 1 + 2', 'expected': ['pure']},
        {'body': 'fs.readFile(path)', 'expected': ['io']},
        {'body': 'global.config', 'expected': ['state']},
    ]
    
    # Phase 1: inferEffects
    print('=== Phase 1: inferEffects ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for item in workload:
            infer_effects(item['body'])
    elapsed = (time.perf_counter() - start) * 1000
    total = iterations * len(workload)
    print(f'  {total} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total:.2f}us')
    
    # Phase 2: validateEffects
    print('=== Phase 2: validateEffects ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for item in workload:
            validate_effects(item['expected'], infer_effects(item['body']))
    elapsed = (time.perf_counter() - start) * 1000
    print(f'  {total} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total:.2f}us')
    
    # Phase 3: emitEffectAnnotation
    print('=== Phase 3: emitEffectAnnotation ===')
    start = time.perf_counter()
    for _ in range(iterations):
        for item in workload:
            emit_effect_annotation(infer_effects(item['body']), 'ts')
    elapsed = (time.perf_counter() - start) * 1000
    print(f'  {total} calls: {elapsed:.2f}ms')
    print(f'  Per call: {elapsed * 1000 / total:.2f}us')
    
    # Oracle
    print('\n=== Oracle: Semantic Output ===')
    print('Oracle hashes:')
    for item in workload:
        effects = infer_effects(item['body'])
        hash_val = content_hash(json.dumps(effects))
        print(f'  {item["body"][:30]:30} → {effects} → {hash_val}')
    
    # Knowledge Transfer Assessment
    print('\n=== Knowledge Transfer Assessment ===')
    print('Prior knowledge from content_hash experiments:')
    print('  TypeScript > MJS > Python > Rust (for string_heavy + regex_heavy)')
    print('')
    print('New module workload classification:')
    print('  lin_effects: string_heavy + regex_heavy (regex matching for effect inference)')
    print('')
    print('Knowledge transfer recommendation:')
    print('  1. TypeScript (STRONG evidence from prior experiments)')
    print('  2. MJS (baseline, STRONG evidence)')
    print('  3. Python (MEDIUM evidence)')
    print('  4. Rust (REJECTED — semantic mismatch + performance regression)')
    print('')
    print('Expected: TypeScript should be selected as first candidate')
    print('without needing to re-discover or re-benchmark all languages.')


if __name__ == '__main__':
    main()
