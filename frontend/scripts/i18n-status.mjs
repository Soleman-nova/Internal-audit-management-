#!/usr/bin/env node
/**
 * List the translation work still outstanding.
 *
 * `I18nContext.jsx` holds one dictionary per language. `t()` already falls back
 * to English when a key is missing from the active language, so a key that exists
 * only in `en` is not a bug — it renders the English string and is simply waiting
 * for a translator. This script prints exactly those keys, which is the whole
 * reason the extraction could leave `am` alone: an untranslated string shows up
 * here rather than as a duplicated English value inside the Amharic dictionary
 * that would go stale the moment someone edited the English.
 *
 *   node scripts/i18n-status.mjs              # summary + the worklist
 *   node scripts/i18n-status.mjs --scaffold   # ready-to-paste `am` entries
 *   node scripts/i18n-status.mjs --quiet      # exit code only, for CI
 *
 * Exit code is 0 either way: outstanding translations are work, not failure.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = path.join(HERE, '..', 'src', 'context', 'I18nContext.jsx');

const KEY = /^\s{4,}([A-Za-z_][A-Za-z0-9_]*)\s*:/;

/** Pull one top-level language block out by brace matching, so nested objects and
 *  arrow-function values cannot end it early. */
function block(lines, startIndex) {
  let depth = 0;
  const out = [];
  for (let i = startIndex; i < lines.length; i += 1) {
    depth += (lines[i].match(/\{/g) || []).length;
    depth -= (lines[i].match(/\}/g) || []).length;
    out.push(lines[i]);
    if (depth <= 0 && out.length > 1) break;
  }
  return out;
}

function keysOf(lines, lang) {
  const at = lines.findIndex((l) => new RegExp(`^\\s*${lang}\\s*:\\s*\\{`).test(l));
  if (at === -1) throw new Error(`no ${lang}: block found in ${SOURCE}`);
  const names = [];
  for (const line of block(lines, at).slice(1)) {
    const m = KEY.exec(line);
    if (m) names.push(m[1]);
  }
  return names;
}

/** The English text of a key, best effort: enough to hand a translator context. */
function englishOf(lines, key) {
  const at = lines.findIndex((l) => new RegExp(`^\\s*${key}\\s*:`).test(l));
  if (at === -1) return '';
  const line = lines[at];
  const quoted = /(['"`])((?:(?!\1).)*)\1/.exec(line.slice(line.indexOf(':') + 1));
  if (quoted) return quoted[2];
  // A function value: take the returned template literal's static parts.
  const parts = [...line.matchAll(/`([^`$]*)/g)].map((m) => m[1]).filter(Boolean);
  return parts.length ? parts.join('…') : '(interpolated)';
}

const args = process.argv.slice(2);
const lines = fs.readFileSync(SOURCE, 'utf8').split('\n');
const en = keysOf(lines, 'en');
const am = keysOf(lines, 'am');
const missing = en.filter((k) => !am.includes(k));
const orphaned = am.filter((k) => !en.includes(k));

if (!args.includes('--quiet')) {
  console.log(`en keys: ${en.length}`);
  console.log(`am keys: ${am.length}`);
  console.log(`awaiting Amharic: ${missing.length}`);
  if (orphaned.length) {
    console.log(`\nam-only (dead: the key is never requested): ${orphaned.length}`);
  }
  if (missing.length) {
    console.log('\n--- worklist ---');
    for (const key of missing) console.log(`  ${key}: ${englishOf(lines, key)}`);
  } else {
    console.log('\nEvery key is translated.');
  }
}

if (args.includes('--scaffold') && missing.length) {
  console.log('\n--- paste into the am block, then translate the values ---');
  for (const key of missing) console.log(`    ${key}: ${JSON.stringify(englishOf(lines, key))},`);
}

if (orphaned.length) {
  console.error(`\nwarning: ${orphaned.length} am-only key(s) — nothing ever requests them`);
  process.exit(2);
}
