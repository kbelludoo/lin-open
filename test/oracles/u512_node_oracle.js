#!/usr/bin/env node
/* Independent Node.js BigInt oracle (not TCB). FullMath width, not CRT/mulmod. */
"use strict";

const fs = require("fs");
const UMAX = (1n << 256n) - 1n;

function parseHex(s) {
  if (!s) return 0n;
  if (s.startsWith("0x") || s.startsWith("0X")) s = s.slice(2);
  if (s.length === 0) return 0n;
  return BigInt("0x" + s);
}

function hex32(n) {
  let v = BigInt(n);
  if (v < 0n) throw new Error("negative");
  return v.toString(16).padStart(64, "0");
}

function muldiv(a, b, d) {
  if (d === 0n) return { st: -1, q: 0n, r: 0n };
  const n = a * b;
  const q = n / d;
  const r = n % d;
  if (q > UMAX) return { st: -2, q: 0n, r: 0n };
  if (q * d + r !== n || r >= d) {
    process.stderr.write("FAIL remainder identity\n");
    process.exit(1);
  }
  return { st: 1, q, r };
}

function selftest() {
  const md = muldiv(7n, 9n, 2n);
  if (md.st !== 1 || md.q !== 31n || md.r !== 1n) {
    process.stderr.write("FAIL 7*9/2\n");
    return 1;
  }
  const n = UMAX * UMAX;
  if ((n & UMAX) !== 1n || (n >> 256n) !== UMAX - 1n) {
    process.stderr.write("FAIL max^2\n");
    return 1;
  }
  const t = muldiv(1n << 255n, 2n, 3n);
  if (t.st !== 1 || t.r !== 1n || t.q !== 0x5555555555555555555555555555555555555555555555555555555555555555n) {
    process.stderr.write("FAIL 2^255*2/3\n");
    return 1;
  }
  if (muldiv(1n, 1n, 0n).st !== -1) {
    process.stderr.write("FAIL d=0\n");
    return 1;
  }
  if (muldiv(1n << 255n, 2n, 1n).st !== -2) {
    process.stderr.write("FAIL q overflow\n");
    return 1;
  }
  const gao = muldiv(997000n, 20000n, 10997000n);
  if (gao.st !== 1 || gao.q !== 1813n) {
    process.stderr.write("FAIL 1813\n");
    return 1;
  }
  const two256 = 1n << 256n;
  const umax = UMAX;
  if (!(two256 >= umax) || (umax >= two256) || !(0n >= 0n)) {
    process.stderr.write("FAIL ge512\n");
    return 1;
  }
  process.stdout.write("SELFTEST_PASS node_bigint q*d+r==n ge512\n");
  return 0;
}

function batch() {
  const text = fs.readFileSync(0, "utf8");
  let nvec = 0;
  for (const line of text.split(/\n/)) {
    const t = line.trim();
    if (!t) continue;
    const p = t.split(/\s+/);
    if (p[0] === "MUL") {
      const a = parseHex(p[1]);
      const b = parseHex(p[2]);
      const n = a * b;
      process.stdout.write("1 " + hex32(n & UMAX) + " " + hex32(n >> 256n) + "\n");
    } else if (p[0] === "MULDIV") {
      const a = parseHex(p[1]);
      const b = parseHex(p[2]);
      const d = parseHex(p[3]);
      const r = muldiv(a, b, d);
      process.stdout.write(String(r.st) + " " + hex32(r.q) + " " + hex32(r.r) + "\n");
    } else if (p[0] === "GE") {
      const a = parseHex(p[1]);
      const b = parseHex(p[2]);
      process.stdout.write((a >= b ? "1" : "0") + "\n");
    } else {
      process.stderr.write("unknown op " + p[0] + "\n");
      return 1;
    }
    nvec += 1;
  }
  process.stderr.write("BATCH_N=" + nvec + " NODE_BIGINT_CONSENSUS\n");
  return 0;
}

if (process.argv[2] === "--self-test") process.exit(selftest());
if (process.argv[2] === "--batch") process.exit(batch());
process.stderr.write("usage: u512_node_oracle.js --self-test | --batch\n");
process.exit(2);
