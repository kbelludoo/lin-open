/**
 * Host loader: LIN source is src/clone_lin_full_repo_gate.lin
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compileLiaToJs } from '../src/compiler.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LIN = path.join(ROOT, 'src', 'clone_lin_full_repo_gate.lin');
const lin = fs.readFileSync(LIN, 'utf8');
const { js } = compileLiaToJs(lin, { exportMode: 'multiple' });
const tmp = path.join(os.tmpdir(), 'lin_full_repo_gate.cjs');
fs.writeFileSync(tmp, js, 'utf8');
const mod = createRequire(import.meta.url)(tmp);
try { fs.rmSync(tmp, { force: true }); } catch { /* ignore */ }

export const defaultEmitTarget = mod.defaultEmitTarget;
export const realNucleusLangs = mod.realNucleusLangs;
export const compileOrder = mod.compileOrder;
export const gateRequiredLangs = mod.gateRequiredLangs;
export const stubEmitLangs = mod.stubEmitLangs;
export const formatStubIntel = mod.formatStubIntel;
export const honestNucleusMulti = mod.honestNucleusMulti;
export const hasStubPassScore = mod.hasStubPassScore;
export const refuseStubBenchmark = mod.refuseStubBenchmark;
export const benchWarmupCount = mod.benchWarmupCount;
export const benchRepeatCount = mod.benchRepeatCount;
export const rowIsFull = mod.rowIsFull;
export const allRowsFull = mod.allRowsFull;
export const langMemoryKind = mod.langMemoryKind;
export const langIsMemorySafe = mod.langIsMemorySafe;
export const inMemoryHostLang = mod.inMemoryHostLang;
export const cMemoryLabel = mod.cMemoryLabel;
export const memoryClassRank = mod.memoryClassRank;
export const rankQualityRows = mod.rankQualityRows;
export const rankInMemoryRows = mod.rankInMemoryRows;
export const pickBestFromRows = mod.pickBestFromRows;
export const futurePickBestLang = mod.futurePickBestLang;
export const normalizeSkipToFail = mod.normalizeSkipToFail;
export const fileCoverage = mod.fileCoverage;
export const isOverloadOrNestedFn = mod.isOverloadOrNestedFn;
export const missedExtracts = mod.missedExtracts;
export const canPublishFullRepo = mod.canPublishFullRepo;
export const isTypeOnlyModule = mod.isTypeOnlyModule;
export const multiAllFull = mod.multiAllFull;
