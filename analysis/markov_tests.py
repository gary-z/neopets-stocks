"""Is tomorrow's price a function of today's price alone?

H0 (Markov): P(x_{t+1} | x_t, x_{t-1}, ...) = P(x_{t+1} | x_t)

Every test conditions on today's price, then asks whether some piece of history
still carries information. Tests 6-7 ask the companion questions the trading
model relies on: do all 43 tickers share one law, and is that law stable in time.

    python analysis/markov_tests.py
"""
import numpy as np
import pandas as pd
from scipy import stats

import np_data


def price_bin(x):
    """Fine states: exact integer levels where data is dense, coarser in the tail."""
    edges = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23, 26, 30,
             35, 41, 48, 56, 66, 78, 92, 110, 135, 170, 220, 300, 450, 700, 10 ** 9]
    return np.searchsorted(edges, x, side='right') - 1


def coarse_bin(x):
    """8 heavily populated states."""
    return np.searchsorted(np.array([6, 9, 12, 15, 18, 21, 35, 70, 10 ** 9]), x, side='right') - 1


def test_1_momentum(df):
    print('=' * 78)
    print("TEST 1  Does yesterday's move predict tomorrow's, holding today's price fixed?")
    print('=' * 78)
    rows = []
    for b, g in df.groupby('b'):
        if len(g) < 200:
            continue
        rho, pv = stats.spearmanr(g.rprev, g.r)
        rows.append({'price_range': f'{g.x.min()}-{g.x.max()}', 'n': len(g), 'spearman': rho, 'p': pv})
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:9.4f}'))

    z = df.groupby('b')[['r', 'rprev']].transform(lambda s: s - s.mean())
    rho, p = stats.pearsonr(z.rprev, z.r)
    print(f'\n  Pooled within-price partial correlation:  r = {rho:+.4f}  p = {p:.3f}'
          f'   (explains {100*rho**2:.4f}% of variance)')
    z2 = df.groupby('b')[['r', 'rprev2']].transform(lambda s: s - s.mean())
    rho2, p2 = stats.pearsonr(z2.rprev2, z2.r)
    print(f'  Same using the move from two days back:   r = {rho2:+.4f}  p = {p2:.3f}')


def test_2_sign(df):
    print('\n' + '=' * 78)
    print("TEST 2  Cochran-Mantel-Haenszel on the SIGN of the move, stratified by price")
    print('=' * 78)
    g = df[(df.dprev != 0) & (df.d != 0)].copy()
    g['up_prev'] = (g.dprev > 0).astype(int)
    g['up_now'] = (g.d > 0).astype(int)
    num = den = 0.0
    for _, s in g.groupby('b'):
        tab = pd.crosstab(s.up_prev, s.up_now).reindex(index=[0, 1], columns=[0, 1]).fillna(0).values
        n = tab.sum()
        if n < 100 or tab.sum(axis=0).min() == 0 or tab.sum(axis=1).min() == 0:
            continue
        num += tab[1, 1] - tab[1].sum() * tab[:, 1].sum() / n
        den += (tab[1].sum() * tab[0].sum() * tab[:, 1].sum() * tab[:, 0].sum()) / (n ** 2 * (n - 1))
    chi2 = num ** 2 / den
    print(f'  CMH chi2(1) = {chi2:.2f}   p = {stats.chi2.sf(chi2, 1):.3f}')
    print('  H0: given today\'s price, yesterday\'s direction is uninformative.')


def _lr_order2(df, binner, label):
    """Anderson-Goodman LR test, 1st- vs 2nd-order, unsmoothed, df from non-empty cells."""
    a, b, c = binner(df.x2.values), binner(df.x.values), binner(df.y.values)
    K = max(a.max(), b.max(), c.max()) + 1
    n_abc = np.zeros((K, K, K))
    np.add.at(n_abc, (a, b, c), 1)
    n_ab, n_bc = n_abc.sum(2), n_abc.sum(0)
    n_b = n_bc.sum(1)
    with np.errstate(divide='ignore', invalid='ignore'):
        p2 = np.where(n_ab[:, :, None] > 0, n_abc / n_ab[:, :, None], 0)
        p1 = np.where(n_b[:, None] > 0, n_bc / n_b[:, None], 0)
        lr = 2 * np.where((n_abc > 0) & (p1[None] > 0), n_abc * np.log(p2 / p1[None]), 0).sum()
    dof = sum(max((n_ab[:, s] > 0).sum() - 1, 0) * max((n_bc[s] > 0).sum() - 1, 0) for s in range(K))
    print(f'  {label:<30s} LR = {lr:8.1f}  df = {dof:5d}  LR/df = {lr/dof:6.2f}  '
          f'p = {stats.chi2.sf(lr, dof):.4f}')


