"""Replay every buy/sell rule on the real price paths -- no model involved.

For each historical day a stock traded at `b`, buy it, follow the actual archived
path, and sell the first day it trades at `s` or above. Discount the proceeds at
12.5% APR compounded daily. This is the check on strategy.py: if the fitted chain
is telling the truth, the two should agree.

    python analysis/backtest.py
"""
import numpy as np
import pandas as pd

import np_data

APR = 0.125
DELTA = 1.0 / (1.0 + APR / 365)


def _next_hit(prices, s):
    """first[i] = earliest index j >= i with prices[j] >= s, else -1."""
    out = np.full(len(prices), -1)
    nxt = -1
    for i in range(len(prices) - 1, -1, -1):
        v = prices[i]
        if v == v and v >= s:       # not NaN and at/above the target
            nxt = i
        out[i] = nxt
    return out


def run(buy_prices=(15,), thresholds=(65,), min_forward=0):
    """One row per (historical buy opportunity, sell rule).

    Trades still open when the archive ends are marked hit=False and valued at the
    last observed price, which understates them -- an unsold position would have been
    sold higher later. `min_forward` restricts buys to days with that many days of
    archive left, which is the clean way to remove the censoring.
    """
    p = np_data.panel()
    T = len(p)
    recs = []
    for s in thresholds:
        for tk in p.columns:
            v = p[tk].values
            nh = _next_hit(v, s)
            last = pd.Series(v).ffill().values[T - 1]
            for b in buy_prices:
                idx = np.where(v == b)[0]
                if min_forward:
                    idx = idx[idx < T - min_forward]
                if not len(idx):
                    continue
                j = nh[idx]
                hit = j >= 0
                tau = np.where(hit, j - idx, T - 1 - idx)
                sale = np.where(hit, v[np.clip(j, 0, T - 1)], last)
                recs.append(pd.DataFrame({'s': s, 'b': b, 'ticker': tk, 'tau': tau,
                                          'sale': sale, 'hit': hit}))
    r = pd.concat(recs, ignore_index=True)
    r['pv'] = DELTA ** r.tau * r.sale
    r['mult'] = r.pv / r.b
    return r


def summarize(r):
    def f(z):
        b = z.name[0]
        filled = z.tau[z.hit]
        return pd.Series({
            'n_trades': len(z),
            'pct_sold': 100 * z.hit.mean(),
            'median_days': np.median(filled) if len(filled) else np.nan,
            'mean_days': filled.mean() if len(filled) else np.nan,
            'mean_sale': z.sale.mean(),
            'PV_multiple': z['mult'].mean(),
            'PV_profit_per_share': z.pv.mean() - b,
        })
    return r.groupby(['b', 's']).apply(f, include_groups=False)


def ticker_bootstrap(r, b, s, n=2000, seed=0):
    """Resample whole tickers -- overlapping trades on one ticker are not independent."""
    sub = r[(r.b == b) & (r.s == s)]
    groups = [g['mult'].values for _, g in sub.groupby('ticker')]
    rng = np.random.default_rng(seed)
    out = [np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))]).mean()
           for _ in range(n)]
    return np.percentile(out, [2.5, 97.5])


def winning_threshold_bootstrap(r, b=15, n=1000, seed=1):
    sub = r[r.b == b]
    tickers = sorted(sub.ticker.unique())
    ths = sorted(sub.s.unique())
    tab = {tk: {s: g['mult'].values for s, g in gg.groupby('s')} for tk, gg in sub.groupby('ticker')}
    rng = np.random.default_rng(seed)
    wins = []
    for _ in range(n):
        pick = [tickers[j] for j in rng.integers(0, len(tickers), len(tickers))]
        means = [np.concatenate([tab[tk][s] for tk in pick]).mean() for s in ths]
        wins.append(ths[int(np.argmax(means))])
    return pd.Series(wins).value_counts(normalize=True).sort_index()


def main():
    print(f'{APR:.1%} APR compounded daily -> delta = {DELTA:.8f} per day\n')
    print('=' * 100)
    print('BUY AT 15, SELL AT s -- every opportunity in the archive')
    print('=' * 100)
    r = run(buy_prices=(15,), thresholds=range(20, 106, 5))
    g = summarize(r)
    print(g.to_string(float_format=lambda v: f'{v:12.3f}'))
    best = g['PV_multiple'].idxmax()
    print(f'\n  best threshold: {best[1]} NP  ({g.loc[best, "PV_multiple"]:.3f}x present value)')
    for s in (55, 60, 65, 70):
        lo, hi = ticker_bootstrap(r, 15, s)
        print(f'    sell at {s}: {g.loc[(15, s), "PV_multiple"]:.3f}x   95% CI over tickers '
              f'[{lo:.3f}, {hi:.3f}]')
    w = winning_threshold_bootstrap(r, 15)
    print('  bootstrap over tickers, which threshold wins:',
          {int(k): round(v, 3) for k, v in w.items() if v >= 0.02})

    print('\n' + '=' * 100)
    print('SAME, WITHOUT CENSORING (only buys with 5+ years of archive left to run)')
    print('=' * 100)
    r2 = run(buy_prices=(15,), thresholds=(50, 55, 60, 65, 70, 75, 80), min_forward=1825)
    print(summarize(r2).to_string(float_format=lambda v: f'{v:12.3f}'))
    print('  Now ~99% of trades actually close, and the multiples line up with the fitted')
    print('  chain in strategy.py (V(15)/15 = 3.69x).')

    print('\n' + '=' * 100)
    print('WHICH ENTRY PRICE? (exit fixed at 65)')
    print('=' * 100)
    r3 = run(buy_prices=tuple(range(6, 61)), thresholds=(65,))
    g3 = summarize(r3).reset_index()
    keep = [6, 8, 10, 12, 14, 15, 16, 17, 18, 19, 20, 25, 30, 40, 50, 60]
    print(g3[g3.b.isin(keep)].to_string(index=False, float_format=lambda v: f'{v:12.3f}'))
    print('  Monotone in the entry price: nothing about 15 is special except that it is the')
    print('  cheapest share the game will sell you.')

    print('\n' + '=' * 100)
    print('IS 15 ACTUALLY AVAILABLE? (cheapest stock priced 15+, which is what index.html buys)')
    print('=' * 100)
    v = np_data.panel().values.copy()
    v[v < 15] = np.nan
    cheapest = np.nanmin(np.where(np.isnan(v), np.inf, v), axis=1)
    cheapest = cheapest[np.isfinite(cheapest)]
    share = pd.Series(cheapest).value_counts(normalize=True).sort_index()
    print(f'  days with at least one stock at 15+: {len(cheapest):,}')
    print(f'  that cheapest price is exactly 15 on {100*share.get(15.0, 0):.1f}% of them, '
          f'<= 17 on {100*(cheapest <= 17).mean():.1f}%')


if __name__ == '__main__':
    main()
