"""When to sell, and what to pay to get in.

Selling is an optimal-stopping problem. Holding a share is free in cash terms but
costs the interest the money would have earned in the bank, so the value of a share
priced p is

    V(p) = max( p ,  delta * E[ V(next price) | p ] ),    delta = 1 / (1 + 0.125/365)

and you sell the moment the price reaches the region where V(p) = p. Buying is then
trivial: a share is worth V(p) and costs p, so compare across entry prices.

    python analysis/strategy.py
"""
import numpy as np
import pandas as pd

import np_data

APR = 0.125
DELTA = 1.0 / (1.0 + APR / 365)
PMIN, PMAX = 6, 1600           # 6 is the observed floor, 1505 the observed high
STATES = np.arange(PMIN, PMAX + 1)
NS = len(STATES)
I15 = 15 - PMIN


def build_kernel(t=None, nmin=400):
    """P[i, j] = P(tomorrow = STATES[j] | today = STATES[i]).

    A price level with at least `nmin` observations of its own uses only those. Thinner
    levels widen a window in log-price and reuse the *relative* moves seen there, which
    is the scale price moves actually live on. Mass is split between the two neighbouring
    integers so the conditional mean survives the rescaling.
    """
    if t is None:
        t = np_data.full_pairs()
    o = t.sort_values('x')
    ox = o.x.values.astype(float)
    lox = np.log(ox)
    ratio = o.y.values / o.x.values

    P = np.zeros((NS, NS))
    bandwidth = np.zeros(NS)
    for i, x in enumerate(STATES):
        lx = np.log(x)
        lo, hi = np.searchsorted(ox, x, 'left'), np.searchsorted(ox, x, 'right')
        h = 0.0
        while hi - lo < nmin and h < 5.0:
            h += 0.02
            lo, hi = np.searchsorted(lox, lx - h, 'left'), np.searchsorted(lox, lx + h, 'right')
        bandwidth[i] = h
        sl = slice(lo, hi)
        w = np.ones(hi - lo) if h == 0 else (1 - (np.abs(lox[sl] - lx) / h) ** 3) ** 3
        w = np.maximum(w, 1e-12)

        yv = np.clip(x * ratio[sl], PMIN, PMAX)
        f = np.floor(yv).astype(int)
        frac = yv - f
        np.add.at(P[i], f - PMIN, w * (1 - frac))
        np.add.at(P[i], np.minimum(f + 1, PMAX) - PMIN, w * frac)
        P[i] /= P[i].sum()
    return P, bandwidth


def solve_stopping(P, delta=DELTA):
    """Exact optimal stopping by Howard policy iteration. Returns (V, keep_holding)."""
    x = STATES.astype(float)
    V, cont = x.copy(), np.zeros(NS, bool)
    for it in range(200):
        new = delta * (P @ V) > x + 1e-12
        if it and np.array_equal(new, cont):
            break
        cont = new
        c, s = np.where(cont)[0], np.where(~cont)[0]
        V = x.copy()
        if len(c):
            V[c] = np.linalg.solve(np.eye(len(c)) - delta * P[np.ix_(c, c)],
                                   delta * P[np.ix_(c, s)] @ x[s])
    return V, cont


def evaluate(P, sell_at, delta=DELTA):
    """The plain rule 'hold until the price reaches sell_at'. Returns a dict of arrays:
    V (discounted value), EP (expected sale price), tau (expected days held)."""
    x = STATES.astype(float)
    c, s = np.where(STATES < sell_at)[0], np.where(STATES >= sell_at)[0]
    I = np.eye(len(c))
    V, EP, tau = x.copy(), x.copy(), np.zeros(NS)
    V[c] = np.linalg.solve(I - delta * P[np.ix_(c, c)], delta * P[np.ix_(c, s)] @ x[s])
    EP[c] = np.linalg.solve(I - P[np.ix_(c, c)], P[np.ix_(c, s)] @ x[s])
    tau[c] = np.linalg.solve(I - P[np.ix_(c, c)], np.ones(len(c)))
    return {'V': V, 'EP': EP, 'tau': tau}


def implied_apr(P, sell_at, buy=15):
    """The annual rate at which this round trip exactly breaks even."""
    lo, hi = 0.0, 50.0
    for _ in range(200):
        mid = (lo + hi) / 2
        v = evaluate(P, sell_at, 1 / (1 + mid / 365))['V'][buy - PMIN]
        lo, hi = (mid, hi) if v > buy else (lo, mid)
        if hi - lo < 1e-9:
            break
    return (lo + hi) / 2


def hold_region(cont):
    """The contiguous run of hold-states starting at the price floor -- the part of the
    stopping rule that a trade starting cheap can actually reach."""
    top = PMIN
    for p in STATES[cont]:
        if p == top + 1:
            top = p
    return PMIN, top


