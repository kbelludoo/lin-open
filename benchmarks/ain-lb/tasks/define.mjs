export const FIXTURE_SPEC = `
Build a medium user-management system:
- registration (email + password)
- login (token-based session)
- permissions (role-based: admin/member/viewer)
- audit logging (who did what, when)
- business rules (email unique, password min 8 chars, cannot delete self)
- a small test suite
- brief documentation
`

export const LANGUAGES = ['py', 'ts', 'rust', 'lin']

const SHARED = `
Generate ONLY the source code for this system in ${'__LANG__'}. No prose, no markdown fences, no explanation.
Place it in a single file so it can be syntax-checked by the toolchain.
`

function langLabel(lang) {
  return { py: 'Python', ts: 'TypeScript', rust: 'Rust' }[lang]
}

export const TASKS = {
  T1: { id: 'T1', name: 'create_initial_system', spec: (l) => `${FIXTURE_SPEC}\n${SHARED.replace('__LANG__', langLabel(l))}` },
  T2: { id: 'T2', name: 'add_feature', spec: (l) => `Add password reset and email verification to the existing user system.\n${SHARED.replace('__LANG__', langLabel(l))}` },
  T3: { id: 'T3', name: 'fix_introduced_bug', spec: (l) => `A user reports that duplicate registrations crash with a database uniqueness constraint error. Fix it to return a friendly error.\n${SHARED.replace('__LANG__', langLabel(l))}` },
  T4: { id: 'T4', name: 'refactor_architecture', spec: (l) => `Extract the authentication logic into a reusable module/interface, keeping behavior identical.\n${SHARED.replace('__LANG__', langLabel(l))}` },
  T5: { id: 'T5', name: 'migrate_requirement', spec: (l) => `Change the permission model from role-based (RBAC) to attribute-based (ABAC): a permission is granted if any required attribute is present.\n${SHARED.replace('__LANG__', langLabel(l))}` },
  T6: { id: 'T6', name: 'explain_invariants', spec: (l) => `Explain this system's invariants and how each one is enforced. Be concrete and reference the code structure.\n${SHARED.replace('__LANG__', langLabel(l))}` },
}

export const COLD_TASK = {
  id: 'T7',
  name: 'cold_agent_maintenance',
  artifactNote: 'All conversation history is removed. You receive ONLY the repository (code + memory + docs).',
  spec: (l) => `${langLabel(l)} — a new engineer with NO prior conversation must add OAuth login to the system, preserving all existing behavior. ${SHARED.replace('__LANG__', langLabel(l))}`,
}

export const RECOVERY_TASK = {
  id: 'T0',
  name: 'context_loss_recovery',
  // Artifacts + memory + docs ONLY; no conversation history (R7)
  artifactNote: 'You receive ONLY the code artifacts, the project memory, and the docs. The prior conversation is gone.',
  spec: (l) => `${langLabel(l)} — add OAuth login support to the system, preserving all existing behavior. ${SHARED.replace('__LANG__', langLabel(l))}`,
}

export function langComment(lang) {
  return { py: '#', ts: '//', rust: '//' }[lang]
}
