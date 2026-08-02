# neopets-stocks

A static page that redirects straight to the Neopets buy page with the cheapest stock trading at
15 NP or above already selected. You fill in the share count and click **Buy Shares** yourself.

No server. Hosted on GitHub Pages.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session.
[neostocks.info](https://neostocks.info) tracks the market publicly and bootstraps its summary
table into the served HTML as a `window.__data__` literal, with a current price per ticker:

```json
{"summary_data": {"1d": [{"ticker": "ACFI", "curr": 20, "update_time_nst": "..."}]}}
```

neostocks sends no `Access-Control-Allow-Origin`, so the browser can't read that directly. Instead
`scripts/build.js` fetches it in CI, picks the cheapest stock at or above 15 NP, and substitutes
that stock's buy URL into `index.html`, which is a template holding a `__BUY_URL__` placeholder and
a meta refresh. The published page is that redirect and nothing else — no JavaScript, no data file.

## Deploying

`.github/workflows/publish.yml` rebuilds and redeploys about every 15 minutes, matching the
neostocks refresh. Nothing is committed back to the repo — each run publishes a fresh artifact.

The `build` job is split from `deploy` on purpose: the build passes or fails on this repo's code
alone, so it stays a useful signal even while the deploy half is blocked on repo settings.

One-time manual step: **Settings → Pages → Source → GitHub Actions** (pick that, not "Deploy from
a branch" — there's no folder to choose). The workflow can't do this itself: `GITHUB_TOKEN` can
deploy to Pages but not create the site, so `configure-pages` with `enablement: true` fails with
*"Resource not accessible by integration"*. It needs a repo admin.

**Deploys only happen from `main`**, for two independent reasons — the `github-pages` environment
rejects other branches before the job is dispatched, and GitHub only fires `schedule` triggers on
the default branch. A feature branch therefore can't publish, and can't refresh prices on a timer
either. On pull requests the deploy job is skipped and only `build` runs.

Caveats worth knowing:

- **Pages on a private repo requires a paid plan** (Pro, Team, or Enterprise). On Free, the
  Pages section won't offer GitHub Actions as a source until the repo is public.
- A published Pages site is world-readable even when the repo is private, unless you're on
  Enterprise with access control. Nothing here is sensitive — it's a ticker in a URL — but
  it is public once deployed.
- GitHub delays scheduled workflows under load, so the target can be older than 15 minutes.
- Scheduled workflows are disabled after 60 days without repo activity.
- A stale target only ever costs you a slightly-off pick — you see the real price on the Neopets
  page before confirming, and Neopets rejects anything below 15 NP itself.

## Local development

```bash
node scripts/build.js          # writes _site/index.html
```

Open `_site/index.html` — it will bounce you to Neopets immediately, so to inspect the page itself
read the file rather than loading it.

### Options

| Env var     | Default | Meaning             |
| ----------- | ------- | ------------------- |
| `MIN_PRICE` | `15`    | Minimum share price |

## Notes

- Neopets caps purchases at 1,000 shares per day, so this is one visit per day.
- The 15 NP floor is Neopets' own rule: *"You can only purchase shares in companies that trade at
  15 NP per share or above."*
