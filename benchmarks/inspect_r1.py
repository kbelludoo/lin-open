import json

with open(r'C:\Users\kbell\OneDrive\Documents\lia\raw\phase_a\seed_001.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for u in data['units'][:8]:
    print(f"=== Task {u['taskId']} | Lang: {u['language']} | Pass: {u['firstPassOk']} ===")
    print(f"Check Stage: {u['checkStage']} | Reason: {u['checkReason'][:80]}")
    print(f"Snippet:\n{u['codeSnippet'][:180]}\n{'-'*60}")
