#!/usr/bin/env node
/* Zero-LIN Node auditor (schema 1.9). Recomputes LNR1 + LCR2 + LCR2-full + LGE1
 * + LRI1 remainder identity. Does not run LinVM. */
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const DOM_LEAF = Buffer.from("LIN:U512:LEAF:1");
const DOM_NODE = Buffer.from("LIN:U512:NODE:1");
const LCR_LEAF = Buffer.from("LIN:LEAF:1");
const LCR_NODE = Buffer.from("LIN:NODE:1");
const GE_LEAF = Buffer.from("LIN:U512:GE:LEAF:1");
const GE_NODE = Buffer.from("LIN:U512:GE:NODE:1");
const RI_LEAF = Buffer.from("LIN:U512:RI:LEAF:1");
const RI_NODE = Buffer.from("LIN:U512:RI:NODE:1");
const PIN_FM = "959c52e1c860bfbede3e33c8d04910c11038973173aa3478547cbad2e444880e";
const UMAX = (1n << 256n) - 1n;
const OP = { MUL: 1, MULDIV: 2 };

function fail(msg) {
  process.stdout.write("FAIL " + msg + "\n");
  process.exit(1);
}

function parseInt0(v) {
  if (typeof v === "number") return BigInt(v);
  if (typeof v === "bigint") return v;
  return BigInt(v);
}

function be32(n) {
  const b = Buffer.alloc(32);
  let v = BigInt(n);
  for (let i = 31; i >= 0; i--) {
    b[i] = Number(v & 0xffn);
    v >>= 8n;
  }
  return b;
}

function packU64(buf, off, n) {
  let v = BigInt(n) & 0xffffffffffffffffn;
  for (let i = 0; i < 8; i++) buf[off + i] = Number((v >> BigInt(8 * i)) & 0xffn);
}

function packI64(buf, off, n) {
  let v = BigInt(n);
  if (v < 0n) v = (1n << 64n) + v;
  packU64(buf, off, v);
}

function lnr1(src, runId, vid, op, a, b, d, q, r, steps, status) {
  const raw = Buffer.alloc(240);
  raw.write("LNR1", 0);
  raw[4] = 1;
  raw[5] = op;
  src.copy(raw, 8);
  packU64(raw, 40, runId);
  packU64(raw, 48, vid);
  be32(a).copy(raw, 56);
  be32(b).copy(raw, 88);
  be32(d).copy(raw, 120);
  be32(q).copy(raw, 152);
  be32(r).copy(raw, 184);
  packU64(raw, 216, steps);
  packI64(raw, 224, status);
  return raw;
}

function lcr2(img, runId, tx, ain, rin, rout, aout, steps, status) {
  const raw = Buffer.alloc(208);
  raw.write("LCR2", 0);
  raw[4] = 1;
  raw[5] = 1;
  img.copy(raw, 8);
  packU64(raw, 40, runId);
  packU64(raw, 48, tx);
  be32(ain).copy(raw, 56);
  be32(rin).copy(raw, 88);
  be32(rout).copy(raw, 120);
  be32(aout).copy(raw, 152);
  packU64(raw, 184, steps);
  packI64(raw, 192, status);
  return raw;
}

function lge1(src, runId, vid, a, b, ge, steps) {
  const raw = Buffer.alloc(208);
  raw.write("LGE1", 0);
  raw[4] = 1;
  src.copy(raw, 8);
  packU64(raw, 40, runId);
  packU64(raw, 48, vid);
  be32(a & UMAX).copy(raw, 56);
  be32(a >> 256n).copy(raw, 88);
  be32(b & UMAX).copy(raw, 120);
  be32(b >> 256n).copy(raw, 152);
  packU64(raw, 184, steps);
  packU64(raw, 192, ge);
  return raw;
}

function lri1(src, runId, vid, n, d, q, r, steps, status) {
  const raw = Buffer.alloc(240);
  raw.write("LRI1", 0);
  raw[4] = 1;
  src.copy(raw, 8);
  packU64(raw, 40, runId);
  packU64(raw, 48, vid);
  be32(n & UMAX).copy(raw, 56);
  be32(n >> 256n).copy(raw, 88);
  be32(d).copy(raw, 120);
  be32(q).copy(raw, 152);
  be32(r).copy(raw, 184);
  packU64(raw, 216, steps);
  packI64(raw, 224, status);
  return raw;
}

function merkle(recs, leafD, nodeD) {
  let nodes = recs.map((r) => crypto.createHash("sha256").update(leafD).update(r).digest());
  while (nodes.length > 1) {
    const nxt = [];
    for (let i = 0; i < nodes.length; i += 2) {
      const L = nodes[i];
      const R = i + 1 < nodes.length ? nodes[i + 1] : L;
      nxt.push(crypto.createHash("sha256").update(nodeD).update(L).update(R).digest());
    }
    nodes = nxt;
  }
  return nodes[0].toString("hex");
}

