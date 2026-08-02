# neopets-stocks

A static page that redirects straight to the Neopets buy page with the cheapest stock trading at
15 NP or above already selected. You fill in the share count and click **Buy Shares** yourself.

No server. Hosted on GitHub Pages.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session.
[neostocks.info](https://neostocks.info) tracks the market publicly and — undocumented, but plainly
public; see [`R/api.R`](https://github.com/glin/neostocks/blob/main/R/api.R) — serves it as JSON at
`https://neostocks.info/api/tickers?period=1d`:

```json
[{"ticker": "ACFI", "curr": 20, "update_time_nst": "...", "...": "..."}]
```

The one thing it does not send is `Access-Control-Allow-Origin`, so a page on another origin can't
read it directly. That is the whole difficulty. Public CORS proxies re-serve it with the header
attached, and the page tries them in order — [cors.eu.org](https://cors.eu.org) first, then
[r.jina.ai](https://r.jina.ai) and [allorigins](https://allorigins.win) if it stalls past 1.5s.
First answer wins; `cheapest()` in `index.html` and the pick in `scripts/build.js` apply the same
rule, so they agree on the same market.

That makes prices current as of page load rather than as of the last deploy, which is what lets the
build run on push alone instead of on a timer.

### If the fetch fails

`scripts/build.js` still picks a target at build time and bakes it into `index.html` in place of the
`__BUY_URL__` placeholder. The page falls back to that when no proxy answers within 4 seconds, and a
`<noscript>` meta refresh uses it when JavaScript is off — so the page always redirects somewhere
sensible, it just may be a slightly stale somewhere.

Depending on strangers' free proxies is the real cost here, and they do come and go. The clean fix
is upstream: one `headers` argument on the `shiny::httpResponse` in neostocks' `api.R` would make
that API directly readable and let the proxies be deleted. Worth an issue on
[glin/neostocks](https://github.com/glin/neostocks) if this ever matters enough.

## Deploying

`.github/workflows/publish.yml` rebuilds and redeploys on pushes to `main`, and on
`workflow_dispatch`. There is no schedule: the page gets its own prices in the browser, so a deploy
is only needed when the code changes. Nothing is committed back to the repo — each run publishes a
fresh artifact.

Run it by hand if you want to refresh the baked-in fallback, which otherwise stays at whatever the
market looked like on the last deploy.

The `build` job is split from `deploy` on purpose: the build passes or fails on this repo's code
alone, so it stays a useful signal even while the deploy half is blocked on repo settings.

One-time manual step: **Settings → Pages → Source → GitHub Actions** (pick that, not "Deploy from
a branch" — there's no folder to choose). The workflow can't do this itself: `GITHUB_TOKEN` can
deploy to Pages but not create the site, so `configure-pages` with `enablement: true` fails with
*"Resource not accessible by integration"*. It needs a repo admin.

**Deploys only happen from `main`**: the `github-pages` environment rejects other branches before
the job is dispatched, so a feature branch can't publish. On pull requests the deploy job is skipped
and only `build` runs.

Caveats worth knowing:

- **Pages on a private repo requires a paid plan** (Pro, Team, or Enterprise). On Free, the
  Pages section won't offer GitHub Actions as a source until the repo is public.
- A published Pages site is world-readable even when the repo is private, unless you're on
  Enterprise with access control. Nothing here is sensitive — it's a ticker in a URL — but
  it is public once deployed.
- The redirect now waits on a network round trip, so it takes about a second instead of firing
  instantly. Four seconds is the worst case before it gives up and uses the baked-in pick.
- neostocks samples every 15 minutes, so "live" prices are still up to 15 minutes old.
- A stale target only ever costs you a slightly-off pick — you see the real price on the Neopets
  page before confirming, and Neopets rejects anything below 15 NP itself.

## Local development

```bash
node scripts/build.js          # writes _site/index.html
```

Open `_site/index.html` — it will bounce you to Neopets within a few seconds, so to inspect the page
itself read the file rather than loading it. Opening it over `file://` exercises the fallback rather
than the live fetch, since the proxies won't return CORS headers to a null origin; serve `_site`
over HTTP to see the real path.

### Options

`MIN_PRICE` is read by the build and baked into the page as `data-min-price`, so it applies to the
live pick too.

| Env var     | Default | Meaning             |
| ----------- | ------- | ------------------- |
| `MIN_PRICE` | `15`    | Minimum share price |

## Notes

- Neopets caps purchases at 1,000 shares per day, so this is one visit per day.
- The 15 NP floor is Neopets' own rule: *"You can only purchase shares in companies that trade at
  15 NP per share or above."*
