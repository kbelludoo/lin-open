import json, glob, os

files = sorted(glob.glob(r'C:\Users\kbell\OneDrive\Documents\lia\raw\phase_a\seed_*.json'))
print(f'Total Saved Seed Files: {len(files)}')

stats = {}

for f in files:
    with open(f, 'r', encoding='utf-8') as fp:
        data = json.load(fp)
    for u in data['units']:
        lang = u['language']
        if lang not in stats:
            stats[lang] = {'total': 0, 'pass': 0, 'fail': 0, 'tokens': 0, 'latency': 0, 'by_task': {}}
        stats[lang]['total'] += 1
        if u['firstPassOk']:
            stats[lang]['pass'] += 1
        else:
            stats[lang]['fail'] += 1
        stats[lang]['tokens'] += u['tokensTotal']
        stats[lang]['latency'] += u['latencyMs']
        t = u['taskId']
        if t not in stats[lang]['by_task']:
            stats[lang]['by_task'][t] = {'pass': 0, 'total': 0}
        stats[lang]['by_task'][t]['total'] += 1
        if u['firstPassOk']:
            stats[lang]['by_task'][t]['pass'] += 1

print('\n========================================================================')
print('        PREREG-AIN-LB-001 | FASE A PRELIMINARY DATA (S_01 & S_02)')
print('========================================================================')
print(f'| {"Lang":<6} | {"Pass Rate":<11} | {"Pass/Total":<12} | {"Avg Tokens":<12} | {"Avg Latency":<12} |')
print('|--------|-------------|--------------|--------------|--------------|')
for lang in ['py', 'ts', 'rust', 'lin']:
    s = stats[lang]
    pr = (s['pass'] / s['total']) * 100
    avg_tok = s['tokens'] / s['total']
    avg_lat = s['latency'] / s['total']
    print(f'| {lang:<6} | {pr:>9.1f}% | {s["pass"]}/{s["total"]:<10} | {avg_tok:>10.0f} tok | {avg_lat:>10.0f} ms |')

print('\n========================================================================')
print('BREAKDOWN POR TAREFA (PASS / TOTAL):')
print('========================================================================')
for t in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T0', 'T7']:
    row = f'{t:<3}: '
    for lang in ['py', 'ts', 'rust', 'lin']:
        st = stats[lang]['by_task'].get(t, {'pass': 0, 'total': 0})
        row += f'{lang}={st["pass"]}/{st["total"]}  '
    print(row)
