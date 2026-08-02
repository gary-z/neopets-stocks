# neopets-stocks

A URL that redirects straight to the Neopets buy page with the cheapest stock trading at 15 NP or
above already selected. You fill in the share count and click **Buy Shares** yourself.

The price is looked up **when you load the page**, not on a timer. One Cloudflare Worker, no cron,
nothing published ahead of time.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session.
[neostocks.info](https://neostocks.info) tracks the market publicly and bootstraps its summary
table into the served HTML as a `window.__data__` literal, with a current price per ticker:

```json
{"summary_data": {"1d": [{"ticker": "ACFI", "curr": 20, "update_time_nst": "..."}]}}
```

neostocks sends no `Access-Control-Allow-Origin`, so a browser can't read that from page
JavaScript — which is the entire reason there's a server here at all. The Worker fetches it
server-side on each request, picks the cheapest stock at or above the minimum, and answers with a
`302` to that stock's Neopets buy URL. Nothing is stored and nothing is built in advance.

Two consequences worth knowing:

- The redirect is a `302` with `Cache-Control: no-store`. A `301` would be cached by the browser
  and pin you to one ticker forever.
- The upstream fetch is cached at Cloudflare's edge for 120 seconds, so a burst of loads makes one
  request to neostocks. That never serves a stale price: neostocks only resamples every 15 minutes.

## Routes

| Route      | Response                                                         |
| ---------- | ---------------------------------------------------------------- |
| `/`        | `302` to the Neopets buy page for the chosen stock                |
| `/json`    | The same decision as JSON — ticker, price, candidates, timestamp  |
| `?min=<n>` | Override the 15 NP floor on either route                          |

`/json` exists because `/` bounces you off the site instantly, which makes it awkward to see what
was picked and why:

```console
$ curl https://neopets-stocks.<your-subdomain>.workers.dev/json
{"ticker":"TPP","price":15,"minPrice":15,"candidates":25,"tracked":44, ...}
```

Failures are answered, not swallowed: `502` if neostocks can't be reached or parsed, `404` if
nothing trades at or above the minimum, `400` for a nonsense `min`. In a browser each of those
renders a short page linking to the plain stock market so the trip isn't wasted.

## Deploying

Free tier is 100,000 requests/day, which this will not trouble.

One-time setup:

1. Create a Cloudflare account, then an API token from the **Edit Cloudflare Workers** template
   (My Profile → API Tokens).
2. Grab your account ID from the Workers & Pages dashboard sidebar.
3. Add both as repository secrets: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.

After that, `.github/workflows/deploy.yml` deploys on every push to `main`. The Worker lands at
`https://neopets-stocks.<your-subdomain>.workers.dev`; the subdomain is chosen the first time you
deploy anything. To use your own domain instead, add a `routes` entry to `wrangler.toml`.

The `check` job is split from `deploy` on purpose: it passes or fails on this repo's code and
neostocks alone, so it stays a useful signal on branches and forks where the Cloudflare secrets
aren't available. It hits neostocks live — a fixture would hide the one breakage worth catching,
which is neostocks changing shape.

## Local development

```bash
npm install
npm run check     # fetch and print the pick, no server
npm run dev       # http://127.0.0.1:8787
npm run deploy    # deploy by hand (needs `npx wrangler login` first)
```

`curl -sI localhost:8787` shows the redirect without following it; `/json` shows the reasoning.

### Options

| Env var / param | Default | Meaning                                 |
| --------------- | ------- | --------------------------------------- |
| `MIN_PRICE`     | `15`    | Minimum share price for `npm run check` |
| `?min=`         | `15`    | Same, per-request, for the Worker       |

## Notes

- Neopets caps purchases at 1,000 shares per day, so this is one visit per day.
- The 15 NP floor is Neopets' own rule: *"You can only purchase shares in companies that trade at
  15 NP per share or above."*
- Neopets fills the ticker box from `?ticker=`, but not the share count — that part is yours.
- A slightly-off pick costs nothing: you see the real price on the Neopets page before confirming,
  and Neopets rejects anything below 15 NP itself.
