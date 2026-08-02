# neopets-stocks

A static page that redirects to the Neopets Stock Market buy page with the cheapest stock trading at
15 NP or above already selected.

The prices come from [neostocks.info](https://neostocks.info), which serves its JSON without an
`Access-Control-Allow-Origin` header, so the browser cannot read it from this page's origin. `worker/`
is a small Cloudflare Worker that fetches that feed and re-serves it with CORS headers. It is the only
source the page uses: public CORS proxies used to do this job and were unreliable enough that visitors
were regularly dropped on the plain stock market page. When the worker doesn't answer within four
seconds the page falls back to that same link, so the worker being down costs a visitor the ticker
choice and nothing else.

## Deploying

The page is published by GitHub Pages on every push to `main`. The worker is published by
`.github/workflows/deploy-worker.yml` on every push to `main` that touches `worker/`, so the two halves
of the site stay in step without anyone remembering to redeploy.

The worker needs no bindings, no environment variables, and no paid plan. The free tier covers 100,000
requests a day, and responses are edge-cached for 60 seconds, so repeat visits within a minute do not
reach neostocks at all.

### Deploying by hand

Needed once to create the worker, and afterwards only to change where it is published:

```sh
cd worker
npx wrangler@latest login    # once, opens a browser
npx wrangler@latest deploy
```

### If the hostname changes

The deployed hostname lives in two places, and both have to move together:

1. the `WORKER` constant near the top of the script in `index.html` — this is the one visitors use;
2. the `WORKER_URL` repository variable, which only the post-deploy smoke test reads.

Miss the first and the page falls back to the plain stock market link on every visit. Miss the second
and deploys stay green while the smoke test checks a hostname nobody is using.

### Repository settings for automatic deploys

Under **Settings → Secrets and variables → Actions**:

| Kind | Name | Value | Required |
| --- | --- | --- | --- |
| Secret | `CLOUDFLARE_API_TOKEN` | An API token with the **Edit Cloudflare Workers** template | yes |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | Account ID from the Cloudflare dashboard sidebar | only if the token can see more than one account |
| Variable | `WORKER_URL` | The deployed `https://…workers.dev/` URL | no — enables the post-deploy smoke test |

Create the token at **My Profile → API Tokens → Create Token** in the Cloudflare dashboard; the *Edit
Cloudflare Workers* template already has the right permissions. It is shown once, so copy it straight
into the GitHub secret.

With `WORKER_URL` set, each deploy ends by fetching the live worker and failing the run if the CORS
header is missing or the feed no longer has the fields the page reads — the failures a green
`wrangler deploy` can still hide.

The workflow can also be run by hand from the **Actions** tab (**deploy worker → Run workflow**), which
is the way to redeploy after changing something in Cloudflare rather than in the repo.

## Tests

```sh
node --test
```

No dependencies and nothing to install. `test/worker.test.mjs` runs the worker against a stubbed
upstream; `test/page.test.mjs` runs the page's inline script against a stubbed `fetch` and a virtual
clock, so the four-second fallback is checked without waiting four seconds. Both run on every pull
request, and again before anything is deployed.

## Data

`data/archived_prices.csv` is a historical price dataset, kept for analysis. Nothing on the page reads
it.
