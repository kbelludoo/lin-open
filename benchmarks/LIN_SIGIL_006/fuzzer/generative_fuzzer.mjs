import { createPRNG } from '../../LIN_MEM_001/dataset/generate.mjs';

export function generateCombinatorialCorpus(seed = 987654) {
  const rand = createPRNG(seed);
  const corpus = [];

  const effectOptions = ['Pure', 'IO', 'HeapMut'];

  for (let p = 1; p <= 50; p++) {
    const progId = `gen_prog_${String(p).padStart(3, '0')}`;
    const numFns = 2 + Math.floor(rand() * 2); // 2 or 3 functions
    const fns = [];

    // Generate functions
    for (let f = 1; f <= numFns; f++) {
      const fnName = `fn_${f}`;
      const eff = rand() < 0.75 ? 'Pure' : effectOptions[Math.floor(rand() * 3)];
      const hasPre = rand() < 0.8;
      const hasPost = rand() < 0.8;

      const contracts = [];
      if (hasPre) {
        contracts.push({ kind: 'pre', expr: 'a > 0 && b > 0' });
      }
      if (hasPost) {
        contracts.push({ kind: 'post', expr: 'result >= a' });
      }

      let body = '^(a + b)';
      let calls = null;

      // If fn_1 and multiple functions exist, chain call to fn_2
      if (f === 1 && numFns > 1) {
        calls = { target: 'fn_2', args: (args) => ({ a: args.a, b: args.b }) };
        body = '^fn_2(a, b)';
      }

      fns.push({
        name: fnName,
        params: [{ name: 'a', type: 'i32' }, { name: 'b', type: 'i32' }],
        returnType: 'i32',
        effects: [eff],
        contracts,
        body,
        calls
      });
    }

    // Generate input args
    const isInvalidPre = (p % 4 === 0);
    const args = isInvalidPre ? { a: -5, b: 10 } : { a: 10 + (p * 2), b: 5 + p };

    // Format LIN source
    let linSource = `@LIN:L1c:0.2\n~G{?=if #=for ^=ret :else %=contract *=effect}\n\n`;
    for (const fn of fns) {
      linSource += `!${fn.name}(a: i32, b: i32) -> i32\n`;
      for (const c of fn.contracts) {
        linSource += `  %(${c.kind}: ${c.expr})\n`;
      }
      linSource += `  *(${fn.effects[0]})\n`;
      linSource += `{\n  ${fn.body}\n}\n\n`;
    }

    corpus.push({
      prog_id: progId,
      entry_fn: 'fn_1',
      ast: { protocol: 'LIN_TYPED_IR/2.0', functions: fns },
      lin_source: linSource,
      args
    });
  }

  return corpus;
}
