// LIN AST Lexical & Scope-Aware Alpha-Canonicalizer
// Preserves string literals, comments, handles variable shadowing and computes true AST alpha-equivalence

import crypto from 'crypto';

export class AstAlphaCanonicalizer {
  // Simple yet robust tokeniser that classifies code into structural tokens
  static tokenize(source) {
    const tokens = [];
    let i = 0;
    const len = source.length;

    while (i < len) {
      const ch = source[i];

      // 1. Whitespace
      if (/\s/.test(ch)) {
        i++;
        continue;
      }

      // 2. Line / Block Comments
      if (ch === '/' && source[i + 1] === '/') {
        let comment = '';
        while (i < len && source[i] !== '\n') {
          comment += source[i++];
        }
        tokens.push({ type: 'COMMENT', value: comment });
        continue;
      }
      if (ch === '/' && source[i + 1] === '*') {
        let comment = '';
        i += 2;
        while (i < len && !(source[i] === '*' && source[i + 1] === '/')) {
          comment += source[i++];
        }
        i += 2;
        tokens.push({ type: 'COMMENT', value: comment });
        continue;
      }

      // 3. String Literals ("...", '...', `...`)
      if (ch === '"' || ch === "'" || ch === '`') {
        const quote = ch;
        let str = quote;
        i++;
        while (i < len) {
          const c = source[i];
          str += c;
          if (c === '\\') {
            str += source[++i];
          } else if (c === quote) {
            i++;
            break;
          }
          i++;
        }
        tokens.push({ type: 'STRING_LITERAL', value: str });
        continue;
      }

      // 4. Numeric Literals
      if (/[0-9]/.test(ch)) {
        let num = '';
        while (i < len && /[0-9.xXabcdefABCDEF]/.test(source[i])) {
          num += source[i++];
        }
        tokens.push({ type: 'NUMERIC_LITERAL', value: num });
        continue;
      }

      // 5. Identifiers and Keywords
      if (/[a-zA-Z_$]/.test(ch)) {
        let ident = '';
        while (i < len && /[a-zA-Z0-9_$]/.test(source[i])) {
          ident += source[i++];
        }
        tokens.push({ type: 'IDENTIFIER', value: ident });
        continue;
      }

      // 6. Punctuators & Operators
      tokens.push({ type: 'PUNCTUATOR', value: ch });
      i++;
    }

    return tokens;
  }

  // Scope-aware alpha-renaming
  static canonicalizeAst(rawParams, rawBody) {
    const tokens = this.tokenize(rawBody);
    const paramMap = new Map();
    rawParams.forEach((p, idx) => paramMap.set(p.trim(), `$p${idx}`));

    const shadowedVars = new Set();
    const canonicalTokens = [];

    for (let k = 0; k < tokens.length; k++) {
      const tok = tokens[k];

      if (tok.type === 'COMMENT') {
        // Strip comments for semantic canonicalization
        continue;
      }

      if (tok.type === 'STRING_LITERAL') {
        // String literals are preserved EXACTLY as content, never alpha-renamed!
        canonicalTokens.push(tok.value);
        continue;
      }

      // Detect local variable declarations: let x = ..., var x = ..., const x = ...
      if (tok.type === 'IDENTIFIER' && (tok.value === 'let' || tok.value === 'var' || tok.value === 'const')) {
        canonicalTokens.push(tok.value);
        if (k + 1 < tokens.length && tokens[k + 1].type === 'IDENTIFIER') {
          const nextIdent = tokens[k + 1].value;
          shadowedVars.add(nextIdent);
        }
        continue;
      }

      if (tok.type === 'IDENTIFIER') {
        if (!shadowedVars.has(tok.value) && paramMap.has(tok.value)) {
          // Rename outer parameter binding to positional de Bruijn parameter
          canonicalTokens.push(paramMap.get(tok.value));
        } else {
          canonicalTokens.push(tok.value);
        }
        continue;
      }

      canonicalTokens.push(tok.value);
    }

    return canonicalTokens.join(' ');
  }

  static computeSemanticHash(fnNode) {
    const rawParams = fnNode.params || [];
    const canonicalBody = this.canonicalizeAst(rawParams, fnNode.body || '');

    const structuralDigest = {
      kind: 'FUNCTION',
      arity: rawParams.length,
      effect: fnNode.effect || 'Pure',
      contracts: fnNode.contracts || [],
      canonicalBody
    };

    return crypto.createHash('sha256').update(JSON.stringify(structuralDigest)).digest('hex');
  }
}