function refSafe(ain, rin, rout) {
  if (ain <= 0n || rin <= 0n || rout <= 0n) return { st: -1, q: 0n };
  const fee = ain * 997n;
  const num = fee * rout;
  const den = rin * 1000n + fee;
  if (fee > UMAX || den > UMAX || num > UMAX) return { st: -2, q: 0n };
  return { st: 1, q: num / den };
}

function refFull(ain, rin, rout) {
  if (ain <= 0n || rin <= 0n || rout <= 0n) return { st: -1, q: 0n };
  const fee = ain * 997n;
  const den = rin * 1000n + fee;
  if (fee > UMAX || den > UMAX) return { st: -2, q: 0n };
  const q = (fee * rout) / den;
  if (q > UMAX) return { st: -2, q: 0n };
  return { st: 1, q };
}

function checkLcr2(leaves, imgHex, runId, full) {
  if (!leaves || leaves.length < 8) fail("need >=8 LCR2 leaves");
  const img = Buffer.from(imgHex, "hex");
  const recs = [];
  let nEx = 0, nOv = 0, nZ = 0, nP = 0, nPh = 0, nFee = 0;
  for (const leaf of leaves) {
    const cls = leaf.class;
    const ain = parseInt0(leaf.ain);
    const rin = parseInt0(leaf.rin);
    const rout = parseInt0(leaf.rout);
    const aout = parseInt0(leaf.aout);
    const cop = parseInt0(leaf.coprocessor);
    const onch = parseInt0(leaf.onchain);
    const status = Number(leaf.status);
    const steps = Number(leaf.steps);
    const tx = Number(leaf.tx || 0);
    if (steps === 0) fail("LCR2 " + cls + " steps=0");
    const safe = refSafe(ain, rin, rout);
    const fullR = refFull(ain, rin, rout);
    if (cls === "EXACT_INPUT") {
      const want = full ? fullR : safe;
      if (status !== 1 || want.st !== 1 || aout !== want.q || aout !== onch || aout !== cop) {
        fail("EXACT " + cls);
      }
      nEx += 1;
    } else if (cls === "OVERPAID_INPUT") {
      const want = full ? fullR : safe;
      if (status !== 1 || want.st !== 1 || aout !== want.q || aout !== cop || aout === onch) {
        fail("OVERPAID");
      }
      nOv += 1;
    } else if (cls === "GUARD_ZERO") {
      if (status !== -1 || safe.st !== -1 || ain !== 0n) fail("GUARD_ZERO");
      nZ += 1;
    } else if (cls === "GUARD_OVERFLOW") {
      if (full) fail("GUARD_OVERFLOW not in full tree");
      if (status !== -2 || safe.st !== -2) fail("GUARD_OVERFLOW");
      nP += 1;
    } else if (cls === "PHANTOM_APPROVE") {
      if (!full) fail("PHANTOM_APPROVE only in full tree");
      if (status !== 1 || fullR.st !== 1 || safe.st !== -2 || aout !== fullR.q || aout !== cop) {
        fail("PHANTOM_APPROVE");
      }
      nPh += 1;
    } else if (cls === "GUARD_FEE_OVERFLOW") {
      if (!full) fail("GUARD_FEE_OVERFLOW only in full tree");
      if (status !== -2 || fullR.st !== -2 || ain !== UMAX) fail("GUARD_FEE_OVERFLOW");
      nFee += 1;
    } else fail("unknown class " + cls);
    recs.push(lcr2(img, runId, tx, ain, rin, rout, aout, steps, status));
  }
  if (full) {
    if (nEx < 3 || nOv < 3 || nZ < 1 || nPh < 1 || nFee < 1) {
      fail("full counts");
    }
  } else if (nEx < 3 || nOv < 3 || nZ < 1 || nP < 1) {
    fail("lcr2 counts");
  }
  return merkle(recs, LCR_LEAF, LCR_NODE);
}

