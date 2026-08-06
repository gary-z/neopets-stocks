#!/usr/bin/env python3
"""How much capital does the buy-at-15 / sell-at-60 strategy keep tied up?

The strategy: every day buy 1000 shares of the cheapest ticker priced at 15 or
more (15 is the game's minimum purchase price), and sell a holding the moment it
reaches 60.

Because the strategy buys exactly one lot per day and holds it until that ticker
touches 60, the steady-state answer is Little's law:

    average capital tied up = (lots bought per day) * E[cost of a lot * days held]
                            = 1000 * E[buy price * first passage time to 60]

Tickers are interchangeable and a ticker's move depends only on its current
price, so the first passage time is a property of the price alone and comes out
of a 54-state absorbing Markov chain (prices 6..59, absorbed at >= 60) fitted to
the pooled day-over-day transitions in data/archived_prices.csv.

Run with --market-sim to additionally simulate a full 43-ticker market for
centuries of days, which cross-checks the mean and gives the distribution of
capital (the mean alone does not tell you how large a bankroll the strategy
needs).
"""

import argparse
import collections
import csv
import datetime
import math
import os

SELL = 60          # sell as soon as a holding reaches this
MIN_BUY = 15       # the game will not sell you a stock priced below this
SHARES = 1000      # per-day purchase limit
PRICE_FLOOR = 6    # no ticker-day in the archive is below this
PRICE_CAP = 1505   # nor above this

DATA = os.path.join(os.path.dirname(__file__), os.pardir, "data", "archived_prices.csv")


def load():
    """Prices by day, split into runs of consecutive observed days.

    The archive's NA gaps are collection outages - every ticker goes missing on
    the same days - so they are missing data, not delistings. Transitions must
    not be measured across a gap, hence the split into contiguous blocks.
    """
    rows = list(csv.DictReader(open(DATA)))
    tickers = sorted({r["ticker"] for r in rows})
    px = collections.defaultdict(dict)
    for r in rows:
        px[r["time"]][r["ticker"]] = None if r["curr"] == "NA" else int(r["curr"])

    days = sorted(d for d in px if any(v is not None for v in px[d].values()))
    parsed = [datetime.date.fromisoformat(d) for d in days]
    blocks, start = [], 0
    for i in range(1, len(parsed)):
        if (parsed[i] - parsed[i - 1]).days != 1:
            blocks.append(days[start:i])
            start = i
    blocks.append(days[start:])
    return px, tickers, blocks


def transitions(px, tickers, blocks):
    """price today -> Counter of price tomorrow, pooled over all tickers."""
    trans = collections.defaultdict(collections.Counter)
    for block in blocks:
        for i in range(1, len(block)):
            today, tomorrow = px[block[i - 1]], px[block[i]]
            for t in tickers:
                if today[t] is not None and tomorrow[t] is not None:
                    trans[today[t]][tomorrow[t]] += 1
    return trans


def buy_prices(px, blocks):
    """What the strategy pays each day: the cheapest ticker at or above 15."""
    return collections.Counter(
        min(v for v in px[d].values() if v is not None and v >= MIN_BUY)
        for block in blocks
        for d in block
    )


def solve(trans, reward):
    """Solve f(p) = reward(p, q) summed over one step, absorbing at >= SELL.

    reward(p, q) is added when the chain steps p -> q; f(q) is carried on only
    while q is still below SELL. With reward = 1 this gives expected days to
    absorption, with reward = q it gives the expected selling price.
    """
    states = sorted(p for p in trans if p < SELL)
    idx = {p: i for i, p in enumerate(states)}
    n = len(states)

    aug = [[0.0] * (n + 1) for _ in range(n)]
    for p in states:
        i = idx[p]
        total = sum(trans[p].values())
        aug[i][i] += 1.0
        for q, c in trans[p].items():
            w = c / total
            aug[i][n] += w * reward(p, q)
            if q < SELL:
                aug[i][idx[q]] -= w

    for col in range(n):  # Gaussian elimination, partial pivoting
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[piv] = aug[piv], aug[col]
        d = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= d
        for r in range(n):
            if r != col and aug[r][col]:
                f = aug[r][col]
                for j in range(col, n + 1):
                    aug[r][j] -= f * aug[col][j]
    return {p: aug[idx[p]][n] for p in states}


