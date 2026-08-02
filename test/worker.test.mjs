// The worker with its upstream stubbed out. Run with `node --test test/`.
import test from 'node:test';
import assert from 'node:assert/strict';

import worker from '../worker/src/index.js';

const UPSTREAM = 'https://neostocks.info/api/tickers?period=1d';
const FEED = JSON.stringify([{ ticker: 'BLK', curr: 16 }]);

// Stubs global fetch for one test and hands back what the worker asked for.
function stubUpstream(reply) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    if (typeof reply === 'function') return reply();
    return reply;
  };
  return calls;
}

const get = (url = 'https://worker.example/') => worker.fetch(new Request(url));

test('serves the feed with the CORS header the page needs', async () => {
  stubUpstream(new Response(FEED, { status: 200 }));
  const res = await get();

  assert.equal(res.status, 200);
  assert.equal(await res.text(), FEED, 'body passed through untouched');
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
  assert.match(res.headers.get('content-type'), /^application\/json/);
});

test('asks the edge to cache, and tells the browser to as well', async () => {
  const calls = stubUpstream(new Response(FEED, { status: 200 }));
  const res = await get();

  assert.equal(calls[0].init.cf.cacheTtl, 60);
  assert.equal(calls[0].init.cf.cacheEverything, true);
  assert.equal(res.headers.get('cache-control'), 'public, max-age=60');
});

test('is not an open proxy: a caller-supplied url is ignored', async () => {
  const calls = stubUpstream(new Response(FEED, { status: 200 }));
  const res = await get('https://worker.example/?url=https://somewhere.else/');

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, UPSTREAM);
  assert.equal(res.status, 200);
});

test('answers a preflight without hitting the upstream', async () => {
  const calls = stubUpstream(new Response(FEED, { status: 200 }));
  const res = await worker.fetch(new Request('https://worker.example/', { method: 'OPTIONS' }));

  assert.equal(res.status, 204);
  assert.match(res.headers.get('access-control-allow-methods'), /GET/);
  assert.equal(calls.length, 0);
});

test('refuses methods it does not serve', async () => {
  stubUpstream(new Response(FEED, { status: 200 }));
  const res = await worker.fetch(new Request('https://worker.example/', { method: 'POST' }));

  assert.equal(res.status, 405);
  assert.equal(res.headers.get('allow'), 'GET, HEAD, OPTIONS');
});

// The page can only react to a failure it is allowed to read, so the CORS
// header has to survive the error paths too - without it the fetch rejects as
// an opaque network error and the visitor waits out the full deadline.
test('reports an upstream error as a readable 502', async () => {
  stubUpstream(new Response('down for maintenance', { status: 503 }));
  const res = await get();

  assert.equal(res.status, 502);
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
  assert.match(JSON.parse(await res.text()).error, /503/);
});

test('reports an unreachable upstream as a readable 502', async () => {
  stubUpstream(() => { throw new Error('ECONNRESET'); });
  const res = await get();

  assert.equal(res.status, 502);
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
  assert.equal(JSON.parse(await res.text()).error, 'upstream unreachable');
});
