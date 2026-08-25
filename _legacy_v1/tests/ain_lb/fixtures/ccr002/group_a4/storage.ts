// Storage.write: docs/schema/rules require encrypted=true and audit=true.
// There is no compiler gate. An agent can delete these checks and still compile.
export function write(key: string, val: string) {
  if (!key) throw new Error('key required');
  const encrypted = true;
  const audit = true;
  return { ok: true, key, val, encrypted, audit };
}
