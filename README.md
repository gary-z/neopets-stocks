# neopets-stocks

A static page that redirects to the Neopets Stock Market buy page with the cheapest stock trading at
15 NP or above already selected.

The prices come from [neostocks.info](https://neostocks.info), which serves its JSON without an
`Access-Control-Allow-Origin` header, so the browser cannot read it from this page's origin. `worker/`
is a small Cloudflare Worker that fetches that feed and re-serves it with CORS headers. Public CORS
proxies used to do this job and were unreliable; one of them is still wired up as a backup, but it is
only contacted when the worker does not answer.

## Deploying the worker

From `worker/`:

```sh
npx wrangler@latest login    # once, opens a browser
npx wrangler@latest deploy
```

Deploy prints the hostname it published to, e.g.
`https://neopets-stocks-proxy.your-subdomain.workers.dev`. Put that in the `WORKER` constant near the
top of the script in `index.html`, replacing the `YOUR-SUBDOMAIN` placeholder, and commit. Until that
placeholder is replaced the page skips the worker entirely and runs on the backup proxy alone.

The worker needs no bindings, secrets, environment variables, or a paid plan. The free tier covers
100,000 requests a day, and responses are edge-cached for 60 seconds, so repeat visits within a minute
do not reach neostocks at all.

Sanity check after deploying:

```sh
curl -sI https://neopets-stocks-proxy.your-subdomain.workers.dev | grep -i access-control-allow-origin
```

`access-control-allow-origin: *` means the page can read it.

## Data

`data/archived_prices.csv` is a historical price dataset, kept for analysis. Nothing on the page reads
it.
