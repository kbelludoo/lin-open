#!/usr/bin/env node
/* Zero-LIN LIP1 auditor (schema 1.11). Path + LRI1 identity + packed LCR2 vs
 * SafeMath ref + packed LCR2-full vs FullMath ref. */
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

function u64le(buf, off) {
  let n = 0n;
  for (let i = 7; i >= 0; i--) n = (n << 8n) + BigInt(buf[off + i]);
  return n;
}

function i64le(buf, off) {
  const u = u64le(buf, off);
  return u >= (1n << 63n) ? u - (1n << 64n) : u;
}

function lri1Fields(hex) {
  const rec = Buffer.from(hex, "hex");
  if (rec.length !== 240 || rec.slice(0, 4).toString() !== "LRI1") return null;
  return {
    n: be(rec, 56) + (be(rec, 88) << 256n),
    d: be(rec, 120), q: be(rec, 152), r: be(rec, 184),
  };
}

function lcr2Fields(hex) {
  const rec = Buffer.from(hex, "hex");
  if (rec.length !== 208 || rec.slice(0, 4).toString() !== "LCR2") return null;
  return {
    ain: be(rec, 56), rin: be(rec, 88), rout: be(rec, 120), aout: be(rec, 152),
    steps: u64le(rec, 184), status: i64le(rec, 192),
  };
}

function parseInt0(v) {
  if (typeof v === "number") return BigInt(v);
  if (typeof v === "bigint") return v;
  return BigInt(v);
}

function refSafe(ain, rin, rout) {
  if (ain <= 0n || rin <= 0n || rout <= 0n) return { st: -1n, q: 0n };
  const fee = ain * 997n;
  const num = fee * rout;
  const den = rin * 1000n + fee;
  if (fee > UMAX || den > UMAX || num > UMAX) return { st: -2n, q: 0n };
  return { st: 1n, q: num / den };
}

function refFull(ain, rin, rout) {
  if (ain <= 0n || rin <= 0n || rout <= 0n) return { st: -1n, q: 0n };
  const fee = ain * 997n;
  const den = rin * 1000n + fee;
  if (fee > UMAX || den > UMAX) return { st: -2n, q: 0n };
  const q = (fee * rout) / den;
  if (q > UMAX) return { st: -2n, q: 0n };
  return { st: 1n, q };
}