def test_3_order(df):
    print('\n' + '=' * 78)
    print('TEST 3  1st-order vs 2nd-order chain')
    print('=' * 78)
    _lr_order2(df, coarse_bin, '8 coarse price states')
    _lr_order2(df, price_bin, '34 fine price states')
    print('\n  Control: the same test on data that is Markov BY CONSTRUCTION (successors')
    print('  reshuffled within each exact price, which destroys any dependence on history):')
    for seed in range(3):
        rg = np.random.default_rng(seed)
        sh = df.copy()
        sh['y'] = sh.groupby('x')['y'].transform(lambda s: s.values[rg.permutation(len(s))])
        _lr_order2(sh, coarse_bin, f'  shuffled replicate {seed+1}')
    print('\n  The coarse test rejects just as hard on data with no memory at all: lumping')
    print('  distinct prices into one state manufactures the dependence. Only the fine')
    print('  resolution -- the actual state of the process -- gives a valid test.')

    # out-of-sample, which no amount of binning can fake
    K = price_bin(df.y.max()) + 1
    d = df.copy()
    d['b2'], d['by'] = price_bin(d.x2.values), price_bin(d.y.values)
    cut = d.date.quantile(0.7)
    tr, te = d[d.date <= cut], d[d.date > cut]
    a = 0.5
    c1 = np.full((K, K), a)
    np.add.at(c1, (tr.b.values, tr.by.values), 1)
    P1 = c1 / c1.sum(1, keepdims=True)
    c2 = np.full((K, K, K), a)
    np.add.at(c2, (tr.b2.values, tr.b.values, tr.by.values), 1)
    P2 = c2 / c2.sum(2, keepdims=True)
    ll1 = np.log(P1[te.b.values, te.by.values]).mean()
    ll2 = np.log(P2[te.b2.values, te.b.values, te.by.values]).mean()
    print(f'\n  Held-out log-likelihood (train <= {pd.Timestamp(cut).date()}, test after; n={len(te):,}):')
    print(f'    1st-order {ll1:+.4f} nats/obs      2nd-order {ll2:+.4f} nats/obs'
          f'      gain from extra memory {ll2-ll1:+.4f}')


def test_4_r2(df):
    print('\n' + '=' * 78)
    print("TEST 4  Incremental R^2 of history, on top of today's price")
    print('=' * 78)
    y = df.r.values
    base = pd.get_dummies(df.b, prefix='b', dtype=float).values

    def r2(X):
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        e = y - X @ beta
        return 1 - e @ e / ((y - y.mean()) @ (y - y.mean()))

    b0 = r2(base)
    print(f'  price-level fixed effects alone       R^2 = {b0:.5f}')
    for name, extra in [('+ yesterday\'s return', df[['rprev']].values),
                        ('+ two days of returns', df[['rprev', 'rprev2']].values),
                        ('+ 3-day price change', np.c_[df.rprev, df.rprev2, (df.x - df.x3) / df.x3])]:
        print(f'  {name:<37s} R^2 = {r2(np.c_[base, extra]):.5f}')


def test_5_runs():
    print('\n' + '=' * 78)
    print('TEST 5  Duration dependence: does a run of up-days change the next day?')
    print('=' * 78)
    V = np_data.panel().values
    up = np.diff(V, axis=0) > 0
    valid = ~np.isnan(V[1:]) & ~np.isnan(V[:-1])
    run = np.zeros_like(up, dtype=int)
    for i in range(1, len(up)):
        run[i] = np.where(valid[i] & valid[i - 1] & up[i - 1], run[i - 1] + 1, 0) * up[i - 1]
    price, nxt_up, ok, rl = V[1:-1], up[1:], valid[1:] & valid[:-1], run[1:]
    rows = []
    for k in range(6):
        sel = ok & (rl == k) & (price >= 10) & (price <= 20)
        if sel.sum() >= 100:
            rows.append({'up_run_length': k, 'n': int(sel.sum()), 'P(up next)': nxt_up[sel].mean()})
    print('  (restricted to prices 10-20 so the price level is roughly held fixed)')
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:8.4f}'))


