'use strict';

/*
 * Tiny zero-dependency server behind the one-button buy page.
 *
 * It exists because the browser can't do either half of this on its own:
 *   - neostocks.info sends no Access-Control-Allow-Origin, so a page can't fetch prices.
 *   - the Neopets buy form is a POST that needs your session cookie and a fresh
 *     _ref_ck token, and cookies don't ride along on a cross-site POST.
 *
 * Run it on your own machine, logged in as you. See README.md.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = Number(process.env.PORT || 8787);
const SHARES = Number(process.env.SHARES || 1000);
const MIN_PRICE = Number(process.env.MIN_PRICE || 15);
const COOKIE = process.env.NEOPETS_COOKIE || '';

const NEOSTOCKS_URL = 'https://neostocks.info/?period=1d';
const BUY_PAGE_URL = 'https://www.neopets.com/stockmarket.phtml?type=buy';
const PROCESS_URL = 'https://www.neopets.com/process_stockmarket.phtml';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36';

/* ------------------------------------------------------------------ prices */

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
  const res = await fetch(NEOSTOCKS_URL, { headers: { 'User-Agent': UA } });
  if (!res.ok) throw new Error(`neostocks returned HTTP ${res.status}`);

  const data = JSON.parse(extractDataLiteral(await res.text()));
  const rows = data && data.summary_data && data.summary_data['1d'];
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('neostocks: no 1d summary rows');

  const eligible = rows
    .filter((r) => r && typeof r.ticker === 'string' && Number.isFinite(r.curr) && r.curr >= MIN_PRICE)
    .sort((a, b) => a.curr - b.curr || a.ticker.localeCompare(b.ticker));

  if (eligible.length === 0) throw new Error(`no stock is trading at ${MIN_PRICE} NP or above`);

  const best = eligible[0];
  return {
    ticker: best.ticker,
    price: best.curr,
    shares: SHARES,
    totalCost: best.curr * SHARES,
    minPrice: MIN_PRICE,
    candidates: eligible.length,
    tracked: rows.length,
    // neostocks samples every 15 minutes, so the price can be one tick stale.
    updatedAt: best.update_time || data.update_time || null,
    updatedAtNst: best.update_time_nst || null,
  };
}

/* --------------------------------------------------------------------- buy */

function scrapeRefCk(html) {
  const m =
    html.match(/name=["']?_ref_ck["']?[^>]*?value=["']([^"']+)["']/i) ||
    html.match(/value=["']([^"']+)["'][^>]*?name=["']?_ref_ck["']?/i);
  if (!m) return null;
  return m[1];
}

// The result page is a full Neopets layout; keep only the readable sentences so
// whatever Neopets actually said comes back verbatim rather than paraphrased.
function htmlToText(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|tr|h\d)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#0?39;|&apos;/gi, "'")
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/[ \t]+/g, ' ')
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .join('\n');
}

// Neopets returns HTTP 200 whether the trade worked or not, so the outcome has
// to be read out of the copy. Anything unrecognised stays "unknown" and the
// raw message is shown rather than guessed at.
//
// The success test is deliberately narrow: it wants the past-tense confirmation
// with a share count ("you have purchased 1,000 shares"). Loose matching on
// "purchase" + "shares" also hits the refusal "you have already purchased ..."
// and the buy page's own boilerplate "you can only purchase shares in companies
// that trade at 15 NP per share or above" - reporting either of those as a
// completed trade is the worst thing this function could do.
function classify(text) {
  const t = text.toLowerCase();

  if (/you (have |just )?(purchased|bought)\s+[\d,]+\s+shares?/.test(t)) return 'success';
  if (/you now own\s+[\d,]+\s+shares?/.test(t)) return 'success';

  if (/already (purchased|bought)|daily limit|come back tomorrow/.test(t)) return 'daily_limit';
  if (/enough neopoints|cannot afford|can't afford/.test(t)) return 'insufficient_funds';
  if (/only purchase shares|15 np per share|trade at 15/.test(t)) return 'below_minimum';
  if (/invalid|does not exist|no such|sorry|error/.test(t)) return 'error';

  return 'unknown';
}

function relevantLines(text) {
  // Trim the surrounding site chrome down to the lines that mention the trade.
  const lines = text.split('\n');
  const hits = lines.filter((l) =>
    /(share|stock|neopoint|purchas|bought|sorry|error|invalid|cannot|can't|limit)/i.test(l)
  );
  return (hits.length ? hits : lines).slice(0, 12).join('\n');
}

async function buy() {
  if (!COOKIE) {
    const err = new Error(
      'NEOPETS_COOKIE is not set. Copy the Cookie header from a logged-in neopets.com ' +
        'request and start the server with it (see README.md).'
    );
    err.statusCode = 400;
    throw err;
  }

  // Re-derive the target at buy time; the page may have been open for a while.
  const target = await getTarget();

  const headers = {
    'User-Agent': UA,
    Cookie: COOKIE,
    'Accept-Language': 'en-US,en;q=0.9',
  };

  const pageRes = await fetch(BUY_PAGE_URL, { headers, redirect: 'follow' });
  if (!pageRes.ok) throw new Error(`Neopets buy page returned HTTP ${pageRes.status}`);
  const pageHtml = await pageRes.text();

  const refCk = scrapeRefCk(pageHtml);
  if (!refCk) {
    throw new Error(
      'Could not find the _ref_ck token on the buy page. The cookie is probably expired ' +
        'or the session is logged out — sign in again and copy a fresh Cookie header.'
    );
  }

  const body = new URLSearchParams({
    _ref_ck: refCk,
    type: 'buy',
    ticker_symbol: target.ticker,
    amount_shares: String(target.shares),
  });

  const buyRes = await fetch(PROCESS_URL, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/x-www-form-urlencoded',
      Referer: BUY_PAGE_URL,
      Origin: 'https://www.neopets.com',
    },
    body,
    redirect: 'follow',
  });

  const text = htmlToText(await buyRes.text());
  const outcome = classify(text);

  return {
    outcome,
    status: buyRes.status,
    target,
    message: relevantLines(text),
  };
}

/* ------------------------------------------------------------------ server */

function sendJson(res, code, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

async function handleApi(req, res, pathname) {
  try {
    if (pathname === '/api/target' && req.method === 'GET') {
      return sendJson(res, 200, { ok: true, target: await getTarget(), configured: Boolean(COOKIE) });
    }
    if (pathname === '/api/buy' && req.method === 'POST') {
      return sendJson(res, 200, { ok: true, ...(await buy()) });
    }
    return sendJson(res, 404, { ok: false, error: 'Not found' });
  } catch (err) {
    return sendJson(res, err.statusCode || 502, { ok: false, error: err.message });
  }
}

const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, `http://localhost:${PORT}`).pathname;

  if (pathname.startsWith('/api/')) return handleApi(req, res, pathname);

  if (pathname === '/' || pathname === '/index.html') {
    const file = path.join(__dirname, 'public', 'index.html');
    return fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        return res.end('Could not read public/index.html');
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(buf);
    });
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not found');
});

// Bind to loopback only: this process is holding a live session cookie.
server.listen(PORT, '127.0.0.1', () => {
  console.log(`neopets-stocks -> http://localhost:${PORT}`);
  console.log(`buying ${SHARES} shares of the cheapest stock at >= ${MIN_PRICE} NP`);
  if (!COOKIE) console.log('NEOPETS_COOKIE not set - prices will load, buying will not.');
});
