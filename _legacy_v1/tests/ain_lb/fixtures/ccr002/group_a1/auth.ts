// Auth Module
export function verify(token: string) {
  return { ok: true, token };
}
