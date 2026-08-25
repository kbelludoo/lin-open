/**
 * LIA → JavaScript emitter (canonical working path).
 * Fail-closed: compileLiaToJs runs node --check; illegal JS is never OK.
 */
import { compileLiaToJs } from './compiler.mjs';

export function emitJs(liaText, opts = {}) {
  const { js, program } = compileLiaToJs(liaText, opts);
  return { code: js, program, target: 'js' };
}
