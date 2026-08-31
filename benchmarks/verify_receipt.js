#!/usr/bin/env node
/**
 * Independent LIN compute-receipt verifier (Node.js, no dependencies).
 *
 * Zero-trust: recomputes the receipt Merkle root with the built-in `crypto`
 * module (SHA-256, NIST FIPS 180-4) — no LIN compiler/runtime involved.
 *
 * Open receipt format (LIN_COMPUTE_RECEIPT_1.0):
 *   leaf[0:32]  = SHA-256(source code)                ("artifact")
 *   leaf[32:40] = output   (i64, little-endian)
 *   leaf[40:48] = steps    (u64, little-endian)
 *   leaf[48:56] = sp_at_ret (u64, little-endian)
 *   leaf[56:64] = input    (i64, little-endian)
 *   merkle_root = SHA-256(leaf)
 *
 * Usage:
 *   node verify_receipt.js receipt.json
 *   node verify_receipt.js receipt.rulel
 *   node verify_receipt.js receipt.json "return x * x;"   // optional source check
 * Exit code: 0 = PASS, 1 = FAIL.
 */
'use strict';

const crypto = require('crypto');
const fs = require('fs');

const file = process.argv[2];
const source = process.argv[3];
if (!file) {
  console.error('usage: node verify_receipt.js <receipt.json|receipt.rulel> [source-code]');
  process.exit(2);
}

class ReceiptError extends Error {}

function stripSha256(s) {
  return s.startsWith('sha256:') ? s.slice(7) : s;
}

function parseReceipt(txt) {
  const t = txt.trim();
  if (t.startsWith('{')) {
    const d = JSON.parse(t);
    if (typeof d !== 'object' || d === null || Array.isArray(d)) {
      throw new ReceiptError('JSON root must be an object');
    }
    for (const k of ['artifact', 'input', 'output', 'steps', 'sp_at_ret', 'merkle_root']) {
      if (!(k in d)) throw new ReceiptError(`missing field "${k}"`);
    }
    return {
      artifact: String(d.artifact),
      input: String(d.input),
      output: String(d.output),
      steps: BigInt(d.steps),
      sp_at_ret: BigInt(d.sp_at_ret),
      merkle_root: String(d.merkle_root),
    };
  }
  // RULEL
  const get = (tag) => {
    for (const line of t.split('\n')) {
      const s = line.trim();
      if (s.startsWith(tag)) return s.slice(tag.length).trim().replace(/^"|"$/g, '');
    }
    return null;
  };
  const a = get('.a='), i = get('.i='), o = get('.o='),
        s = get('.s='), p = get('.p='), m = get('.m=');
  if ([a, i, o, s, p, m].some((v) => v === null || v === '')) {
    throw new ReceiptError('missing RULEL field(s) (.a/.i/.o/.s/.p/.m)');
  }
  return {
    artifact: a, input: i, output: o,
    steps: BigInt(s), sp_at_ret: BigInt(p), merkle_root: m,
  };
}

function buildLeaf(f) {
  const artHex = stripSha256(f.artifact);
  if (!/^[0-9a-fA-F]{64}$/.test(artHex)) {
    throw new ReceiptError('artifact is not a 32-byte SHA-256 hex digest');
  }
  const art = Buffer.from(artHex, 'hex');
  if (art.length !== 32) throw new ReceiptError('artifact must be 32 bytes');

  const leaf = Buffer.alloc(64);
  art.copy(leaf, 0);
  leaf.writeBigInt64LE(BigInt(f.output), 32);
  leaf.writeBigUInt64LE(BigInt(f.steps), 40);
  leaf.writeBigUInt64LE(BigInt(f.sp_at_ret), 48);
  leaf.writeBigInt64LE(BigInt(f.input), 56);
  return leaf;
}

function main() {
  const txt = fs.readFileSync(file, 'utf8');
  const f = parseReceipt(txt);
  const computed = crypto.createHash('sha256').update(buildLeaf(f)).digest('hex');
  const claimed = stripSha256(f.merkle_root);

  const line = '='.repeat(72);
  console.log(line);
  console.log('   INDEPENDENT LIN RECEIPT VERIFIER (Node.js crypto)');
  console.log(line);
  console.log(`  Artifact     : sha256:${stripSha256(f.artifact)}`);
  console.log(`  Input        : ${f.input}`);
  console.log(`  Output       : ${f.output}`);
  console.log(`  Steps        : ${f.steps}`);
  console.log(`  SP at ret    : ${f.sp_at_ret}`);
  console.log(`  Merkle (file): sha256:${claimed}`);
  console.log(`  Merkle (calc): sha256:${computed}`);

  let ok = computed === claimed;
  if (source !== undefined) {
    const srcHash = crypto.createHash('sha256').update(source, 'utf8').digest('hex');
    const srcOk = srcHash === stripSha256(f.artifact);
    console.log(`  Source check : ${srcOk ? 'PASS (artifact matches source)' : 'FAIL (artifact != SHA-256(source))'}`);
    ok = ok && srcOk;
  }

  if (ok) {
    console.log(`  [PASS] Receipt validated by an independent open-source verifier`);
  } else {
    console.log(`  [FAIL] Receipt forged or tampered! calculated=${computed} claimed=${claimed}`);
  }
  console.log(line);
  process.exit(ok ? 0 : 1);
}

try {
  main();
} catch (e) {
  console.error(`[FAIL] ${e.message}`);
  process.exit(1);
}
