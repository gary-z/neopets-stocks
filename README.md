# neopets-stocks

A static page that redirects to the Neopets Stock Market buy page with the cheapest stock trading at
15 NP or above already selected.

## Analysis

[`analysis/`](analysis/README.md) works out, from the 2006-2018 price archive in `data/`, whether
those prices are Markov and what the best buy and sell prices are against a 12.5% APR opportunity
cost. Short version: the moves are Markov, all 43 tickers share one law, **buy at 15 and sell at 65**
— so the 15 NP floor this page already uses is the right one, and the usual "sell at 60" is within
2.2% of optimal.
