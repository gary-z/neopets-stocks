// Re-serves the neostocks ticker feed with CORS headers so the static page can
// read it straight from the browser.
//
// The upstream URL is fixed here on purpose. A worker that forwarded whatever
// arrived in a ?url= parameter would be a public open proxy, and public open
// proxies are exactly the unreliable thing this replaces.

const UPSTREAM = 'https://neostocks.info/api/tickers?period=1d';

// Neopets moves prices a few times a day, so a minute of staleness is invisible
// to a visitor while keeping repeat visits off neostocks entirely.
const CACHE_SECONDS = 60;

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, HEAD, OPTIONS',
  'access-control-max-age': '86400'
};

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return error('method not allowed', 405, { allow: 'GET, HEAD, OPTIONS' });
    }

    let upstream;
    try {
      upstream = await fetch(UPSTREAM, {
        headers: { accept: 'application/json' },
        cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true }
      });
    } catch (err) {
      return error('upstream unreachable', 502);
    }

    if (!upstream.ok) {
      return error('upstream returned ' + upstream.status, 502);
    }

    // Passed through as text rather than parsed and re-serialized: the page
    // does its own parsing, and this way a change in the feed's shape is not
    // also a change here.
    return new Response(upstream.body, {
      headers: {
        ...CORS,
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'public, max-age=' + CACHE_SECONDS
      }
    });
  }
};

// Failures answer with a non-2xx status so the page's fetch treats them as a
// miss and moves on, and with CORS headers so it can see them at all.
function error(message, status, extra) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      ...CORS,
      ...(extra || {}),
      'content-type': 'application/json; charset=utf-8'
    }
  });
}