def survival(trans, weight):
    """weight-weighted P(lot still held after k days), for k = 0, 1, 2, ...

    Summing this is the same expectation the linear solve produces; iterating it
    is what shows *which* holding periods the mean is made of and how long a
    cold start takes to converge.
    """
    states = sorted(p for p in trans if p < SELL)
    idx = {p: i for i, p in enumerate(states)}
    n = len(states)
    Q = [[0.0] * n for _ in range(n)]
    for p in states:
        total = sum(trans[p].values())
        for q, c in trans[p].items():
            if q < SELL:
                Q[idx[p]][idx[q]] = c / total

    cur = [0.0] * n
    for p, w in weight.items():
        cur[idx[p]] += w
    out = []
    while True:
        out.append(sum(cur))
        if out[-1] < 1e-12:
            return out
        nxt = [0.0] * n
        for i, ci in enumerate(cur):
            if ci:
                row = Q[i]
                for j in range(n):
                    nxt[j] += ci * row[j]
        cur = nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market-sim", action="store_true",
                    help="also simulate a synthetic 43-ticker market (needs numpy)")
    ap.add_argument("--years", type=int, default=400)
    args = ap.parse_args()

    px, tickers, blocks = load()
    trans = transitions(px, tickers, blocks)
    buys = buy_prices(px, blocks)
    n_days = sum(buys.values())
    p_buy = {p: c / n_days for p, c in buys.items()}

    print("%d tickers, %d observed days in %d contiguous blocks, %d transitions"
          % (len(tickers), n_days, len(blocks), sum(sum(c.values()) for c in trans.values())))
    print("\nbuy price is nearly pinned to the 15 floor:")
    for p, w in sorted(p_buy.items()):
        print("   %2d NP on %6.2f%% of days" % (p, 100 * w))

    hold = solve(trans, lambda p, q: 1.0)
    sale = solve(trans, lambda p, q: q if q >= SELL else 0.0)

    print("\nexpected days for a ticker at price p to first reach %d:" % SELL)
    for p in sorted(hold):
        if p <= 20 or p % 10 == 0 or p >= 58:
            print("   p=%2d  %7.1f days   (n=%d)" % (p, hold[p], sum(trans[p].values())))
    print("   ^ nearly flat below 60: the barrier is crossing 60 at all, not the")
    print("     distance to it (prices in the 46-80 band drift down ~5%/day).")

    e_price = sum(w * p for p, w in p_buy.items())
    e_days = sum(w * hold[p] for p, w in p_buy.items())
    e_cost_days = sum(w * p * hold[p] for p, w in p_buy.items())
    capital = SHARES * e_cost_days

    print("\nE[buy price]           %10.3f NP" % e_price)
    print("E[days held]           %10.1f days" % e_days)
    print("E[buy price * days]    %10.1f NP-days" % e_cost_days)
    print("\n=> average capital tied up = %d shares/day * %.1f NP-days" % (SHARES, e_cost_days))
    print("   = %.2f million NP  (%.0f shares held at an average cost of %.2f NP)"
          % (capital / 1e6, SHARES * e_days, e_price))

    cost_weight = {p: w * p for p, w in p_buy.items()}
    s_cost = survival(trans, cost_weight)
    print("\nwhich holding periods that mean is made of:")
    for lo, hi in [(0, 365), (365, 730), (730, 1095), (1095, 1825), (1825, len(s_cost))]:
        part = sum(s_cost[lo:hi])
        print("   days %5d-%-5d %6.2fM NP  (%4.1f%%)" % (lo, hi, SHARES * part / 1e6,
                                                         100 * part / e_cost_days))
    print("   ^ 80% of it sits inside 2 years, the range the archive can check")
    print("     directly, so the answer is not an artifact of tail extrapolation.")

    s_unw = survival(trans, p_buy)
    print("\nholding time for one lot: median %d days, p90 %d, p99 %d"
          % tuple(next(i for i, s in enumerate(s_unw) if s <= 1 - q) for q in (0.5, 0.9, 0.99)))

    print("\ncapital after N days from a cold start (the strategy converges slowly):")
    running = 0.0
    marks = {30, 90, 180, 365, 730, 1095, 1825, 3650}
    for k, s in enumerate(s_cost):
        running += s
        if k + 1 in marks:
            print("   N=%5d (%4.1f yr)  %6.2fM NP  (%3.0f%% of steady state)"
                  % (k + 1, (k + 1) / 365, SHARES * running / 1e6, 100 * running / e_cost_days))

    e_sale = sum(w * sale[p] for p, w in p_buy.items())
    profit = SHARES * (e_sale - e_price)
    print("\nfor context, what that capital earns: sells at %.2f NP on average," % e_sale)
    print("   %.0f NP profit per lot, one lot/day in steady state" % profit)
    print("   = %.1fM NP/year on %.2fM tied up, a %.0f%% annual return on capital"
          % (365 * profit / 1e6, capital / 1e6, 100 * 365 * profit / capital))

    if args.market_sim:
        market_sim(px, tickers, blocks, trans, buys, args.years, capital)


