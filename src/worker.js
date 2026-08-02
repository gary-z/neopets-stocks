/*
 * The whole site: one request, one live price lookup, one redirect.
 *
 * A browser can't do this itself - neostocks sends no Access-Control-Allow-Origin,
 * so its market summary is unreadable from page JavaScript. Fetching it here,
 * server-side, is the reason this Worker exists.
 */

import { BUY_URL, DEFAULT_MIN_PRICE, NoEligibleStock, fetchTarget } from './neostocks.js';

// neostocks resamples every 15 minutes. Holding its HTML at the edge for a
// fraction of that collapses a burst of loads into one origin fetch, and can't
// serve a price older than the sample it came from.
const UPSTREAM_CACHE_TTL = 120;

class BadRequest extends Error {}

function parseMinPrice(url) {
  const raw = url.searchParams.get('min');
  if (raw === null) return DEFAULT_MIN_PRICE;

  // Number('') is 0, which would quietly mean "no floor" - and a stock under
  // 15 NP can't be bought anyway, so that is never what was meant.
  const value = raw.trim() === '' ? NaN : Number(raw);
  if (!Number.isFinite(value) || value < 0) throw new BadRequest(`min must be a number, got "${raw}"`);
  return value;
}

// Only ever reached when something went wrong - the happy path is a bare 302.
function page(status, body) {
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/favicon.ico">
<title>Neopets Stock Buyer</title>
<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    text-align: center;
    font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  code { font-size: 13px; opacity: 0.7; }
</style>
</head>
<body>
  <div>${body}</div>
</body>
</html>
`;

  return new Response(html, {
    status,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' },
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('method not allowed\n', { status: 405, headers: { allow: 'GET, HEAD' } });
    }
    if (url.pathname !== '/' && url.pathname !== '/json') {
      return new Response('not found\n', { status: 404 });
    }

    let target;
    try {
      const minPrice = parseMinPrice(url);
      target = await fetchTarget({ minPrice, cacheTtl: UPSTREAM_CACHE_TTL });
    } catch (err) {
      // 502 is reserved for neostocks itself failing; a `min` nothing satisfies
      // is a normal answer to an unreasonable question.
      let status = 502;
      if (err instanceof BadRequest) status = 400;
      else if (err instanceof NoEligibleStock) status = 404;
      else console.error(err.cause ?? err);

      if (url.pathname === '/json') {
        return Response.json({ error: err.message }, { status, headers: { 'cache-control': 'no-store' } });
      }
      // Still worth landing on: the market page lists every price, so the pick
      // can be made by eye. Saying why beats a redirect that looks deliberate.
      return page(
        status,
        `<p>Couldn't work out the cheapest stock.<br><code>${escapeHtml(err.message)}</code></p>` +
          `<p><a href="${BUY_URL}">Open the stock market</a> and pick one yourself.</p>`
      );
    }

    if (url.pathname === '/json') {
      return Response.json(target, { headers: { 'cache-control': 'no-store' } });
    }

    // 302, not 301: the target changes with the market, and a permanent
    // redirect would be cached by the browser forever. no-store keeps even the
    // temporary one from being replayed on the next visit.
    return new Response(null, {
      status: 302,
      headers: { location: target.buyUrl, 'cache-control': 'no-store' },
    });
  },
};
