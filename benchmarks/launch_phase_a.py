import sqlite3, os, subprocess, sys

# Retrieve active key from 9router sqlite
db_path = os.path.join(os.environ.get('APPDATA', ''), '9router', 'db', 'data.sqlite')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1;')
row = cur.fetchone()
if not row:
    print('Error: No active API key found in 9router sqlite')
    sys.exit(1)
key = row[0]

fixed_model = sys.argv[1] if len(sys.argv) > 1 else 'groq/llama-3.3-70b-versatile'
start_seed = sys.argv[2] if len(sys.argv) > 2 else '1'
end_seed = sys.argv[3] if len(sys.argv) > 3 else '5'

env = os.environ.copy()
env['OPENAI_BASE_URL'] = 'http://localhost:20128/v1'
env['OPENAI_API_KEY'] = key
env['OPENAI_MODEL'] = fixed_model
env['NINEROUTER_URL'] = 'http://localhost:20128/v1'
env['NINEROUTER_KEY'] = key
env['AINLB_PROVIDER'] = '9router'

# Ensure cargo bin is in PATH for rustc
cargo_bin = os.path.expanduser('~/.cargo/bin')
cur_path = env.get('PATH', '')
if cargo_bin not in cur_path:
    env['PATH'] = cargo_bin + os.pathsep + cur_path

print(f"=== LAUNCHING CONFIRMATORY PHASE A: Model = {fixed_model} | Seeds = {start_seed}..{end_seed} ===")

p = subprocess.Popen([
    'node', 'scripts/run_phase_a.mjs', start_seed, end_seed, fixed_model
], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

for line in p.stdout:
    sys.stdout.write(line)
    sys.stdout.flush()

p.wait()
sys.exit(p.returncode)
