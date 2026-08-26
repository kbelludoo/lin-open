/**
 * build_dataset.mjs — Gerador determinístico dos 30 casos de teste e 30 oráculos independentes
 */

import fs from 'fs';
import path from 'path';
import { createHash } from 'crypto';

const BASE_DIR = '/home/k/Downloads/lin-master/benchmarks/cognitive_ablation';
const TASKS_DIR = path.join(BASE_DIR, 'tasks');
const ORACLES_DIR = path.join(BASE_DIR, 'oracles');

fs.mkdirSync(TASKS_DIR, { recursive: true });
fs.mkdirSync(ORACLES_DIR, { recursive: true });

const taskDefinitions = [
  // ==========================================
  // FAMÍLIA 1: Lógica / Estado (T001–T006)
  // ==========================================
  {
    id: 'T001',
    family: 'logic_state',
    difficulty: 'easy',
    specification: 'Implemente uma máquina de estados finita pura para semáforo. Entrada: estado atual ("RED", "GREEN", "YELLOW"). Saída: próximo estado ("GREEN", "YELLOW", "RED"). Qualquer outro estado deve retornar "ERROR".',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut', 'console.log', 'process.'],
    test_cases: [
      { input: 'RED', expected: 'GREEN' },
      { input: 'GREEN', expected: 'YELLOW' },
      { input: 'YELLOW', expected: 'RED' },
      { input: 'BLUE', expected: 'ERROR' }
    ],
    oracle_logic: `
      const m = { RED: 'GREEN', GREEN: 'YELLOW', YELLOW: 'RED' };
      return fn(input) === (m[input] || 'ERROR');
    `,
    correct_solution: `!solve(state){?(state=="RED"){\n^"GREEN"\n}:(state=="GREEN"){\n^"YELLOW"\n}:(state=="YELLOW"){\n^"RED"\n}:{\n^"ERROR"\n}}`
  },
  {
    id: 'T002',
    family: 'logic_state',
    difficulty: 'medium',
    specification: 'Implemente push puro em um ring buffer de capacidade 3. Entrada: { buffer: array, item: any }. Saída: novo array com no máximo 3 itens (se exceder, remove o mais antigo da esquerda).',
    allowed_effects: [],
    forbidden_effects: ['buffer.push', 'buffer.shift', 'globalState'],
    test_cases: [
      { input: { buffer: [1, 2], item: 3 }, expected: [1, 2, 3] },
      { input: { buffer: [1, 2, 3], item: 4 }, expected: [2, 3, 4] },
      { input: { buffer: [], item: 1 }, expected: [1] }
    ],
    oracle_logic: `
      const res = fn(input);
      const expected = [...input.buffer, input.item].slice(-3);
      return JSON.stringify(res) === JSON.stringify(expected);
    `,
    correct_solution: `!solve(data){\nb=data.buffer;\nitem=data.item;\nnb=[...b,item];\n?(nb.length>3){\n^nb.slice(nb.length-3)\n}:{\n^nb\n}\n}`
  },
  {
    id: 'T003',
    family: 'logic_state',
    difficulty: 'medium',
    specification: 'Implemente transição de pilha imutável com rollback. Entrada: { stack: array, action: "push"|"pop"|"rollback", value?: any, history: array }. Saída: { stack: array, history: array }.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut', 'splice'],
    test_cases: [
      { input: { stack: [1], action: 'push', value: 2, history: [[1]] }, expected: { stack: [1, 2], history: [[1], [1, 2]] } },
      { input: { stack: [1, 2], action: 'pop', history: [[1], [1, 2]] }, expected: { stack: [1], history: [[1], [1, 2], [1]] } },
      { input: { stack: [1, 2], action: 'rollback', history: [[1], [1, 2]] }, expected: { stack: [1], history: [[1]] } }
    ],
    oracle_logic: `
      const res = fn(input);
      if (input.action === 'push') {
        const nextStack = [...input.stack, input.value];
        return JSON.stringify(res) === JSON.stringify({ stack: nextStack, history: [...input.history, nextStack] });
      } else if (input.action === 'pop') {
        const nextStack = input.stack.slice(0, -1);
        return JSON.stringify(res) === JSON.stringify({ stack: nextStack, history: [...input.history, nextStack] });
      } else {
        const prevStack = input.history.length > 1 ? input.history[input.history.length - 2] : input.stack;
        const prevHist = input.history.slice(0, -1);
        return JSON.stringify(res) === JSON.stringify({ stack: prevStack, history: prevHist });
      }
    `,
    correct_solution: `!solve(d){\n?(d.action=="push"){\nns=[...d.stack,d.value];\n^{stack:ns,history:[...d.history,ns]}\n}:(d.action=="pop"){\nns=d.stack.slice(0,-1);\n^{stack:ns,history:[...d.history,ns]}\n}:{\nns=d.history.length>1?d.history[d.history.length-2]:d.stack;\n^{stack:ns,history:d.history.slice(0,-1)}\n}\n}`
  },
  {
    id: 'T004',
    family: 'logic_state',
    difficulty: 'hard',
    specification: 'União de intervalos numéricos sobrepostos. Entrada: array de intervalos [[inicio, fim], ...]. Saída: array de intervalos mesclados ordenados.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: [[1, 3], [2, 6], [8, 10], [15, 18]], expected: [[1, 6], [8, 10], [15, 18]] },
      { input: [[1, 4], [4, 5]], expected: [[1, 5]] },
      { input: [], expected: [] }
    ],
    oracle_logic: `
      const res = fn(input);
      if (!input.length) return Array.isArray(res) && res.length === 0;
      const sorted = [...input].sort((a, b) => a[0] - b[0]);
      const merged = [sorted[0]];
      for (let i = 1; i < sorted.length; i++) {
        const last = merged[merged.length - 1];
        const curr = sorted[i];
        if (curr[0] <= last[1]) {
          last[1] = Math.max(last[1], curr[1]);
        } else {
          merged.push(curr);
        }
      }
      return JSON.stringify(res) === JSON.stringify(merged);
    `,
    correct_solution: `!solve(intervals){\n?(intervals.length==0){\n^[]\n}\ns=[...intervals].sort((a,b)=>a[0]-b[0]);\nm=[[s[0][0],s[0][1]]];\n#(i=1;i<s.length;i++){\nlast=m[m.length-1];\nc=s[i];\n?(c[0]<=last[1]){\nlast[1]=last[1]>c[1]?last[1]:c[1]\n}:{\nm.push([c[0],c[1]])\n}\n}\n^m\n}`
  },
  {
    id: 'T005',
    family: 'logic_state',
    difficulty: 'easy',
    specification: 'Contador monotônico com teto. Entrada: { current: number, step: number, max: number }. Saída: number (current + step se <= max, senão max).',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: { current: 5, step: 2, max: 10 }, expected: 7 },
      { input: { current: 9, step: 3, max: 10 }, expected: 10 }
    ],
    oracle_logic: `return fn(input) === Math.min(input.max, input.current + input.step);`,
    correct_solution: `!solve(d){\nnext=d.current+d.step;\n^(next>d.max?d.max:next)\n}`
  },
  {
    id: 'T006',
    family: 'logic_state',
    difficulty: 'medium',
    specification: 'Validador de balanceamento de delimitadores (), [], {}. Entrada: string. Saída: boolean (true se balanceado, false caso contrário).',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'eval'],
    test_cases: [
      { input: '{[()]}', expected: true },
      { input: '{[(])}', expected: false },
      { input: '((()', expected: false },
      { input: '', expected: true }
    ],
    oracle_logic: `
      const res = fn(input);
      const stack = [];
      const map = { ')': '(', ']': '[', '}': '{' };
      let expected = true;
      for (const char of input) {
        if ('([{'.includes(char)) stack.push(char);
        else if (')]}'.includes(char)) {
          if (stack.pop() !== map[char]) { expected = false; break; }
        }
      }
      if (stack.length > 0) expected = false;
      return res === expected;
    `,
    correct_solution: `!solve(s){\nstack=[];\nm={")":"(","]":"[","}":"{"};\n#(i=0;i<s.length;i++){\nc=s[i];\n?("([{".includes(c)){\nstack.push(c)\n}\n?(")]}".includes(c)){\n?(stack.pop()!=m[c]){\n^false\n}\n}\n}\n^stack.length==0\n}`
  },

  // ==========================================
  // FAMÍLIA 2: Transformação de Código (T007–T012)
  // ==========================================
  {
    id: 'T007',
    family: 'code_transformation',
    difficulty: 'medium',
    specification: 'Flatten recursivo puro de arrays aninhados. Entrada: array aninhado de profundidade arbitrária. Saída: array plano com todos os elementos primitivos.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'Array.prototype.flat'],
    test_cases: [
      { input: [1, [2, [3, 4], 5], 6], expected: [1, 2, 3, 4, 5, 6] },
      { input: [[[]]], expected: [] },
      { input: [1, 2, 3], expected: [1, 2, 3] }
    ],
    oracle_logic: `
      const res = fn(input);
      function flat(arr) {
        let r = [];
        for (const item of arr) {
          if (Array.isArray(item)) r = r.concat(flat(item));
          else r.push(item);
        }
        return r;
      }
      return JSON.stringify(res) === JSON.stringify(flat(input));
    `,
    correct_solution: `!solve(arr){\nres=[];\nfunction flat(a){\n#(i=0;i<a.length;i++){\n?(Array.isArray(a[i])){\nflat(a[i])\n}:{\nres.push(a[i])\n}\n}\n}\nflat(arr);\n^res\n}`
  },
  {
    id: 'T008',
    family: 'code_transformation',
    difficulty: 'easy',
    specification: 'Compressão Run-Length Encoding (RLE). Entrada: string (ex: "AAABBBCC"). Saída: string codificada (ex: "3A3B2C"). Se string vazia, retorna "".',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: 'AAABBBCC', expected: '3A3B2C' },
      { input: 'A', expected: '1A' },
      { input: '', expected: '' }
    ],
    oracle_logic: `
      const res = fn(input);
      if (!input) return res === '';
      let exp = '', count = 1;
      for (let i = 1; i <= input.length; i++) {
        if (input[i] === input[i - 1]) count++;
        else { exp += count + input[i - 1]; count = 1; }
      }
      return res === exp;
    `,
    correct_solution: `!solve(s){\n?(!s){\n^""\n}\nres="";\ncount=1;\n#(i=1;i<=s.length;i++){\n?(s[i]==s[i-1]){\ncount++\n}:{\nres+=count+s[i-1];\ncount=1\n}\n}\n^res\n}`
  },
  {
    id: 'T009',
    family: 'code_transformation',
    difficulty: 'medium',
    specification: 'Transformação de objeto aninhado em chave-valor plano com dot-notation. Entrada: { a: { b: 1, c: { d: 2 } } }. Saída: { "a.b": 1, "a.c.d": 2 }.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: { a: { b: 1, c: { d: 2 } } }, expected: { 'a.b': 1, 'a.c.d': 2 } },
      { input: { x: 10 }, expected: { x: 10 } }
    ],
    oracle_logic: `
      const res = fn(input);
      function flatten(obj, prefix = '') {
        let acc = {};
        for (const [k, v] of Object.entries(obj)) {
          const path = prefix ? prefix + '.' + k : k;
          if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
            Object.assign(acc, flatten(v, path));
          } else {
            acc[path] = v;
          }
        }
        return acc;
      }
      return JSON.stringify(res) === JSON.stringify(flatten(input));
    `,
    correct_solution: `!solve(obj){\nout={};\nf=(o,p)=>{\nkeys=Object.keys(o);\n#(k=0;k<keys.length;k++){\nkey=keys[k];\nv=o[key];\nnp=p?p+"."+key:key;\n?(typeof v=="object"&&v!=null){\nf(v,np)\n}:{\nout[np]=v\n}\n}\n};\nf(obj,"");\n^out\n}`
  },
  {
    id: 'T010',
    family: 'code_transformation',
    difficulty: 'medium',
    specification: 'Normalizador de query params para objeto estruturado. Entrada: "a=1&b=test&c=true". Saída: { a: "1", b: "test", c: "true" } (vazio para string vazia).',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: 'a=1&b=test&c=true', expected: { a: '1', b: 'test', c: 'true' } },
      { input: '', expected: {} }
    ],
    oracle_logic: `
      const res = fn(input);
      if (!input) return typeof res === 'object' && Object.keys(res).length === 0;
      const expected = Object.fromEntries(input.split('&').map(p => p.split('=')));
      return JSON.stringify(res) === JSON.stringify(expected);
    `,
    correct_solution: `!solve(q){\n?(!q){\n^{}\n}\npairs=q.split("&");\nout={};\n#(i=0;i<pairs.length;i++){\nkv=pairs[i].split("=");\nout[kv[0]]=kv[1]\n}\n^out\n}`
  },
  {
    id: 'T011',
    family: 'code_transformation',
    difficulty: 'medium',
    specification: 'Deduplicação de array de objetos baseada em chave única "id". Entrada: [{id: 1, v: "a"}, {id: 1, v: "b"}, {id: 2, v: "c"}]. Saída: manter a primeira ocorrência.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: [{ id: 1, v: 'a' }, { id: 1, v: 'b' }, { id: 2, v: 'c' }], expected: [{ id: 1, v: 'a' }, { id: 2, v: 'c' }] }
    ],
    oracle_logic: `
      const res = fn(input);
      const seen = new Set();
      const exp = input.filter(item => { if (seen.has(item.id)) return false; seen.add(item.id); return true; });
      return JSON.stringify(res) === JSON.stringify(exp);
    `,
    correct_solution: `!solve(arr){\nseen={};\nout=[];\n#(i=0;i<arr.length;i++){\nit=arr[i];\n?(!seen[it.id]){\nseen[it.id]=true;\nout.push(it)\n}\n}\n^out\n}`
  },
  {
    id: 'T012',
    family: 'code_transformation',
    difficulty: 'easy',
    specification: 'Serializador determinístico de objeto com chaves ordenadas alfabeticamente. Entrada: objeto. Saída: string JSON canônica.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: { z: 1, a: 2, m: 3 }, expected: '{"a":2,"m":3,"z":1}' }
    ],
    oracle_logic: `
      const res = fn(input);
      const keys = Object.keys(input).sort();
      const exp = JSON.stringify(Object.fromEntries(keys.map(k => [k, input[k]])));
      return res === exp;
    `,
    correct_solution: `!solve(obj){\nkeys=Object.keys(obj).sort();\ns="{";\n#(i=0;i<keys.length;i++){\nk=keys[i];\ns+=JSON.stringify(k)+":"+JSON.stringify(obj[k]);\n?(i<keys.length-1){\ns+=","\n}\n}\ns+="}";\n^s\n}`
  },

  // ==========================================
  // FAMÍLIA 3: Efeitos / Contratos de Pureza (T013–T018)
  // ==========================================
  {
    id: 'T013',
    family: 'effects_contracts',
    difficulty: 'easy',
    specification: 'Ordenação pura de números. Entrada: array de números. Saída: novo array ordenado crescente SEM alterar o array de entrada.',
    allowed_effects: [],
    forbidden_effects: ['input.sort', 'globalState', 'mut'],
    test_cases: [
      { input: [3, 1, 4, 2], expected: [1, 2, 3, 4] }
    ],
    oracle_logic: `
      const clone = [...input];
      const res = fn(input);
      const isUnmutated = JSON.stringify(input) === JSON.stringify(clone);
      const isCorrect = JSON.stringify(res) === JSON.stringify([1, 2, 3, 4]);
      return isUnmutated && isCorrect;
    `,
    correct_solution: `!solve(arr){\n^[...arr].sort((a,b)=>a-b)\n}`
  },
  {
    id: 'T014',
    family: 'effects_contracts',
    difficulty: 'medium',
    specification: 'Validador de livro-razão (ledger) com garantia de soma zero. Entrada: array de transações [{ from, to, amount }]. Saída: boolean (true se total de saídas == total de entradas e todas positivas).',
    allowed_effects: [],
    forbidden_effects: ['db.write', 'network.send', 'globalState'],
    test_cases: [
      { input: [{ from: 'A', to: 'B', amount: 100 }, { from: 'B', to: 'C', amount: 100 }], expected: true },
      { input: [{ from: 'A', to: 'B', amount: -50 }], expected: false }
    ],
    oracle_logic: `
      const res = fn(input);
      const valid = input.every(t => t.amount > 0);
      return res === valid;
    `,
    correct_solution: `!solve(txs){\n#(i=0;i<txs.length;i++){\n?(txs[i].amount<=0){\n^false\n}\n}\n^true\n}`
  },
  {
    id: 'T015',
    family: 'effects_contracts',
    difficulty: 'medium',
    specification: 'Gerador Linear Congruencial puro (LCG). Entrada: { seed: number, a: number, c: number, m: number }. Saída: próximo número pseudo-aleatório (seed * a + c) % m.',
    allowed_effects: [],
    forbidden_effects: ['Math.random', 'Date.now', 'globalState'],
    test_cases: [
      { input: { seed: 42, a: 1664525, c: 1013904223, m: 4294967296 }, expected: 1083814273 }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = (input.seed * input.a + input.c) % input.m;
      return res === exp;
    `,
    correct_solution: `!solve(d){\n^(d.seed*d.a+d.c)%d.m\n}`
  },
  {
    id: 'T016',
    family: 'effects_contracts',
    difficulty: 'easy',
    specification: 'Sanitizador de strings puro (remove tags HTML). Entrada: string com tags HTML. Saída: string limpa sem tags.',
    allowed_effects: [],
    forbidden_effects: ['document.', 'window.', 'eval', 'globalState'],
    test_cases: [
      { input: '<p>Hello <b>World</b></p>', expected: 'Hello World' },
      { input: 'Simple text', expected: 'Simple text' }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = input.replace(/<[^>]*>/g, '');
      return res === exp;
    `,
    correct_solution: `!solve(s){\n^s.replace(/<[^>]*>/g,"")\n}`
  },
  {
    id: 'T017',
    family: 'effects_contracts',
    difficulty: 'hard',
    specification: 'Pipeline de cálculo de taxas imutável. Entrada: { base: number, rates: [number] }. Saída: valor final base * (1 + rate_1) * ... * (1 + rate_n) arredondado a 2 casas decimais.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut', 'db.'],
    test_cases: [
      { input: { base: 100, rates: [0.1, 0.05] }, expected: 115.50 }
    ],
    oracle_logic: `
      const res = fn(input);
      let total = input.base;
      for (const r of input.rates) total *= (1 + r);
      return Math.abs(res - Number(total.toFixed(2))) < 0.001;
    `,
    correct_solution: `!solve(d){\nt=d.base;\n#(i=0;i<d.rates.length;i++){\nt*=(1+d.rates[i])\n}\n^Number(t.toFixed(2))\n}`
  },
  {
    id: 'T018',
    family: 'effects_contracts',
    difficulty: 'easy',
    specification: 'Validador de contrato de tipo estrito. Entrada: any. Saída: string indicando o tipo semântico: "array", "null", "object", "number", "string", "boolean".',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: [1, 2], expected: 'array' },
      { input: null, expected: 'null' },
      { input: { a: 1 }, expected: 'object' },
      { input: 42, expected: 'number' }
    ],
    oracle_logic: `
      const res = fn(input);
      let exp = typeof input;
      if (input === null) exp = 'null';
      else if (Array.isArray(input)) exp = 'array';
      return res === exp;
    `,
    correct_solution: `!solve(x){\n?(x===null){\n^"null"\n}\n?(Array.isArray(x)){\n^"array"\n}\n^typeof x\n}`
  },

  // ==========================================
  // FAMÍLIA 4: Debugging / Reparo (T019–T024)
  // ==========================================
  {
    id: 'T019',
    family: 'debug_repair',
    difficulty: 'medium',
    specification: 'Busca binária corrigida. Entrada: { arr: array ordenado, target: number }. Saída: index do elemento ou -1 se não encontrado. (Evite loop infinito ou erro off-by-one).',
    allowed_effects: [],
    forbidden_effects: ['arr.indexOf', 'globalState'],
    test_cases: [
      { input: { arr: [10, 20, 30, 40, 50], target: 30 }, expected: 2 },
      { input: { arr: [10, 20, 30, 40, 50], target: 10 }, expected: 0 },
      { input: { arr: [10, 20, 30, 40, 50], target: 99 }, expected: -1 }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = input.arr.indexOf(input.target);
      return res === exp;
    `,
    correct_solution: `!solve(d){\na=d.arr;\nt=d.target;\nl=0;\nr=a.length-1;\n#(idx=0;l<=r;idx++){\nm=Math.floor((l+r)/2);\n?(a[m]==t){\n^m\n}\n?(a[m]<t){\nl=m+1\n}\n:{\nr=m-1\n}\n}\n^-1\n}`
  },
  {
    id: 'T020',
    family: 'debug_repair',
    difficulty: 'medium',
    specification: 'Cálculo de divisão segura com média. Entrada: array de números. Saída: média dos números ou 0 se o array estiver vazio.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: [10, 20, 30], expected: 20 },
      { input: [], expected: 0 }
    ],
    oracle_logic: `
      const res = fn(input);
      if (input.length === 0) return res === 0;
      const avg = input.reduce((a, b) => a + b, 0) / input.length;
      return Math.abs(res - avg) < 0.0001;
    `,
    correct_solution: `!solve(arr){\n?(arr.length==0){\n^0\n}\nsum=0;\n#(i=0;i<arr.length;i++){\nsum+=arr[i]\n}\n^sum/arr.length\n}`
  },
  {
    id: 'T021',
    family: 'debug_repair',
    difficulty: 'hard',
    specification: 'Clone profundo à prova de ciclos ou dados nested. Entrada: objeto { a: 1, b: { c: 2 } }. Saída: cópia exata desvinculada por referência.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: { a: 1, b: { c: 2 } }, expected: { a: 1, b: { c: 2 } } }
    ],
    oracle_logic: `
      const res = fn(input);
      const isIdentical = JSON.stringify(res) === JSON.stringify(input);
      const isDifferentRef = res !== input && res.b !== input.b;
      return isIdentical && isDifferentRef;
    `,
    correct_solution: `!solve(obj){\n^JSON.parse(JSON.stringify(obj))\n}`
  },
  {
    id: 'T022',
    family: 'debug_repair',
    difficulty: 'medium',
    specification: 'Compactador de array removendo falsy values (false, null, 0, "", undefined, NaN) exceto zero se configurado. Entrada: array. Saída: array filtrado sem null/undefined/"".',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: [0, 1, false, 2, '', 3, null, undefined], expected: [0, 1, 2, 3] }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = input.filter(x => x !== null && x !== undefined && x !== '' && x !== false);
      return JSON.stringify(res) === JSON.stringify(exp);
    `,
    correct_solution: `!solve(arr){\n^arr.filter(x=>x!==null&&x!==undefined&&x!==""&&x!==false)\n}`
  },
  {
    id: 'T023',
    family: 'debug_repair',
    difficulty: 'medium',
    specification: 'Comparador semântico de versões semânticas (SemVer "major.minor.patch"). Entrada: { v1: string, v2: string }. Saída: 1 se v1 > v2, -1 se v1 < v2, 0 se v1 == v2.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: { v1: '1.2.0', v2: '1.1.9' }, expected: 1 },
      { input: { v1: '2.0.0', v2: '2.0.0' }, expected: 0 },
      { input: { v1: '1.0.5', v2: '1.0.10' }, expected: -1 }
    ],
    oracle_logic: `
      const res = fn(input);
      const p1 = input.v1.split('.').map(Number);
      const p2 = input.v2.split('.').map(Number);
      let exp = 0;
      for (let i = 0; i < 3; i++) {
        if (p1[i] > p2[i]) { exp = 1; break; }
        if (p1[i] < p2[i]) { exp = -1; break; }
      }
      return res === exp;
    `,
    correct_solution: `!solve(d){\np1=d.v1.split(".").map(Number);\np2=d.v2.split(".").map(Number);\n#(i=0;i<3;i++){\n?(p1[i]>p2[i]){\n^1\n}:(p1[i]<p2[i]){\n^-1\n}\n}\n^0\n}`
  },
  {
    id: 'T024',
    family: 'debug_repair',
    difficulty: 'easy',
    specification: 'Sanitizador de chaves de objeto removendo chaves com valores undefined. Entrada: objeto. Saída: novo objeto sem chaves cujo valor é undefined.',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: { a: 1, b: undefined, c: 'ok' }, expected: { a: 1, c: 'ok' } }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = {};
      for (const [k, v] of Object.entries(input)) {
        if (v !== undefined) exp[k] = v;
      }
      return JSON.stringify(res) === JSON.stringify(exp);
    `,
    correct_solution: `!solve(obj){\nout={};\nkeys=Object.keys(obj);\n#(k=0;k<keys.length;k++){\nkey=keys[k];\n?(obj[key]!==undefined){\nout[key]=obj[key]\n}\n}\n^out\n}`
  },

  // ==========================================
  // FAMÍLIA 5: Composição Multi-Etapa (T025–T030)
  // ==========================================
  {
    id: 'T025',
    family: 'multi_step_composition',
    difficulty: 'hard',
    specification: 'Agregador estatístico multi-métrica. Entrada: array de números não vazio. Saída: { min: number, max: number, sum: number, avg: number }.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: [10, 20, 30], expected: { min: 10, max: 30, sum: 60, avg: 20 } }
    ],
    oracle_logic: `
      const res = fn(input);
      const min = Math.min(...input);
      const max = Math.max(...input);
      const sum = input.reduce((a, b) => a + b, 0);
      const avg = sum / input.length;
      return res.min === min && res.max === max && res.sum === sum && res.avg === avg;
    `,
    correct_solution: `!solve(a){\nmin=a[0];\nmax=a[0];\nsum=0;\n#(i=0;i<a.length;i++){\nv=a[i];\n?(v<min){\nmin=v\n}\n?(v>max){\nmax=v\n}\nsum+=v\n}\n^{min:min,max:max,sum:sum,avg:sum/a.length}\n}`
  },
  {
    id: 'T026',
    family: 'multi_step_composition',
    difficulty: 'hard',
    specification: 'Avaliador de expressões booleanas simples com tokens [op, arg1, arg2]. Entrada: ["AND", true, ["OR", false, true]]. Saída: boolean.',
    allowed_effects: [],
    forbidden_effects: ['eval', 'globalState'],
    test_cases: [
      { input: ['AND', true, ['OR', false, true]], expected: true },
      { input: ['NOT', true], expected: false }
    ],
    oracle_logic: `
      const res = fn(input);
      function evalExpr(e) {
        if (typeof e === 'boolean') return e;
        const [op, a, b] = e;
        if (op === 'NOT') return !evalExpr(a);
        if (op === 'AND') return evalExpr(a) && evalExpr(b);
        if (op === 'OR') return evalExpr(a) || evalExpr(b);
        return false;
      }
      return res === evalExpr(input);
    `,
    correct_solution: `!solve(e){\nev=(x)=>{\n?(typeof x=="boolean"){\n^x\n}\nop=x[0];\n?(op=="NOT"){\n^!ev(x[1])\n}:(op=="AND"){\n^ev(x[1])&&ev(x[2])\n}:(op=="OR"){\n^ev(x[1])||ev(x[2])\n}:{\n^false\n}\n};\n^ev(e)\n}`
  },
  {
    id: 'T027',
    family: 'multi_step_composition',
    difficulty: 'hard',
    specification: 'Diff estrutural entre dois objetos planos. Entrada: { oldObj: {}, newObj: {} }. Saída: { added: [keys], removed: [keys], updated: [keys] } (chaves ordenadas).',
    allowed_effects: [],
    forbidden_effects: ['globalState', 'mut'],
    test_cases: [
      { input: { oldObj: { a: 1, b: 2, c: 3 }, newObj: { b: 20, c: 3, d: 4 } }, expected: { added: ['d'], removed: ['a'], updated: ['b'] } }
    ],
    oracle_logic: `
      const res = fn(input);
      const oldKeys = Object.keys(input.oldObj);
      const newKeys = Object.keys(input.newObj);
      const added = newKeys.filter(k => !(k in input.oldObj)).sort();
      const removed = oldKeys.filter(k => !(k in input.newObj)).sort();
      const updated = newKeys.filter(k => (k in input.oldObj) && input.oldObj[k] !== input.newObj[k]).sort();
      return JSON.stringify(res) === JSON.stringify({ added, removed, updated });
    `,
    correct_solution: `!solve(d){\no=d.oldObj;\nn=d.newObj;\nok=Object.keys(o);\nnk=Object.keys(n);\nadd=nk.filter(k=>!(k in o)).sort();\nrem=ok.filter(k=>!(k in n)).sort();\nupd=nk.filter(k=>(k in o)&&o[k]!==n[k]).sort();\n^{added:add,removed:rem,updated:upd}\n}`
  },
  {
    id: 'T028',
    family: 'multi_step_composition',
    difficulty: 'medium',
    specification: 'Agrupamento (groupBy) de array de objetos por uma chave de propriedade. Entrada: { arr: [{cat: "A", val: 1}, {cat: "B", val: 2}, {cat: "A", val: 3}], key: "cat" }. Saída: objeto agrupado.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: { arr: [{ cat: 'A', val: 1 }, { cat: 'B', val: 2 }, { cat: 'A', val: 3 }], key: 'cat' }, expected: { A: [{ cat: 'A', val: 1 }, { cat: 'A', val: 3 }], B: [{ cat: 'B', val: 2 }] } }
    ],
    oracle_logic: `
      const res = fn(input);
      const exp = {};
      for (const item of input.arr) {
        const k = item[input.key];
        if (!exp[k]) exp[k] = [];
        exp[k].push(item);
      }
      return JSON.stringify(res) === JSON.stringify(exp);
    `,
    correct_solution: `!solve(d){\nout={};\n#(i=0;i<d.arr.length;i++){\nit=d.arr[i];\nk=it[d.key];\n?(!out[k]){\nout[k]=[]\n};\nout[k].push(it)\n}\n^out\n}`
  },
  {
    id: 'T029',
    family: 'multi_step_composition',
    difficulty: 'hard',
    specification: 'Motor de regras de acesso (ACL). Entrada: { user: { role, permissions }, resource: string, action: string, rules: [{ role, resource, action, allow }] }. Saída: boolean.',
    allowed_effects: [],
    forbidden_effects: ['globalState'],
    test_cases: [
      { input: { user: { role: 'admin' }, resource: 'file', action: 'delete', rules: [{ role: 'admin', resource: '*', action: '*', allow: true }] }, expected: true },
      { input: { user: { role: 'guest' }, resource: 'file', action: 'delete', rules: [{ role: 'admin', resource: '*', action: '*', allow: true }, { role: 'guest', resource: 'file', action: 'read', allow: true }] }, expected: false }
    ],
    oracle_logic: `
      const res = fn(input);
      let allowed = false;
      for (const r of input.rules) {
        const roleMatch = r.role === '*' || r.role === input.user.role;
        const resMatch = r.resource === '*' || r.resource === input.resource;
        const actMatch = r.action === '*' || r.action === input.action;
        if (roleMatch && resMatch && actMatch) {
          allowed = r.allow;
        }
      }
      return res === allowed;
    `,
    correct_solution: `!solve(d){\nal=false;\n#(i=0;i<d.rules.length;i++){\nr=d.rules[i];\nrm=r.role=="*"||r.role==d.user.role;\nsm=r.resource=="*"||r.resource==d.resource;\nam=r.action=="*"||r.action==d.action;\n?(rm&&sm&&am){\nal=r.allow\n}\n}\n^al\n}`
  },
  {
    id: 'T030',
    family: 'multi_step_composition',
    difficulty: 'hard',
    specification: 'Roundtrip de tokenização semântica: divide string em tokens [TIPO, VALOR] para números, identificadores e operadores (+, -, *, /). Entrada: "x + 42". Saída: [["ID","x"], ["OP","+"], ["NUM","42"]].',
    allowed_effects: [],
    forbidden_effects: ['eval', 'globalState'],
    test_cases: [
      { input: 'x + 42', expected: [['ID', 'x'], ['OP', '+'], ['NUM', '42']] }
    ],
    oracle_logic: `
      const res = fn(input);
      const tokens = [];
      const parts = input.trim().split(/\\s+/);
      for (const p of parts) {
        if (!isNaN(Number(p))) tokens.push(['NUM', p]);
        else if (['+', '-', '*', '/'].includes(p)) tokens.push(['OP', p]);
        else tokens.push(['ID', p]);
      }
      return JSON.stringify(res) === JSON.stringify(tokens);
    `,
    correct_solution: `!solve(s){\nparts=s.trim().split(/\\s+/);\nout=[];\n#(i=0;i<parts.length;i++){\np=parts[i];\n?(!isNaN(Number(p))){\nout.push(["NUM",p])\n}\n?(["+","-","*","/"].includes(p)){\nout.push(["OP",p])\n}\n?(isNaN(Number(p))&&!["+","-","*","/"].includes(p)){\nout.push(["ID",p])\n}\n}\n^out\n}`
  }
];

