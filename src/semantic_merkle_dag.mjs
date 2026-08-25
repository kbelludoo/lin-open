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
      try {
        const existing = JSON.parse(fs.readFileSync(filepath, 'utf8'));
        if (existing && existing.certificates) {
          for (const [k, v] of Object.entries(existing.certificates)) {
            if (!this.proofCertificates.has(k)) {
              this.proofCertificates.set(k, v);
            }
          }
        }
      } catch {}
    }
    fs.writeFileSync(filepath, JSON.stringify(this.exportLedgerJson(), null, 2), 'utf8');
  }

  loadLedgerFromFile(filepath) {
    if (!fs.existsSync(filepath)) return false;
    try {
      const data = JSON.parse(fs.readFileSync(filepath, 'utf8'));
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
