# neopets-stocks

One button. Buys 1,000 shares of the cheapest Neopets stock trading at 15 NP or above.

## What the buy button actually is

From the saved buy page (`stockmarket.phtml?type=buy`), the form is a **POST**, not a GET:

```html
<form action="https://www.neopets.com/process_stockmarket.phtml" method="post">
  <input type="hidden" name="_ref_ck" value="c6fcd4782a859f2930cd0bc4b31420ee">
  <input type="hidden" name="type" value="buy">
  <input type="text" name="ticker_symbol" value="">
  <input type="text" name="amount_shares" size="5" maxlength="5">
  <input type="submit" value="Buy Shares">
</form>
```

`_ref_ck` is a per-session token embedded in the page, so it can't be hardcoded — the server
scrapes a fresh one off the buy page immediately before every order.

## Where prices come from

Neopets has no public price API, and its own stock list needs a session. [neostocks.info](https://neostocks.info)
tracks the market publicly and bootstraps its whole summary table into the served HTML as a
`window.__data__` literal, including a `curr` (current price) per ticker, refreshed every 15 minutes:

```json
{"summary_data": {"1d": [{"ticker": "ACFI", "curr": 20, "update_time_nst": "..."}]}}
```

The server reads that, keeps everything at or above 15 NP, and takes the cheapest.

## Why there's a server at all

The browser can't do either half by itself:

- neostocks sends no `Access-Control-Allow-Origin`, so a page can't fetch prices cross-origin.
- The buy is a cross-site POST, so cookies won't ride along (SameSite), and the token has to be
  read off a page the browser also can't fetch cross-origin.

`server.js` is plain Node with **no dependencies** and binds to `127.0.0.1` only — it holds a live
session cookie, so it should never be exposed.

## Setup

Requires Node 18+ (uses built-in `fetch`).

1. Log into neopets.com in your browser.
2. Open DevTools → Network → click any neopets.com request → copy the full **Cookie** request header.
3. Run:

```bash
NEOPETS_COOKIE='paste the whole cookie header here' node server.js
```

4. Open <http://localhost:8787> and click the button.

Without `NEOPETS_COOKIE` the page still loads and shows the target, but buying will fail with a
clear message.

### Options

| Env var          | Default | Meaning                                |
| ---------------- | ------- | -------------------------------------- |
| `NEOPETS_COOKIE` | —       | Cookie header from a logged-in session |
| `PORT`           | `8787`  | Local port                             |
| `SHARES`         | `1000`  | Shares per order                       |
| `MIN_PRICE`      | `15`    | Minimum share price                    |

## Notes

- The target is re-derived server-side at click time, not taken from whatever the page was
  showing, so a stale tab can't buy the wrong stock.
- Prices are up to 15 minutes old, so the ticker can move between the last neostocks sample and
  your order. Neopets rejects anything under 15 NP itself, and that rejection is reported back.
- Neopets returns HTTP 200 for both accepted and rejected orders, so the outcome is inferred from
  the response text. The heuristic is conservative — it only claims success on an explicit
  past-tense confirmation with a share count, and anything it can't place is reported as
  "check your portfolio". **The raw message from Neopets is always shown.**
- Neopets caps purchases at 1,000 shares per day, so this is one click per day.
- `_ref_ck` expires with the session. When the cookie goes stale the token scrape fails and the
  page tells you to log in and re-copy the cookie.