def test_6_tickers(df):
    print('\n' + '=' * 78)
    print('TEST 6  Do the 43 tickers share one transition law?')
    print('=' * 78)
    a, c = coarse_bin(df.x.values), coarse_bin(df.y.values)
    K = max(a.max(), c.max()) + 1
    tick = pd.factorize(df.ticker)[0]
    n = np.zeros((tick.max() + 1, K, K))
    np.add.at(n, (tick, a, c), 1)
    rows = []
    tot_chi = tot_df = 0
    for s in range(K):
        tab = n[:, s, :]
        tab = tab[tab.sum(axis=1) >= 50]
        tab = tab[:, tab.sum(axis=0) > 0]
        if min(tab.shape) < 2:
            continue
        chi2, p, dof, _ = stats.chi2_contingency(tab)
        rows.append({'origin_state': s, 'n_tickers': tab.shape[0], 'n': int(tab.sum()),
                     'chi2/df': chi2 / dof, 'p': p})
        tot_chi, tot_df = tot_chi + chi2, tot_df + dof
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:10.4f}'))
    print(f'  total chi2/df = {tot_chi/tot_df:.3f}')
    print('  States 0-5 (prices 6-34) are flat at ~1: ticker identity adds nothing. The top')
    print('  two states span 35-69 and 70-1505, so tickers sitting at different prices INSIDE')
    print('  one bin look heterogeneous. Re-testing on relative moves removes that:')

    hi = df[(df.x >= 41) & (df.x <= 80)].copy()
    hi['ybin'] = np.clip(((hi.y / hi.x) * 10).astype(int), 4, 15)
    tab = pd.crosstab(hi.ticker, hi.ybin)
    tab = tab[tab.sum(axis=1) >= 60]
    chi2, p, dof, _ = stats.chi2_contingency(tab.values)
    print(f'    moves at prices 41-80, {tab.shape[0]} tickers: chi2/df = {chi2/dof:.3f}  p = {p:.3f}')

    lo = df[(df.x >= 10) & (df.x <= 20)]
    g = lo.groupby('ticker').apply(lambda z: pd.Series(
        {'n': len(z), 'mean_d': z.d.mean(), 'se': z.d.std() / np.sqrt(len(z)),
         'P_up': (z.d > 0).mean()}), include_groups=False)
    print(f'    mean daily move at 10-20: spread across tickers sd={g.mean_d.std():.3f}'
          f' vs typical sampling SE={g.se.mean():.3f}')
    print(f'    P(up) at 10-20:           spread sd={g.P_up.std():.4f}'
          f' vs binomial SE={np.sqrt(0.38*0.62/g.n.mean()):.4f}')


def test_7_eras(df):
    print('\n' + '=' * 78)
    print('TEST 7  Is the law stable across 2006-2018?')
    print('=' * 78)
    d = df.copy()
    d['era'] = pd.cut(pd.DatetimeIndex(d.date).year, [2005, 2009, 2013, 2019],
                      labels=['2006-09', '2010-13', '2014-18'])
    a, c = coarse_bin(d.x.values), coarse_bin(d.y.values)
    K = max(a.max(), c.max()) + 1
    era = pd.factorize(d.era, sort=True)[0]
    n = np.zeros((era.max() + 1, K, K))
    np.add.at(n, (era, a, c), 1)
    tot_chi = tot_df = 0
    for s in range(K):
        tab = n[:, s, :]
        tab = tab[tab.sum(axis=1) >= 50]
        tab = tab[:, tab.sum(axis=0) > 0]
        if min(tab.shape) < 2:
            continue
        chi2, _, dof, _ = stats.chi2_contingency(tab)
        tot_chi, tot_df = tot_chi + chi2, tot_df + dof
    print(f'  pooled chi2 = {tot_chi:.1f} on {tot_df} df -> chi2/df = {tot_chi/tot_df:.2f}'
          f'  p = {stats.chi2.sf(tot_chi, tot_df):.2g}')
    lo = d[(d.x >= 10) & (d.x <= 20)]
    print(lo.groupby('era', observed=True).apply(lambda z: pd.Series(
        {'n': len(z), 'mean_d': z.d.mean(), 'se': z.d.std() / np.sqrt(len(z)),
         'P_up': (z.d > 0).mean()}), include_groups=False).round(4).to_string())
    print('  Mildly non-stationary: the drift at low prices drifts down over the archive.')
    print('  Small next to the effects the strategy trades on -- see strategy.py era split.')


if __name__ == '__main__':
    df = np_data.windows(lags=3)
    df['b'] = price_bin(df.x.values)
    print(f'{len(df):,} four-day windows from {df.ticker.nunique()} tickers\n')
    test_1_momentum(df)
    test_2_sign(df)
    test_3_order(df)
    test_4_r2(df)
    test_5_runs()
    test_6_tickers(df)
    test_7_eras(df)