function main() {
  const ev = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  if (ev.schema !== "LIN_U512_COPROCESSOR_EVIDENCE_1.11") fail("schema");
  const proofs = ev.lip1_proofs || [];
  if (proofs.length < 34) fail("proofs");
  const roots = {
    LNR1: ev.lnr1_merkle, LCR2: ev.lcr2_merkle, LCR2_FULL: ev.lcr2_full_merkle,
    LGE1: ev.lge1_merkle, LRI1: ev.lri1_merkle,
  };
  const saw = new Set();
  let nRi = 0, nEx = 0, nOv = 0, nZ = 0, nOvf = 0;
  let nFex = 0, nFov = 0, nFz = 0, nFfee = 0, nFph = 0;
  const riBy = {};
  for (const L of ev.lri1_leaves || []) riBy[L.name] = L;
  const lcrBy = {};
  (ev.lcr2_leaves || []).forEach((L, i) => { lcrBy[L.class + "_" + i] = L; });
  const fullBy = {};
  (ev.lcr2_full_leaves || []).forEach((L, i) => {
    const name = L.class === "PHANTOM_APPROVE" ? "PHANTOM_APPROVE" : ("FULL_" + L.class + "_" + i);
    fullBy[name] = L;
  });
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
    if (p.tree === "LCR2") {
      const fld = lcr2Fields(p.leaf_hex);
      const st = lcrBy[p.name];
      if (!fld || !st) fail("LCR2 bind " + p.name);
      if (fld.steps === 0n || fld.steps !== parseInt0(st.steps) || fld.status !== parseInt0(st.status)) {
        fail("LCR2 steps " + p.name);
      }
      if (fld.ain !== parseInt0(st.ain) || fld.aout !== parseInt0(st.aout)) fail("LCR2 pack " + p.name);
      const rst = refSafe(fld.ain, fld.rin, fld.rout);
      if (p.name.startsWith("EXACT_INPUT_")) {
        if (fld.status !== 1n || rst.st !== 1n || fld.aout !== rst.q || fld.aout !== parseInt0(st.onchain)) {
          fail("LCR2 EXACT packed " + p.name);
        }
        nEx += 1;
      } else if (p.name.startsWith("OVERPAID_INPUT_")) {
        if (fld.status !== 1n || rst.st !== 1n || fld.aout !== rst.q || fld.aout === parseInt0(st.onchain)) {
          fail("LCR2 OVERPAID packed " + p.name);
        }
        nOv += 1;
      } else if (p.name.startsWith("GUARD_ZERO_")) {
        if (fld.status !== -1n || rst.st !== -1n) fail("LCR2 GUARD_ZERO packed");
        nZ += 1;
      } else if (p.name.startsWith("GUARD_OVERFLOW_")) {
        if (fld.status !== -2n || rst.st !== -2n) fail("LCR2 GUARD_OVERFLOW packed");
        nOvf += 1;
      } else fail("LCR2 class " + p.name);
    }
    if (p.tree === "LCR2_FULL") {
      const fld = lcr2Fields(p.leaf_hex);
      const st = fullBy[p.name];
      if (!fld || !st) fail("LCR2_FULL bind " + p.name);
      if (fld.steps === 0n || fld.steps !== parseInt0(st.steps) || fld.status !== parseInt0(st.status)) {
        fail("LCR2_FULL steps " + p.name);
      }
      if (fld.ain !== parseInt0(st.ain) || fld.aout !== parseInt0(st.aout)) fail("LCR2_FULL pack " + p.name);
      const rstS = refSafe(fld.ain, fld.rin, fld.rout);
      const rstF = refFull(fld.ain, fld.rin, fld.rout);
      if (p.name.startsWith("FULL_EXACT_INPUT_")) {
        if (fld.status !== 1n || rstF.st !== 1n || fld.aout !== rstF.q || fld.aout !== parseInt0(st.onchain)) {
          fail("LCR2_FULL EXACT packed " + p.name);
        }
        nFex += 1;
      } else if (p.name.startsWith("FULL_OVERPAID_INPUT_")) {
        if (fld.status !== 1n || rstF.st !== 1n || fld.aout !== rstF.q || fld.aout === parseInt0(st.onchain)) {
          fail("LCR2_FULL OVERPAID packed " + p.name);
        }
        nFov += 1;
      } else if (p.name === "PHANTOM_APPROVE") {
        if (fld.status !== 1n || rstS.st !== -2n || rstF.st !== 1n || fld.aout !== rstF.q) {
          fail("LCR2_FULL PHANTOM packed");
        }
        nFph += 1;
      } else if (p.name.startsWith("FULL_GUARD_ZERO_")) {
        if (fld.status !== -1n || rstF.st !== -1n) fail("LCR2_FULL GUARD_ZERO packed");
        nFz += 1;
      } else if (p.name.startsWith("FULL_GUARD_FEE_OVERFLOW_")) {
        if (fld.status !== -2n || rstF.st !== -2n) fail("LCR2_FULL GUARD_FEE packed");
        nFfee += 1;
      } else fail("LCR2_FULL class " + p.name);
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
                   "two255_x2_div3", "max_sq", "PHANTOM_APPROVE"]) {
    if (!saw.has(k)) fail("missing " + k);
  }
  if (nRi < 8) fail("lri1 count");
  if (nEx < 3 || nOv < 3 || nZ < 1 || nOvf < 1) fail("lcr2 inclusion counts");
  if (nFex < 3 || nFov < 3 || nFz < 1 || nFfee < 1 || nFph < 1) fail("lcr2_full inclusion counts");
  process.stdout.write("PASS inclusion auditor\n");
  process.stdout.write("lip1_match " + proofs.length + "\n");
  process.stdout.write("lri1_inclusion " + nRi + "\n");
  process.stdout.write("lcr2_inclusion " + (nEx + nOv + nZ + nOvf) + "\n");
  process.stdout.write("lcr2_full_inclusion " + (nFex + nFov + nFz + nFfee + nFph) + "\n");
}

main();
