"""Loader for the archived Neopets price panel in data/archived_prices.csv."""
import pathlib

import numpy as np
import pandas as pd

CSV = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'archived_prices.csv'


def panel():
    """Wide panel: rows = calendar days, cols = tickers, values = price (NaN if unobserved).

    The archive is a perfect rectangle -- 43 tickers x 4451 consecutive days -- but
    1069-1073 of those days have no price for any ticker (whole days are missing from
    the archive, not individual listings). Those stay NaN and every consumer here
    drops them rather than interpolating.
    """
    df = pd.read_csv(CSV, parse_dates=['time'])
    p = df.pivot(index='time', columns='ticker', values='curr').sort_index()
    step = pd.Series(p.index).diff().dt.days.dropna().unique()
    assert set(step) == {1}, f'index is not contiguous daily: {step}'
    return p


def full_pairs(p=None):
    """Every (today, tomorrow) pair where both days were actually observed."""
    if p is None:
        p = panel()
    V = p.values
    pre, cur = V[:-1], V[1:]
    m = ~np.isnan(pre) & ~np.isnan(cur)
    tick = np.tile(p.columns.values, (len(V) - 1, 1))[m]
    date = np.repeat(p.index.values[1:, None], V.shape[1], axis=1)[m]
    x, y = pre[m].astype(int), cur[m].astype(int)
    return pd.DataFrame({'x': x, 'y': y, 'd': y - x, 'ticker': tick, 'date': date})


def windows(lags=3):
    """One row per (ticker, day) carrying today's price plus `lags` prior days.

    Used by the higher-order tests, which need history to condition on.
    """
    p = panel()
    V = p.values
    cols = {'y': V[lags:], 'x': V[lags - 1:-1]}
    for k in range(2, lags + 1):
        cols[f'x{k}'] = V[lags - k:-k]
    n_rows = V.shape[0] - lags
    out = pd.DataFrame({k: v.ravel() for k, v in cols.items()})
    out['ticker'] = np.tile(p.columns.values, (n_rows, 1)).ravel()
    out['date'] = np.repeat(p.index.values[lags:, None], V.shape[1], axis=1).ravel()
    out = out.dropna().astype({c: int for c in cols})
    out['d'] = out.y - out.x
    out['dprev'] = out.x - out.x2
    out['r'] = out.d / out.x
    out['rprev'] = out.dprev / out.x2
    out['rprev2'] = (out.x2 - out.x3) / out.x3
    return out.reset_index(drop=True)
