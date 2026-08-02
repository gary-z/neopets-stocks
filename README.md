# neopets-stocks

A static page that redirects straight to the Neopets buy page with the cheapest stock trading at
15 NP or above already selected. You fill in the share count and click **Buy Shares** yourself.

Four files, no build step, no server. `index.html` is the whole thing.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session.
[neostocks.info](https://neostocks.info) tracks the market publicly and — undocumented, but plainly
public; see [`R/api.R`](https://github.com/glin/neostocks/blob/main/R/api.R) — serves it as JSON at
`https://neostocks.info/api/tickers?period=1d`:

```json
[{"ticker": "ACFI", "curr": 20, "update_time_nst": "...", "...": "..."}]
```

The one thing it does not send is `Access-Control-Allow-Origin`, so a page on another origin can't
read it directly. Public CORS proxies re-serve that JSON with the header attached, which is what
lets the page do its own pick on load. It tries [cors.eu.org](https://cors.eu.org) first, then
[r.jina.ai](https://r.jina.ai) and [allorigins](https://allorigins.win) if that stalls past 1.5s.
First answer wins.

### If the fetch fails

Both the fallback link and the `<noscript>` meta refresh point at
`https://www.neopets.com/stockmarket.phtml` — the stock market itself, where you can pick a stock by
hand. The page falls back to it when no proxy answers within 4 seconds, or when JavaScript is off.

It is not a hardcoded ticker on purpose: a fixed pick goes stale, and Neopets refuses to sell a
stock that has since fallen below 15 NP — a worse landing spot than the market page itself.

Depending on strangers' free proxies is the real cost here, and they do come and go. The clean fix
is upstream: one `headers` argument on the `shiny::httpResponse` in neostocks' `api.R` would make
that API directly readable and let the proxies be deleted. Worth an issue on
[glin/neostocks](https://github.com/glin/neostocks) if this ever matters enough.

## Deploying

**Settings → Pages → Source → Deploy from a branch → `main` / `(root)`.** That is the entire
deploy — pushing to `main` publishes.

Caveats worth knowing:

- **Pages on a private repo requires a paid plan** (Pro, Team, or Enterprise). On Free, the Pages
  section won't offer to publish until the repo is public.
- A published Pages site is world-readable even when the repo is private, unless you're on
  Enterprise with access control. Nothing here is sensitive — it's a ticker in a URL — but it is
  public once deployed.
- The redirect waits on a network round trip, so it takes about a second. Four seconds is the worst
  case before it gives up and uses the fallback link.
- neostocks samples every 15 minutes, so "live" prices are still up to 15 minutes old. That only
  ever costs a slightly-off pick — you see the real price on the Neopets page before confirming.

## Local development

Edit `index.html`. To try it, serve the directory over HTTP:

```bash
python3 -m http.server 8000     # then open http://localhost:8000
```

Opening the file over `file://` exercises the fallback rather than the live fetch, since the proxies
won't return CORS headers to a null origin.

The 15 NP floor lives in the `#floor` span, which the script reads — change it there and the visible
text and the pick stay in step.

## Notes

- Neopets caps purchases at 1,000 shares per day, so this is one visit per day.
- The 15 NP floor is Neopets' own rule: *"You can only purchase shares in companies that trade at
  15 NP per share or above."*
