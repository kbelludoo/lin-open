#!/usr/bin/env node
/**
 * Independent LNR1 verifier — Node.js crypto only, no LIN runtime.
 * Same 240-byte records / domains as verify_u512_receipt.py.
 * Tamper-evidence + remainder identity. Not zk.
 */
"use strict";
const crypto = require("crypto");
const fs = require("fs");

const DOM_LEAF = Buffer.from("LIN:U512:LEAF:1");
const DOM_NODE = Buffer.from("LIN:U512:NODE:1");
const MAGIC = Buffer.from("LNR1");
const REC = 240;
const U256 = (1n << 256n) - 1n;

function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest();
}
function leafHash(rec) {
  return sha256(Buffer.concat([DOM_LEAF, rec]));
}
function parentHash(l, r) {
  return sha256(Buffer.concat([DOM_NODE, l, r]));
}
function merkleRoot(leaves) {
  let cur = leaves.slice();
  if (!cur.length) return sha256(Buffer.alloc(0));
  while (cur.length > 1) {
    const nxt = [];
    for (let i = 0; i < cur.length; i += 2) {
      nxt.push(parentHash(cur[i], i + 1 < cur.length ? cur[i + 1] : cur[i]));
    }
    cur = nxt;
  }
  return cur[0];
}
function be32(buf) {
  return BigInt("0x" + buf.toString("hex"));
}
function u64le(buf, off) {
  return buf.readBigUInt64LE(off);
}
function i64le(buf, off) {
  return buf.readBigInt64LE(off);
}
function parseRecord(raw) {
  if (raw.length !== REC) throw new Error("bad_len");
  if (raw.subarray(0, 4).compare(MAGIC) !== 0 || raw[4] !== 1 || raw[5] !== 1) {
    throw new Error("bad_header");
  }
  return {
    image: raw.subarray(8, 40).toString("hex"),
    a: be32(raw.subarray(56, 88)),
    b: be32(raw.subarray(88, 120)),
    d: be32(raw.subarray(120, 152)),
    q: be32(raw.subarray(152, 184)),
    r: be32(raw.subarray(184, 216)),
    steps: u64le(raw, 216),
    status: Number(i64le(raw, 224)),
  };
}
function identityOk(rec) {
  const n = rec.a * rec.b;
  if (rec.status === -1) return rec.d === 0n;
  if (rec.status === -2) return rec.d !== 0n && n / rec.d > U256;
  if (rec.status !== 1) return false;
  if (rec.d === 0n || rec.q > U256 || rec.r >= rec.d) return false;
  return rec.q * rec.d + rec.r === n && n / rec.d === rec.q && n % rec.d === rec.r;
}
function verifyBundle(data) {
  const recs = data.records;
  const rootHex = data.merkle_root_sha256;
  const img = data.image_loader_digest;
  if (!Array.isArray(recs) || !recs.length) return { valid: false, reason: "NO_RECORDS" };
  if (typeof rootHex !== "string" || rootHex.length !== 64) return { valid: false, reason: "BAD_ROOT" };
  const leaves = [];
  for (let i = 0; i < recs.length; i++) {
    const raw = Buffer.from(recs[i].raw_record_hex, "hex");
    const parsed = parseRecord(raw);
    if (img && parsed.image !== img) return { valid: false, reason: "BAD_IMAGE_DIGEST", leaf: i };
    if (recs[i].leaf_hash_hex && recs[i].leaf_hash_hex !== leafHash(raw).toString("hex")) {
      return { valid: false, reason: "BAD_LEAF_HASH", leaf: i };
    }
    if (!identityOk(parsed)) return { valid: false, reason: "BAD_IDENTITY", leaf: i };
    leaves.push(leafHash(raw));
  }
  const got = merkleRoot(leaves).toString("hex");
  if (got !== rootHex) return { valid: false, reason: "BAD_ROOT", computed: got };
  return { valid: true, reason: "OK", leaves: leaves.length, merkle_root_sha256: got };
}
function packU256(n) {
  return Buffer.from(n.toString(16).padStart(64, "0"), "hex");
}
function demoRecord(leafId, a, b, d, img) {
  const n = a * b;
  let st, q, r;
  if (d === 0n) {
    st = -1n; q = 0n; r = 0n;
  } else {
    q = n / d; r = n % d;
    if (q > U256) { st = -2n; q = 0n; r = 0n; } else st = 1n;
  }
  const raw = Buffer.alloc(REC);
  MAGIC.copy(raw, 0);
  raw[4] = 1; raw[5] = 1;
  img.copy(raw, 8);
  raw.writeBigUInt64LE(1n, 40);
  raw.writeBigUInt64LE(BigInt(leafId), 48);
  packU256(a).copy(raw, 56);
  packU256(b).copy(raw, 88);
  packU256(d).copy(raw, 120);
  packU256(q).copy(raw, 152);
  packU256(r).copy(raw, 184);
  raw.writeBigUInt64LE(978287n, 216);
  raw.writeBigInt64LE(st, 224);
  return raw;
}
function selfTest() {
  const img = Buffer.alloc(32);
  const r0 = demoRecord(1, 7n, 9n, 2n, img);
  const r1 = demoRecord(2, 1n << 255n, 2n, 3n, img);
  const leaves = [leafHash(r0), leafHash(r1)];
  const root = merkleRoot(leaves).toString("hex");
  const bundle = {
    image_loader_digest: img.toString("hex"),
    merkle_root_sha256: root,
    records: [
      { raw_record_hex: r0.toString("hex"), leaf_hash_hex: leaves[0].toString("hex"), status: 1 },
      { raw_record_hex: r1.toString("hex"), leaf_hash_hex: leaves[1].toString("hex"), status: 1 },
    ],
  };
  const ok = verifyBundle(bundle);
  if (!ok.valid) {
    console.log("SELFTEST FAIL clean bundle", ok);
    return 1;
  }
  const tampered = Buffer.from(r0);
  tampered[56] ^= 1;
  const bad = {
    image_loader_digest: img.toString("hex"),
    merkle_root_sha256: root,
    records: [
      { raw_record_hex: tampered.toString("hex"), leaf_hash_hex: leafHash(tampered).toString("hex"), status: 1 },
      { raw_record_hex: r1.toString("hex"), leaf_hash_hex: leaves[1].toString("hex"), status: 1 },
    ],
  };
  const badV = verifyBundle(bad);
  if (badV.valid) {
    console.log("SELFTEST FAIL 1-bit leaf tamper was ACCEPTED");
    return 1;
  }
  console.log("SELFTEST PASS LNR1 identity + 1-bit leaf tamper REJECT reason=" + badV.reason);
  return 0;
}

function main() {
  const args = process.argv.slice(2);
  const self = args.includes("--self-test");
  const file = args.find((a) => !a.startsWith("-"));
  let rc = 0;
  if (self) rc = selfTest();
  if (rc !== 0) process.exit(rc);
  if (file) {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    const bundle = data.lnr1 ? data.lnr1 : data;
    const v = verifyBundle(bundle);
    console.log(JSON.stringify(v, null, 2));
    if (!v.valid) process.exit(1);
  } else if (!self) {
    console.error("usage: verify_u512_receipt.js [--self-test] [bundle.json]");
    process.exit(2);
  }
}
main();
