/*
 * Fetching and parsing the neostocks market summary.
 *
 * Kept apart from the Worker so the "which stock" decision can be exercised
 * without an HTTP layer wrapped around it - see scripts/check.js.
 */

export const NEOSTOCKS_URL = 'https://neostocks.info/?period=1d';
export const BUY_URL = 'https://www.neopets.com/stockmarket.phtml';

// Neopets' own rule: "You can only purchase shares in companies that trade at
// 15 NP per share or above."
export const DEFAULT_MIN_PRICE = 15;

// neostocks is a Shiny app: it bootstraps the whole summary table into a
// `window.__data__ = {...}` literal in the served HTML. Pull that back out.
export function extractDataLiteral(html) {
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

// Worth telling apart from a parse or network failure: neostocks answered
// correctly, the market just has nothing this cheap.
export class NoEligibleStock extends Error {}

export function pickTarget(data, minPrice) {
  const rows = data && data.summary_data && data.summary_data['1d'];
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('neostocks: no 1d summary rows');

  const eligible = rows
    .filter((r) => r && typeof r.ticker === 'string' && Number.isFinite(r.curr) && r.curr >= minPrice)
    .sort((a, b) => a.curr - b.curr || a.ticker.localeCompare(b.ticker));

  if (eligible.length === 0) throw new NoEligibleStock(`no stock is trading at ${minPrice} NP or above`);

  const best = eligible[0];
  const params = new URLSearchParams({ type: 'buy', ticker: best.ticker });

  return {
    ticker: best.ticker,
    price: best.curr,
    minPrice,
    candidates: eligible.length,
    tracked: rows.length,
    // Neopets fills ticker_symbol from ?ticker=; the shares box it does not.
    buyUrl: `${BUY_URL}?${params}`,
    // neostocks samples every 15 minutes, so this is the age of the price.
    pricesAsOf: best.update_time || data.update_time || null,
    pricesAsOfNst: best.update_time_nst || null,
  };
}

/*
 * `cacheTtl` seconds are handed to Cloudflare's cache via the non-standard
 * `cf` init, which the runtime reads and Node's fetch ignores - so the same
 * call works uncached under plain node.
 */
export async function fetchTarget({ minPrice = DEFAULT_MIN_PRICE, cacheTtl } = {}) {
  let res;
  try {
    res = await fetch(NEOSTOCKS_URL, {
      // neostocks serves a bot challenge to unrecognised clients.
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
          '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
      },
      ...(cacheTtl ? { cf: { cacheEverything: true, cacheTtl } } : {}),
    });
  } catch (cause) {
    // Workers renders a network failure as "internal error; reference = ...",
    // which tells a visitor nothing. Keep the original on `cause` for the logs.
    throw new Error("couldn't reach neostocks.info", { cause });
  }
  if (!res.ok) throw new Error(`neostocks returned HTTP ${res.status}`);

  return pickTarget(JSON.parse(extractDataLiteral(await res.text())), minPrice);
}
