# neopets-stocks

A static page with one button. It sends you to the Neopets buy page with the cheapest stock
trading at 15 NP or above already selected — you click **Buy Shares** yourself.

No server. Hosted on GitHub Pages.

## How the buy actually works

The buy control on `stockmarket.phtml?type=buy` is a **POST**, not a GET:

```html
<form action="https://www.neopets.com/process_stockmarket.phtml" method="post">
  <input type="hidden" name="_ref_ck" value="...">   <!-- per-session token -->
  <input type="hidden" name="type" value="buy">
  <input type="text" name="ticker_symbol">
  <input type="text" name="amount_shares" maxlength="5">
```

A static site can't submit that for you: `_ref_ck` is session-scoped, and cookies don't ride along
on a cross-site POST. So the page doesn't try — it hands the order to Neopets pre-selected and
lets you confirm it there.

What the URL can and can't prefill, confirmed by testing:

| Field               | Prefills from URL? |
| ------------------- | ------------------ |
| Ticker symbol       | **yes** — `?type=buy&ticker=TPP` |
| Number of shares    | **no** — `amount_shares` / `shares` params are ignored |

Hence the bookmarklet on the page: drag it to your bookmarks bar once, click it on the buy page,
and it fills the share count. It reads the ticker from the buy page's own URL rather than baking
one in, so it keeps working after the target stock changes — drag it once, never again.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session.
[neostocks.info](https://neostocks.info) tracks the market publicly and bootstraps its summary
table into the served HTML as a `window.__data__` literal, with a current price per ticker:

```json
{"summary_data": {"1d": [{"ticker": "ACFI", "curr": 20, "update_time_nst": "..."}]}}
```

neostocks sends no `Access-Control-Allow-Origin`, so the browser can't read that directly. Instead
`scripts/build.js` fetches it in CI, picks the cheapest stock at or above 15 NP, and writes
`data.json` beside `index.html`. The page then reads it same-origin.

## Deploying

`.github/workflows/publish.yml` rebuilds and redeploys about every 15 minutes, matching the
neostocks refresh. Nothing is committed back to the repo — each run publishes a fresh artifact.

One-time setup: **Settings → Pages → Source → GitHub Actions**.

Caveats worth knowing:

- GitHub delays scheduled workflows under load, so prices can be older than 15 minutes. The page
  always shows the timestamp it built from.
- Scheduled workflows are disabled after 60 days without repo activity.
- A stale target only ever costs you a slightly-off pick — you see the real price on the Neopets
  page before confirming, and Neopets rejects anything below 15 NP itself.

## Local development

```bash
node scripts/build.js          # writes _site/{index.html,data.json}
python3 -m http.server -d _site 8899
```

Then open <http://localhost:8899>. Serve it rather than opening the file directly — `fetch` on a
`file://` page can't read `data.json`.

### Options

| Env var     | Default | Meaning             |
| ----------- | ------- | ------------------- |
| `SHARES`    | `1000`  | Shares per order    |
| `MIN_PRICE` | `15`    | Minimum share price |

## Notes

- Neopets caps purchases at 1,000 shares per day, so this is one click per day.
- The 15 NP floor is Neopets' own rule: *"You can only purchase shares in companies that trade at
  15 NP per share or above."*
