// LIN RULEL & Comms Protocol Parser (Dogfooding rulel_core.lin)
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  splitTopEntries: linSplitTopEntries,
  parseValuePairs: linParseValuePairs,
  parseRulel: linParseRulel,
  validateComms: linValidateComms,
} = require('./rulel_core.compiled.cjs');

export const splitTopEntries = linSplitTopEntries;
export const parseValuePairs = linParseValuePairs;
export const parseRulel = linParseRulel;
export const validateComms = linValidateComms;
