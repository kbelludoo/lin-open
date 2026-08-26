#!/usr/bin/env node
/**
 * Fill clone-lin queue: emit langs + GitHub most-starred created this year.
 * Does not log tokens. Spec: LIN_CLONE_LIN_LOOP @QUEUE
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'storage', 'lin_year_star_queue.json');
const YEAR = new Date().getFullYear();
const LANGS = ['javascript', 'typescript', 'python', 'go', 'rust'];
const PER = 2;

function ghSearch(q) {
  const r = spawnSync(
    'gh',
    [
      'api',
      '--method', 'GET',
      'search/repositories',
      '-f', `q=${q}`,
      '-f', 'sort=stars',
      '-f', 'order=desc',
      '-F', `per_page=${PER}`,
    ],
    { encoding: 'utf8', timeout: 60_000 },
  );
  if (r.status !== 0) return { items: [], error: (r.stderr || r.stdout || '').slice(0, 300) };
  try {
    return JSON.parse(r.stdout || '{}');
  } catch {
    return { items: [], error: 'parse' };
  }
}

export function buildYearStarQueue() {
  const seen = new Set();
  const queue = [];
  const errors = [];
  for (const lang of LANGS) {
    const q = `created:>=${YEAR}-01-01 stars:>10 language:${lang}`;
    const data = ghSearch(q);
    if (data.error && !data.items?.length) errors.push({ lang, error: data.error });
    for (const it of data.items || []) {
      const name = String(it.name || '').toLowerCase().replace(/[^a-z0-9_-]/g, '-') || 'repo';
      if (seen.has(name)) continue;
      seen.add(name);
      queue.push({
        name,
        source: `${it.clone_url || `https://github.com/${it.full_name}.git`}`,
        lang,
        stars: it.stargazers_count || 0,
        full_name: it.full_name,
        year: YEAR,
        prefer: null,
      });
    }
  }
  const payload = {
    year: YEAR,
    langs: LANGS,
    fetched: new Date().toISOString(),
    queue,
    errors,
    policy: 'all_emit_langs + most_stars_created_this_year',
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  return payload;
}

export function loadYearStarQueue() {
  try {
    return JSON.parse(fs.readFileSync(OUT, 'utf8'));
  } catch {
    return null;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const p = buildYearStarQueue();
  console.log(JSON.stringify({ n: p.queue.length, langs: LANGS, year: YEAR, names: p.queue.map((x) => x.name), errors: p.errors }, null, 2));
  process.exit(p.queue.length ? 0 : 1);
}