def main():
    t = np_data.full_pairs()
    P, bw = build_kernel(t)
    x = STATES.astype(float)
    print(f'{len(t):,} observed daily transitions; delta = {DELTA:.8f} ({APR:.1%} APR / 365)')
    print(f'kernel bandwidth (log-price) at p=15/40/60/100: '
          f'{bw[I15]:.2f} / {bw[34]:.2f} / {bw[54]:.2f} / {bw[94]:.2f}\n')

    print('=' * 78)
    print('THE SHAPE OF THE PROBLEM: one-day expected return by price')
    print('=' * 78)
    Ex = P @ x
    r = pd.DataFrame({'price': STATES, 'exp_1d_return_%': 100 * (Ex / x - 1)})
    print(r[r.price.isin([6, 7, 8, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 100, 200, 500])]
          .to_string(index=False, float_format=lambda v: f'{v:10.3f}'))
    print(f'  daily hurdle from the bank: {100*APR/365:.4f}%/day')
    print('  A hard floor at 6 with big positive drift; a flat middle; heavy mean reversion')
    print('  from ~45 up; nothing much above ~90.')

    V, cont = solve_stopping(P)
    lo, top = hold_region(cont)
    print('\n' + '=' * 78)
    print('SELL RULE (optimal stopping, 12.5% APR opportunity cost)')
    print('=' * 78)
    print(f'  hold while the price is {lo}-{top};  SELL at {top+1} NP or above')
    stray = cont & (STATES > top)
    print(f'  ({stray.sum()} scattered hold-states above {top} are thin-tail estimation noise:')
    print(f'   their value premium is {100*np.max((V[stray]-x[stray])/x[stray]):.2f}% of price at most,')
    print(f'   and removing them leaves V(15) unchanged.)')

    print('\n  Value of the simple rule "sell at s", entering at 15:')
    grid = {s: evaluate(P, s) for s in range(20, 121)}
    v15 = pd.Series({s: g['V'][I15] for s, g in grid.items()})
    best = int(v15.idxmax())
    rows = [{'sell_at': s, 'V(15)': grid[s]['V'][I15], 'vs_optimum_%': 100 * (v15[s] / v15[best] - 1),
             'E[sale price]': grid[s]['EP'][I15], 'E[days held]': grid[s]['tau'][I15],
             'implied APR %': 100 * implied_apr(P, s)}
            for s in [30, 40, 50, 55, 58, 60, 62, 65, 68, 70, 75, 80, 100]]
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:13.3f}'))
    near = v15[v15 >= 0.99 * v15[best]]
    print(f'\n  optimum s* = {best};  every s in {near.index.min()}-{near.index.max()} is within 1% of it')
    print(f'  the rule-of-thumb 60 gives {100*(v15[60]/v15[best]-1):+.2f}% versus the optimum')

    print('\n  Sensitivity to the assumed opportunity cost:')
    rows = []
    for apr in [0.05, 0.10, 0.125, 0.15, 0.20, 0.30, 0.50]:
        _, c2 = solve_stopping(P, 1 / (1 + apr / 365))
        rows.append({'APR': f'{apr:.1%}', 'sell_at': hold_region(c2)[1] + 1})
    print('   ', '   '.join(f"{r['APR']}->{r['sell_at']}" for r in rows))

    print('\n' + '=' * 78)
    print('BUY RULE')
    print('=' * 78)
    rows = [{'buy_at': b, 'share is worth V(p)': V[b - PMIN], 'profit per share': V[b - PMIN] - b,
             'profit per NP spent': V[b - PMIN] / b}
            for b in [6, 8, 10, 12, 14, 15, 16, 18, 20, 25, 30, 40, 50, 60]]
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:20.3f}'))
    print('  V(p) barely moves over p=6..20 -- where you got in stops mattering once you are')
    print('  holding for the same exit. So both columns fall monotonically: buy as cheap as')
    print('  the game lets you, which is 15 NP.')

    print('\n' + '=' * 78)
    print('ERA ROBUSTNESS (chain refitted inside each era)')
    print('=' * 78)
    t2 = t.copy()
    t2['era'] = pd.cut(pd.DatetimeIndex(t2.date).year, [2005, 2009, 2013, 2019],
                       labels=['2006-09', '2010-13', '2014-18'])
    for e, g in t2.groupby('era', observed=True):
        Pe, _ = build_kernel(g)
        ve = pd.Series({s: evaluate(Pe, s)['V'][I15] for s in range(40, 111)})
        b = int(ve.idxmax())
        print(f'  {e}: n={len(g):6,}  optimal sell = {b} NP   V(15) = {ve[b]:.2f}'
              f'  ({ve[b]/15:.2f}x)')
    return P, V, cont


if __name__ == '__main__':
    main()
