# neopets-stocks

A static page that redirects to the Neopets Stock Market buy page with the cheapest stock trading at
15 NP or above already selected.

## Filling in the quantity

The redirect can only carry the ticker. Neopets prefills `ticker_symbol` from
`?type=buy&ticker=…` but ignores every URL parameter for the share count, and the buy control is a
POST to `process_stockmarket.phtml` carrying a session-scoped `_ref_ck` token, so nothing hosted
here can submit it for you either. The share box is left blank for you to type into.

A bookmarklet closes that gap. Create a bookmark and put this in its **URL** field in place of an
address:

```
javascript:(function(){var q=new URLSearchParams(location.search).get('ticker');var t=document.getElementsByName('ticker_symbol')[0];var a=document.getElementsByName('amount_shares')[0];if(!a){alert('Open the Neopets stock buy page first.');return;}if(t&&q&&!t.value){t.value=q;}a.value='1000';a.focus();})();
```

Unminified, it is:

```js
(function () {
  var q = new URLSearchParams(location.search).get('ticker');
  var t = document.getElementsByName('ticker_symbol')[0];
  var a = document.getElementsByName('amount_shares')[0];
  if (!a) { alert('Open the Neopets stock buy page first.'); return; }
  if (t && q && !t.value) { t.value = q; }
  a.value = '1000';
  a.focus();
})();
```

Clicking the bookmark while the buy page is open runs that script against the page: it fills the
share box with 1000 and puts the cursor there, leaving **Buy Shares** as the only thing to click.

The ticker is read back out of the buy page's own URL rather than baked into the bookmark, so the
same bookmark keeps working as the cheapest stock changes — save it once and never touch it again.
It writes the ticker field only when Neopets left it empty, so it won't clobber a stock you picked
by hand. On any other page there is no `amount_shares` field, and it says so and stops.

- Change `a.value='1000'` to buy a different amount. 1,000 is the Neopets daily cap, which is why
  it's the default.
- It has to be an actual bookmark. Chrome and Firefox strip the `javascript:` prefix when you paste
  one into the address bar.
