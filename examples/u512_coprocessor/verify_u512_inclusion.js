#!/usr/bin/env node
/* Zero-LIN LIP1 auditor (schema 1.6). Path + LRI1 remainder identity. No LinVM. */
"use strict";

const fs = require("fs");
const crypto = require("crypto");
const UMAX = (1n << 256n) - 1n;

function fail(msg) {
  process.stdout.write("FAIL " + msg + "\n");
  process.exit(1);
}

function walk(p) {
  const rec = Buffer.from(p.leaf_hex, "hex");
  const ld = Buffer.from(p.leaf_domain);
  const nd = Buffer.from(p.node_domain);
  let h = crypto.createHash("sha256").update(ld).update(rec).digest();
  if (h.toString("hex") !== p.leaf_sha256) return false;
  for (let i = 0; i < p.siblings.length; i++) {
    const sib = Buffer.from(p.siblings[i], "hex");
    const side = Number(p.sides[i]);
    const hx = crypto.createHash("sha256").update(nd);
    if (side === 0) hx.update(h).update(sib);
    else hx.update(sib).update(h);
    h = hx.digest();
  }
  return h.toString("hex") === p.root;
}

function be(buf, off) {
  let n = 0n;
  for (let i = 0; i < 32; i++) n = (n << 8n) + BigInt(buf[off + i]);
  return n;
}

function lri1Fields(hex) {
  const rec = Buffer.from(hex, "hex");
  if (rec.length !== 240 || rec.slice(0, 4).toString() !== "LRI1") return null;
  return {
    n: be(rec, 56) + (be(rec, 88) << 256n),
    d: be(rec, 120), q: be(rec, 152), r: be(rec, 184),
  };
}

function parseInt0(v) {
  if (typeof v === "number") return BigInt(v);
  if (typeof v === "bigint") return v;
  return BigInt(v);
}

function main() {
  const ev = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  if (ev.schema !== "LIN_U512_COPROCESSOR_EVIDENCE_1.6") fail("schema");
  const proofs = ev.lip1_proofs || [];
  if (proofs.length < 8) fail("proofs");
  const roots = {
    LNR1: ev.lnr1_merkle, LCR2: ev.lcr2_merkle, LCR2_FULL: ev.lcr2_full_merkle,
    LGE1: ev.lge1_merkle, LRI1: ev.lri1_merkle,
  };
  const saw = new Set();
  let nRi = 0;
  const riBy = {};
  for (const L of ev.lri1_leaves || []) riBy[L.name] = L;
  for (const p of proofs) {
    if (!walk(p)) fail("path " + p.tree + "/" + p.name);
    if (p.root !== roots[p.tree]) fail("root " + p.name);
    if (p.tree === "LRI1") {
      const fld = lri1Fields(p.leaf_hex);
      const st = riBy[p.name];
      if (!fld || !st) fail("bind " + p.name);
      const a = parseInt0(st.a), b = parseInt0(st.b), n = parseInt0(st.n);
      if (fld.n !== a * b || fld.n !== n || fld.d !== parseInt0(st.d)) fail("n " + p.name);
      if (fld.q * fld.d + fld.r !== fld.n || fld.r >= fld.d || fld.q > UMAX) fail("identity " + p.name);
      nRi += 1;
    }
    if (p.siblings.length) {
      const tamp = p.siblings.slice();
      const b = Buffer.from(tamp[0], "hex");
      b[0] ^= 1;
      tamp[0] = b.toString("hex");
      const q = Object.assign({}, p, { siblings: tamp });
      if (walk(q)) fail("tamper silent " + p.name);
    }
    saw.add(p.name);
  }
  for (const k of ["phantom_997_rout_1997", "wrap_borrow_2_x_2_255_div_umax",
                   "two255_x2_div3", "max_sq", "GUARD_OVERFLOW", "PHANTOM_APPROVE"]) {
    if (!saw.has(k)) fail("missing " + k);
  }
  if (nRi < 8) fail("lri1 count");
  process.stdout.write("PASS inclusion auditor\n");
  process.stdout.write("lip1_match " + proofs.length + "\n");
  process.stdout.write("lri1_inclusion " + nRi + "\n");
}

main();
