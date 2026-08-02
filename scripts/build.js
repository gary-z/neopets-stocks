'use strict';

/*
 * Build step for the static site.
 *
 * Fetches the current market summary, works out the cheapest stock trading at
 * or above the minimum, and bakes that stock's buy URL into index.html.
 *
 * The published page re-runs this same pick client-side on every visit, so what
 * gets baked in here is only the fallback for when that live fetch fails. That
 * means the build no longer has to run on a timer to stay current.
 */

const fs = require('fs');
const path = require('path');

const MIN_PRICE = Number(process.env.MIN_PRICE || 15);

// Undocumented but public, and served as plain JSON - see R/api.R in
// glin/neostocks. Beats scraping the `window.__data__` literal out of the page.
const TICKERS_URL = 'https://neostocks.info/api/tickers?period=1d';
const BUY_URL = 'https://www.neopets.com/stockmarket.phtml';

const ROOT = path.join(__dirname, '..');
const OUT_DIR = path.join(ROOT, '_site');

async function getTarget() {
  const res = await fetch(TICKERS_URL, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`neostocks returned HTTP ${res.status}`);

  const rows = await res.json();
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('neostocks: no ticker rows');

  // Same rule the page applies to live prices - keep the two in step.
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
    pricesAsOf: best.update_time || null,
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
  const html = render(template, {
    BUY_URL: target.buyUrl,
    TICKER: target.ticker,
    MIN_PRICE: target.minPrice,
  });

  fs.rmSync(OUT_DIR, { recursive: true, force: true });
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, 'index.html'), html);
  // _site is wiped above, so static assets have to be re-copied on every build.
  fs.copyFileSync(path.join(ROOT, 'favicon.ico'), path.join(OUT_DIR, 'favicon.ico'));

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
