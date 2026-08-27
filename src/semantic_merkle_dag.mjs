/**
 * LIN Content-Addressed Semantic Merkle DAG & Proof Ledger Manager
 * Spec: spec/LIN_SEMANTIC_MERKLE_DAG.rulel
 */

import fs from 'node:fs';
import { hashCanonicalNode, hashAppMerkleRoot, CANONICALIZATION_VERSION } from './semantic_merkle_hasher.mjs';

export class SemanticMerkleDagStore {
  constructor() {
    this.nodes = new Map(); // hash -> canonicalNode
    this.refCounts = new Map(); // hash -> count
    this.proofCertificates = new Map(); // hash -> Certificate
    this.totalEncountered = 0;
  }

  insert(irNode) {
    const hash = hashCanonicalNode(irNode);
    this.totalEncountered++;

    if (this.nodes.has(hash)) {
      this.refCounts.set(hash, this.refCounts.get(hash) + 1);
    } else {
      this.nodes.set(hash, irNode);
      this.refCounts.set(hash, 1);
    }

    return { hash, isNew: this.refCounts.get(hash) === 1 };
  }

  get(hash) {
    return this.nodes.get(hash) || null;
  }

  has(hash) {
    return this.nodes.has(hash);
  }

  getDeduplicationRatio() {
    if (this.nodes.size === 0) return 1.0;
    return parseFloat((this.totalEncountered / this.nodes.size).toFixed(3));
  }

  registerProofCertificate(opts) {
    const cert = {
      semantic_hash: opts.semantic_hash,
      canonicalization_version: CANONICALIZATION_VERSION,
      source_language: opts.source_language || 'javascript',
      target: opts.target || 'lin',
      oracle: opts.oracle || 'node_v24_js_oracle',
      test_suite_hash: opts.test_suite_hash,
      behavior_eq: opts.behavior_eq !== undefined ? opts.behavior_eq : 1.0,
      timestamp: new Date().toISOString()
    };
    this.proofCertificates.set(cert.semantic_hash, cert);
    return cert;
  }

  verifyCertificate(semantic_hash, expectedVersion = CANONICALIZATION_VERSION) {
    const cert = this.proofCertificates.get(semantic_hash);
    if (!cert) return { valid: false, reason: 'Certificate not found in ledger' };
    if (cert.canonicalization_version !== expectedVersion) {
      return { valid: false, reason: `Version mismatch: cert ${cert.canonicalization_version} != expected ${expectedVersion}` };
    }
    if (cert.behavior_eq < 1.0) {
      return { valid: false, reason: `Sub-unity behavior_eq: ${cert.behavior_eq}` };
    }
    return { valid: true, cert };
  }

  exportLedgerRulel() {
    const lines = [
      `@LEDGER:LIN_PROOF:${CANONICALIZATION_VERSION}`,
      `~MERKLE_SUMMARY{unique_nodes=${this.nodes.size} total_encountered=${this.totalEncountered} deduplication=${this.getDeduplicationRatio().toFixed(2)}x}`
    ];
    for (const [hash, cert] of this.proofCertificates.entries()) {
      lines.push(`.cert{hash="${cert.semantic_hash}" v="${cert.canonicalization_version}" lang="${cert.source_language}" target="${cert.target}" oracle="${cert.oracle}" suite="${cert.test_suite_hash}" eq=${Number(cert.behavior_eq).toFixed(4)} ts="${cert.timestamp}"}`);
    }
    return lines.join('\n') + '\n';
  }

  importLedgerRulel(content) {
    const lines = content.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('.cert{')) continue;
      const m = trimmed.match(/\.cert\{([^}]+)\}/);
      if (!m) continue;
      const body = m[1];
      const entry = {};
      const pairs = body.matchAll(/(\w+)=(?:"([^"]*)"|([\w.-]+))/g);
      for (const p of pairs) {
        const k = p[1];
        const v = p[2] !== undefined ? p[2] : p[3];
        entry[k] = v;
      }
      if (entry.hash) {
        this.proofCertificates.set(entry.hash, {
          semantic_hash: entry.hash,
          canonicalization_version: entry.v || CANONICALIZATION_VERSION,
          source_language: entry.lang,
          target: entry.target || 'lin',
          oracle: entry.oracle,
          test_suite_hash: entry.suite,
          behavior_eq: parseFloat(entry.eq || '1.0'),
          timestamp: entry.ts || new Date().toISOString()
        });
      }
    }
  }

  exportLedgerJson() {
    return {
      version: CANONICALIZATION_VERSION,
      total_unique_nodes: this.nodes.size,
      total_encountered: this.totalEncountered,
      deduplication_ratio: this.getDeduplicationRatio(),
      certificates: Object.fromEntries(this.proofCertificates.entries())
    };
  }

  saveLedgerToFile(filepath) {
    if (fs.existsSync(filepath)) {
      this.loadLedgerFromFile(filepath);
    }
    if (filepath.endsWith('.rulel') || !filepath.endsWith('.json')) {
      fs.writeFileSync(filepath, this.exportLedgerRulel(), 'utf8');
    } else {
      fs.writeFileSync(filepath, JSON.stringify(this.exportLedgerJson(), null, 2), 'utf8');
    }
  }

  loadLedgerFromFile(filepath) {
    if (!fs.existsSync(filepath)) return false;
    try {
      const content = fs.readFileSync(filepath, 'utf8');
      if (filepath.endsWith('.rulel') || content.startsWith('@LEDGER:')) {
        this.importLedgerRulel(content);
        return true;
      }
      const data = JSON.parse(content);
      if (data.certificates) {
        for (const [hash, cert] of Object.entries(data.certificates)) {
          this.proofCertificates.set(hash, cert);
        }
      }
      return true;
    } catch (e) {
      return false;
    }
  }
}
