with open('src_rust/src/main.rs', 'r') as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if line.startswith('fn js_equals(v1: &Value, v2: &Value) -> bool {'):
        if 'v2: &Value) -> bool' in ''.join(lines): # we are doing it via a simpler block replacement
            pass
