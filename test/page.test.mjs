// The page's inline script, run against a stubbed fetch and a virtual clock so
// its timing can be checked without a browser and without waiting.
// Run with `node --test test/`.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.indexOf('</script>'));

const MARKET = 'https://www.neopets.com/stockmarket.phtml';
const BUY = MARKET + '?type=buy&ticker=';
const FEED = [
  { ticker: 'CHE', curr: 14 },   // below the floor
  { ticker: 'ZED', curr: 15 },
  { ticker: 'ABC', curr: 15 },   // tie at the floor - ABC wins on ticker
  { ticker: 'HIG', curr: 40 }
];

// Runs the script with the worker hostname substituted in, and answers its
// fetch with `reply`: { body | badBody | reject | ok/status, after }.
// Returns where it navigated, when, and every request it made.
async function visit({ reply, worker = 'mine.workers.dev' }) {
  const requests = [];
  let clock = 0, timers = [], id = 0, landed = null;

  const sandbox = {
    document: {
      getElementById: (elId) => ({
        textContent: elId === 'floor' ? '15' : '',
        href: MARKET
      })
    },
    location: { replace: (url) => { if (landed === null) landed = { url, at: clock }; } },
    setTimeout: (fn, ms) => { timers.push({ fn, due: clock + (ms || 0), id: ++id }); return id; },
    fetch: (url) => {
      requests.push({ url, at: clock });
      return new Promise((resolve, reject) => {
        timers.push({
          due: clock + reply.after, id: ++id,
          fn: () => reply.reject
            ? reject(new Error(reply.reject))
            : resolve({
                ok: reply.ok !== false,
                status: reply.status || 200,
                json: () => reply.badBody
                  ? Promise.reject(new SyntaxError('not json'))
                  : Promise.resolve(reply.body)
              })
        });
      });
    }
  };

  vm.createContext(sandbox);
  vm.runInContext(script.replace('YOUR-SUBDOMAIN.workers.dev', worker), sandbox);

  // Flush pending promises, then jump the clock to whatever is due next.
  for (let i = 0; i < 500 && timers.length; i++) {
    for (let j = 0; j < 20; j++) await Promise.resolve();
    timers.sort((a, b) => a.due - b.due || a.id - b.id);
    const next = timers.shift();
    clock = Math.max(clock, next.due);
    next.fn();
  }
  for (let j = 0; j < 50; j++) await Promise.resolve();

  return { requests, landed };
}

test('sends the visitor to the cheapest stock at or above the floor', async () => {
  const { landed } = await visit({ reply: { body: FEED, after: 200 } });
  assert.equal(landed.url, BUY + 'ABC');
});

test('talks to the worker and nothing else', async () => {
  const { requests } = await visit({ reply: { body: FEED, after: 200 } });
  assert.equal(requests.length, 1);
  assert.match(requests[0].url, /workers\.dev/);
  assert.equal(requests[0].at, 0);
});

test('falls back the moment the worker returns an error status', async () => {
  const { landed } = await visit({ reply: { ok: false, status: 502, after: 50 } });
  assert.deepEqual(landed, { url: MARKET, at: 50 });
});

test('falls back the moment the worker is unreachable', async () => {
  const { landed } = await visit({ reply: { reject: 'offline', after: 30 } });
  assert.deepEqual(landed, { url: MARKET, at: 30 });
});

test('falls back on a body it cannot parse', async () => {
  const { landed } = await visit({ reply: { badBody: true, after: 40 } });
  assert.equal(landed.url, MARKET);
});

test('gives up at the deadline rather than leaving the visitor waiting', async () => {
  const { landed } = await visit({ reply: { body: FEED, after: 99000 } });
  assert.deepEqual(landed, { url: MARKET, at: 4000 });
});

test('ignores an answer that arrives after the deadline', async () => {
  const { landed } = await visit({ reply: { body: FEED, after: 5000 } });
  assert.deepEqual(landed, { url: MARKET, at: 4000 },
    'a second navigation would yank the page out from under the visitor');
});

// The placeholder ships in the repo until the worker is deployed, so this is
// the state of the page for anyone who merges before deploying.
test('an unconfigured worker costs no request and no wait', async () => {
  const { requests, landed } = await visit({
    worker: 'YOUR-SUBDOMAIN.workers.dev',
    reply: { body: FEED, after: 100 }
  });
  assert.equal(requests.length, 0);
  assert.deepEqual(landed, { url: MARKET, at: 0 });
});

test('falls back when nothing is trading above the floor', async () => {
  const { landed } = await visit({ reply: { body: [{ ticker: 'LOW', curr: 3 }], after: 40 } });
  assert.equal(landed.url, MARKET);
});

test('skips malformed rows instead of choking on them', async () => {
  const { landed } = await visit({ reply: { after: 40, body: [
    null,
    { ticker: 'NAN', curr: '20' },   // price as a string
    { curr: 18 },                    // no ticker
    { ticker: 'GUD', curr: 22 }
  ] } });
  assert.equal(landed.url, BUY + 'GUD');
});