// 1. Gravar cada tarefa individual e oráculo individual
const manifestEntries = [];

for (const t of taskDefinitions) {
  const taskObj = {
    id: t.id,
    family: t.family,
    difficulty: t.difficulty,
    specification: t.specification,
    allowed_effects: t.allowed_effects,
    forbidden_effects: t.forbidden_effects,
    test_cases: t.test_cases,
    oracle: {
      type: 'deterministic_unit',
      entrypoint: `oracles/oracle_${t.id}.mjs`
    }
  };

  const taskJsonStr = JSON.stringify(taskObj, null, 2);
  fs.writeFileSync(path.join(TASKS_DIR, `${t.id}.json`), taskJsonStr);

  const oracleCode = `/**
 * oracle_${t.id}.mjs — Oráculo independente para ${t.id} (${t.family})
 */
function transpile(code) {
  let clean = code.replace(/@LIN:[^\\n]+\\n/g, '').replace(/=ex\\{[^\\}]+\\}/g, '').trim();
  clean = clean.replace(/!([a-zA-Z0-9_]+)\\(([^)]*)\\)\\s*\\{/g, 'function $1($2){');
  clean = clean.replace(/\\^([^;\\n\\}]+)/g, 'return $1');

  let out = '';
  let i = 0;
  while (i < clean.length) {
    // Strings literais
    if (clean[i] === '"' || clean[i] === "'" || clean[i] === '\`') {
      const q = clean[i];
      out += q;
      i++;
      while (i < clean.length && clean[i] !== q) {
        if (clean[i] === '\\\\') {
          out += clean[i] + (clean[i + 1] || '');
          i += 2;
        } else {
          out += clean[i];
          i++;
        }
      }
      if (i < clean.length) {
        out += clean[i];
        i++;
      }
      continue;
    }

    if (clean[i] === '?' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      let inStr = null;
      while (j < clean.length && depth > 0) {
        const c = clean[j];
        if (inStr) {
          if (c === '\\\\') j += 2;
          else if (c === inStr) { inStr = null; j++; }
          else j++;
          continue;
        }
        if (c === '"' || c === "'" || c === '\`') { inStr = c; j++; continue; }
        if (c === '(') depth++;
        else if (c === ')') depth--;
        j++;
      }
      const cond = clean.slice(i + 2, j - 1);
      while (j < clean.length && /\\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        out += \`if (\${cond}) {\`;
        i = j + 1;
        continue;
      }
    }

    if (clean[i] === ':' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      let inStr = null;
      while (j < clean.length && depth > 0) {
        const c = clean[j];
        if (inStr) {
          if (c === '\\\\') j += 2;
          else if (c === inStr) { inStr = null; j++; }
          else j++;
          continue;
        }
        if (c === '"' || c === "'" || c === '\`') { inStr = c; j++; continue; }
        if (c === '(') depth++;
        else if (c === ')') depth--;
        j++;
      }
      const cond = clean.slice(i + 2, j - 1);
      while (j < clean.length && /\\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        out += \`else if (\${cond}) {\`;
        i = j + 1;
        continue;
      }
    }

    if (clean[i] === ':' && clean[i + 1] === '{') {
      out += 'else {';
      i += 2;
      continue;
    }

    if (clean[i] === '#' && clean[i + 1] === '(') {
      let depth = 1;
      let j = i + 2;
      while (j < clean.length && depth > 0) {
        if (clean[j] === '(') depth++;
        else if (clean[j] === ')') depth--;
        j++;
      }
      const loopParts = clean.slice(i + 2, j - 1).split(';');
      while (j < clean.length && /\\s/.test(clean[j])) j++;
      if (clean[j] === '{') {
        if (loopParts.length === 3) {
          const init = loopParts[0].trim();
          const initStr = init ? (init.includes('=') && !init.startsWith('let ') ? \`let \${init}\` : init) : '';
          out += \`for (\${initStr}; \${loopParts[1].trim()}; \${loopParts[2].trim()}) {\`;
        } else {
          out += \`for (\${loopParts.join(';')}) {\`;
        }
        i = j + 1;
        continue;
      }
    }

    out += clean[i];
    i++;
  }
  return out;
}

export async function oracle(task, candidateResult) {
  try {
    const jsSource = transpile(candidateResult.candidate_code);
    const fn = new Function('input', \`
      \${jsSource}
      return solve(input);
    \`);

    for (const tc of task.test_cases) {
      const input = tc.input;
      const testPassed = (() => {
        ${t.oracle_logic}
      })();
      if (!testPassed) {
        return { passed: false, hint: 'Falha no caso de teste: ' + JSON.stringify(tc) };
      }
    }
    return { passed: true };
  } catch (err) {
    return { passed: false, hint: err.message };
  }
}
`;
  fs.writeFileSync(path.join(ORACLES_DIR, `oracle_${t.id}.mjs`), oracleCode);

  const taskHash = createHash('sha256').update(taskJsonStr).digest('hex');
  manifestEntries.push({
    id: t.id,
    family: t.family,
    difficulty: t.difficulty,
    sha256: taskHash,
    oracle_entrypoint: `oracles/oracle_${t.id}.mjs`
  });
}

// 2. Gravar task_solutions.json para uso nos testes de validação controlados
const solutionsMap = {};
for (const t of taskDefinitions) {
  solutionsMap[t.id] = t.correct_solution;
}
fs.writeFileSync(path.join(BASE_DIR, 'task_solutions.json'), JSON.stringify(solutionsMap, null, 2));

// 3. Gravar MANIFEST.json com hash global
const manifestObj = {
  manifest_version: '1.0.0',
  dataset_id: 'COGNITIVE_ABLATION_DATASET_V1',
  timestamp: '2026-08-18T00:00:00.000Z',
  total_tasks: manifestEntries.length,
  tasks: manifestEntries
};

const manifestJsonStr = JSON.stringify(manifestObj, null, 2);
const globalSha256 = createHash('sha256').update(manifestJsonStr).digest('hex');
manifestObj.global_sha256 = globalSha256;

fs.writeFileSync(path.join(BASE_DIR, 'MANIFEST.json'), JSON.stringify(manifestObj, null, 2));

console.log(`✅ Dataset gerado com sucesso: ${manifestEntries.length} tarefas e oráculos.`);
console.log(`🔒 SHA-256 Global do Manifesto: ${globalSha256}`);