function main() {
  const evPath = process.argv[2];
  if (!evPath) {
    process.stderr.write("usage: verify_u512_receipt.js <evidence.json>\n");
    process.exit(2);
  }
  const ev = JSON.parse(fs.readFileSync(evPath, "utf8"));
  if (ev.schema !== "LIN_U512_COPROCESSOR_EVIDENCE_1.9") fail("schema");
  if (ev.class !== "EXPERIMENTAL") fail("class");
  const rootDir = path.resolve(path.dirname(evPath), "../..");
  const fm = crypto.createHash("sha256")
    .update(fs.readFileSync(path.join(rootDir, "test/fixtures/external_proof/FullMath.sol")))
    .digest("hex");
  if (fm !== PIN_FM || ev.pins.fullmath_sol !== PIN_FM) fail("fullmath pin");
  const src = Buffer.from(ev.pins.lin_src, "hex");
  const recs = [];
  const leaves = ev.leaves || [];
  if (leaves.length < 8) fail("leaves");
  let i = 0;
  for (const leaf of leaves) {
    const op = leaf.op;
    const a = parseInt0(leaf.a);
    const b = parseInt0(leaf.b);
    const d = parseInt0(leaf.d);
    const q = parseInt0(leaf.q);
    const r = parseInt0(leaf.r);
    const status = Number(leaf.status);
    const steps = Number(leaf.steps);
    if (steps === 0) fail("leaf steps=0");
    if (op === "MULDIV" && status === 1) {
      if (q * d + r !== a * b || r >= d || q > UMAX) fail("remainder leaf " + i);
    }
    if (op === "MUL" && status === 1) {
      if (q + (r << 256n) !== a * b) fail("mul leaf " + i);
    }
    recs.push(lnr1(src, 1, i, OP[op], a, b, d, q, r, steps, status));
    i += 1;
  }
  const root = merkle(recs, DOM_LEAF, DOM_NODE);
  if (root !== ev.lnr1_merkle) fail("lnr1 merkle");
  const tamp = Buffer.from(recs[0]);
  tamp[56 + 31] ^= 1;
  const tRoot = merkle([tamp].concat(recs.slice(1)), DOM_LEAF, DOM_NODE);
  if (tRoot === root) fail("tamper silent");
  const lcr = checkLcr2(ev.lcr2_leaves, ev.pins.u256_linbc1, Number(ev.lcr2_run_id || 2), false);
  if (lcr !== ev.lcr2_merkle) fail("lcr2 merkle");
  const lcrF = checkLcr2(ev.lcr2_full_leaves, ev.pins.u512_linbc1, Number(ev.lcr2_full_run_id || 3), true);
  if (lcrF !== ev.lcr2_full_merkle) fail("lcr2_full merkle");
  const geLeaves = ev.lge1_leaves || [];
  if (geLeaves.length !== 8) fail("lge1 leaves");
  const geRecs = [];
  let iGe = 0;
  for (const leaf of geLeaves) {
    const a = parseInt0(leaf.a);
    const b = parseInt0(leaf.b);
    const ge = Number(leaf.ge);
    const steps = Number(leaf.steps);
    if (steps === 0) fail("LGE1 steps=0");
    const want = a >= b ? 1 : 0;
    if (ge !== want) fail("LGE1 ge " + leaf.name);
    geRecs.push(lge1(src, Number(ev.lge1_run_id || 4), iGe, a, b, ge, steps));
    iGe += 1;
  }
  const geRoot = merkle(geRecs, GE_LEAF, GE_NODE);
  if (geRoot !== ev.lge1_merkle) fail("lge1 merkle");
  const riLeaves = ev.lri1_leaves || [];
  if (riLeaves.length !== 8) fail("lri1 leaves");
  const riRecs = [];
  let iRi = 0;
  for (const leaf of riLeaves) {
    const a = parseInt0(leaf.a);
    const b = parseInt0(leaf.b);
    const d = parseInt0(leaf.d);
    const n = parseInt0(leaf.n);
    const q = parseInt0(leaf.q);
    const r = parseInt0(leaf.r);
    const status = Number(leaf.status);
    const steps = Number(leaf.steps);
    if (steps === 0) fail("LRI1 steps=0");
    if (n !== a * b) fail("LRI1 n!=a*b " + leaf.name);
    if (status !== 1 || q * d + r !== n || r >= d || q > UMAX) fail("LRI1 identity " + leaf.name);
    riRecs.push(lri1(src, Number(ev.lri1_run_id || 5), iRi, n, d, q, r, steps, status));
    iRi += 1;
  }
  const riRoot = merkle(riRecs, RI_LEAF, RI_NODE);
  if (riRoot !== ev.lri1_merkle) fail("lri1 merkle");
  process.stdout.write("PASS node auditor\n");
  process.stdout.write("merkle_match " + root + "\n");
  process.stdout.write("lcr2_match " + lcr + "\n");
  process.stdout.write("lcr2_full_match " + lcrF + "\n");
  process.stdout.write("lge1_match " + geRoot + "\n");
  process.stdout.write("lri1_match " + riRoot + "\n");
  process.stdout.write("tamper_rejected true\n");
}

main();