def market_sim(px, tickers, blocks, trans, buys, years, analytic):
    """Simulate 43 interchangeable tickers and run the strategy on them.

    Little's law already fixes the mean; this checks it end to end and gives the
    spread, which is what actually decides how much bankroll is needed. High
    prices are too sparsely observed to sample a next price directly (a state
    seen twice would become a near-deterministic cycle), so those states borrow
    pooled log-returns from their price neighbourhood - scale-free is the right
    shape there, since above ~80 NP the drift is ~0 and moves are proportional.
    """
    import numpy as np

    log_moves = collections.defaultdict(list)
    for p, ctr in trans.items():
        for q, c in ctr.items():
            log_moves[p].extend([math.log(q / p)] * c)

    RAW_MIN, POOL_MIN = 100, 400
    kernel, smoothed = {}, 0
    for p in range(PRICE_FLOOR, PRICE_CAP + 1):
        if sum(trans[p].values()) >= RAW_MIN:
            kernel[p] = np.array([q for q, c in trans[p].items() for _ in range(c)],
                                 dtype=np.int32)
            continue
        width = 0.15
        while True:
            pool = [r for q in log_moves if abs(math.log(q / p)) <= width
                    for r in log_moves[q]]
            if len(pool) >= POOL_MIN or width > 2.0:
                break
            width *= 1.3
        kernel[p] = np.clip(np.round(p * np.exp(np.array(pool))), PRICE_FLOOR,
                            PRICE_CAP).astype(np.int32)
        smoothed += 1

    sizes = np.array([len(kernel[p]) for p in range(PRICE_FLOOR, PRICE_CAP + 1)])
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    flat = np.concatenate([kernel[p] for p in range(PRICE_FLOOR, PRICE_CAP + 1)])
    rng = np.random.default_rng(7)

    def step(prices):
        i = prices - PRICE_FLOOR
        return flat[offsets[i] + (rng.random(prices.size) * sizes[i]).astype(np.int64)]

    print("\n--- synthetic market: %d raw states, %d smoothed, %d years ---"
          % (PRICE_CAP - PRICE_FLOOR + 1 - smoothed, smoothed, years))
    n_tick = len(tickers)
    prices = np.full(n_tick, MIN_BUY, dtype=np.int32)
    for _ in range(20 * 365):  # burn in past the artificial start
        prices = step(prices)

    runlen = years * 365
    cost = np.zeros(n_tick, dtype=np.int64)
    shares = np.zeros(n_tick, dtype=np.int64)
    tied = np.empty(runlen, dtype=np.int64)
    seen = np.zeros(PRICE_CAP + 2, dtype=np.int64)
    sim_buys = collections.Counter()
    for d in range(runlen):
        prices = step(prices)
        seen += np.bincount(prices, minlength=PRICE_CAP + 2)
        done = (prices >= SELL) & (shares > 0)
        cost[done] = 0
        shares[done] = 0
        elig = np.where(prices >= MIN_BUY)[0]
        if elig.size:
            j = elig[np.argmin(prices[elig])]
            sim_buys[int(prices[j])] += 1
            cost[j] += SHARES * int(prices[j])
            shares[j] += SHARES
        tied[d] = cost.sum()

    real = collections.Counter(v for d in px for v in px[d].values() if v is not None)
    n_real, n_sim = sum(real.values()), seen.sum()
    print("%-24s %9s %9s" % ("cross-section check", "archive", "sim"))
    for label, test in [("price < 15", lambda p: p < 15), ("15-20", lambda p: 15 <= p <= 20),
                        ("21-59", lambda p: 21 <= p <= 59), (">= 60", lambda p: p >= 60)]:
        print("%-24s %9.4f %9.4f"
              % (label, sum(c for p, c in real.items() if test(p)) / n_real,
                 sum(seen[p] for p in range(PRICE_FLOOR, PRICE_CAP + 1) if test(p)) / n_sim))
    n_b, n_s = sum(buys.values()), sum(sim_buys.values())
    print("%-24s %9.4f %9.4f" % ("mean buy price",
                                 sum(p * c for p, c in buys.items()) / n_b,
                                 sum(p * c for p, c in sim_buys.items()) / n_s))

    print("\ncapital tied up: mean %.2fM NP (Little's law says %.2fM), sd %.2fM"
          % (tied.mean() / 1e6, analytic / 1e6, tied.std() / 1e6))
    for q in (5, 25, 50, 75, 95, 99):
        print("   p%-3d %7.2fM NP" % (q, np.percentile(tied, q) / 1e6))
    print("   max  %7.2fM NP" % (tied.max() / 1e6))


if __name__ == "__main__":
    main()
