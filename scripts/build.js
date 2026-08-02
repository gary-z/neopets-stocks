'use strict';

/*
 * Build step for the static site.
 *
 * Fetches the current market summary, works out the cheapest stock trading at
 * or above the minimum, and bakes that stock's buy URL into index.html. Runs in
 * CI on a schedule; the published site is a single static page that redirects,
 * with no server behind it.
 */

const fs = require('fs');
const path = require('path');

const MIN_PRICE = Number(process.env.MIN_PRICE || 15);

const NEOSTOCKS_URL = 'https://neostocks.info/?period=1d';
const BUY_URL = 'https://www.neopets.com/stockmarket.phtml';

const ROOT = path.join(__dirname, '..');
const OUT_DIR = path.join(ROOT, '_site');

// neostocks is a Shiny app: it bootstraps the whole summary table into a
// `window.__data__ = {...}` literal in the served HTML. Pull that back out.
function extractDataLiteral(html) {
  const marker = html.indexOf('window.__data__');
  if (marker === -1) throw new Error('neostocks: window.__data__ not found (page layout changed?)');

  const start = html.indexOf('{', marker);
  if (start === -1) throw new Error('neostocks: no object literal after window.__data__');

  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = start; i < html.length; i++) {
    const c = html[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') inString = true;
    else if (c === '{') depth++;
    else if (c === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error('neostocks: unbalanced object literal');
}

async function getTarget() {
  const res = await fetch(NEOSTOCKS_URL, {
    headers: {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    },
  });
  if (!res.ok) throw new Error(`neostocks returned HTTP ${res.status}`);

  const data = JSON.parse(extractDataLiteral(await res.text()));
  const rows = data && data.summary_data && data.summary_data['1d'];
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('neostocks: no 1d summary rows');

  const eligible = rows
    .filter((r) => r && typeof r.ticker === 'string' && Number.isFinite(r.curr) && r.curr >= MIN_PRICE)
    .sort((a, b) => a.curr - b.curr || a.ticker.localeCompare(b.ticker));

  if (eligible.length === 0) throw new Error(`no stock is trading at ${MIN_PRICE} NP or above`);

  const best = eligible[0];
  const params = new URLSearchParams({ type: 'buy', ticker: best.ticker });

  return {
    ticker: best.ticker,
    price: best.curr,
    minPrice: MIN_PRICE,
    candidates: eligible.length,
    tracked: rows.length,
    // Neopets fills ticker_symbol from ?ticker=; the shares box it does not.
    buyUrl: `${BUY_URL}?${params}`,
    // neostocks samples every 15 minutes, so this is the age of the price.
    pricesAsOf: best.update_time || data.update_time || null,
    pricesAsOfNst: best.update_time_nst || null,
  };
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// index.html is a template with __NAME__ placeholders. Missing one is a build
// failure rather than a page published with the literal token still in it.
function render(template, vars) {
  return Object.entries(vars).reduce((html, [name, value]) => {
    const token = `__${name}__`;
    if (!html.includes(token)) throw new Error(`index.html has no ${token} to substitute`);
    return html.split(token).join(escapeHtml(value));
  }, template);
}

async function main() {
  const target = await getTarget();

  const template = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  const html = render(template, { BUY_URL: target.buyUrl, TICKER: target.ticker });

  fs.rmSync(OUT_DIR, { recursive: true, force: true });
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, 'index.html'), html);

  console.log(
    `${target.ticker} @ ${target.price} NP  ` +
      `(cheapest of ${target.candidates} at >= ${target.minPrice}, ${target.tracked} tracked)  ` +
      `prices as of ${target.pricesAsOfNst || target.pricesAsOf} NST`
  );
  console.log(`wrote ${path.relative(ROOT, OUT_DIR)}/index.html -> ${target.buyUrl}`);
}

main().catch((err) => {
  console.error(`build failed: ${err.message}`);
  process.exit(1);
});
