"""Should you hold past 65, given that every price is reached eventually?

The premise is true: Neopets tickers never delist, the chain is recurrent, and
P(ever reach L) = 1 for every L. So a share bought at 65 will, with certainty,
someday be worth 130, or 1000. The question is whether it happens fast enough to
beat leaving the money in the bank at 12.5% APR.

This computes the effective APY of "hold from 65, sell at THRESHOLD, or liquidate
at day X" over the whole grid, rather than appealing to the stopping solution.

    python analysis/hold_longer.py
"""
import numpy as np
import pandas as pd

import np_data
import strategy as S

X = S.STATES.astype(float)
DOUBLING = np.log(2) / np.log(1 + S.APR / 365)   # days for the bank to double your money

# The forward passes below run tens of thousands of days, so they use a kernel truncated
# at 600 NP with the (negligible) mass above folded into the top state. Starting at 65
# with exits at or below 200 that is far outside anything the walk reaches.
TRUNC = 600
NT = TRUNC - S.PMIN + 1
XT = X[:NT]


def truncate(P):
    Q = P[:NT, :NT].copy()
    Q[:, -1] += P[:NT, NT:].sum(1)
    return Q / Q.sum(1, keepdims=True)


def hitting(P, start, level):
    """(P(ever reach `level`), E[days to reach it]) from `start`."""
    c = np.where(S.STATES < level)[0]
    s = np.where(S.STATES >= level)[0]
    A = np.eye(len(c)) - P[np.ix_(c, c)]
    i = start - S.PMIN
    return np.linalg.solve(A, P[np.ix_(c, s)].sum(1))[i], np.linalg.solve(A, np.ones(len(c)))[i]


def cashflows(Q, start, thresh, horizon):
    """f[j] = E[sale proceeds on day j]; alive[j] = value of the still-held book at day j.

    Takes a TRUNCATED kernel (see truncate). One pass gives every horizon at once.
    """
    cont = XT < thresh
    mu = np.zeros(NT)
    mu[start - S.PMIN] = 1.0
    f, alive = np.zeros(horizon + 1), np.zeros(horizon + 1)
    alive[0] = mu @ XT
    for j in range(1, horizon + 1):
        mu = (mu * cont) @ Q
        f[j] = (mu * ~cont) @ XT
        alive[j] = (mu * cont) @ XT
    return f, alive


def apy(f, alive, horizon, cost):
    """Rate r solving  sum_j (1+r/365)^-j f_j  +  (1+r/365)^-X alive_X  =  cost."""
    lo, hi = -0.99, 20.0
    for _ in range(140):
        r = (lo + hi) / 2
        d = (1 + r / 365) ** -np.arange(horizon + 1)
        pv = (d * f[:horizon + 1]).sum() + d[horizon] * alive[horizon]
        lo, hi = (r, hi) if pv > cost else (lo, r)
    return 100 * (lo + hi) / 2


def tilt(P, lo, hi, theta):
    """Exponentially re-weight rows in [lo,hi] toward up-moves, to test robustness."""
    R = P.copy()
    for i, p in enumerate(S.STATES):
        if lo <= p <= hi:
            R[i] = R[i] * np.exp(theta * (S.STATES - p) / p)
            R[i] /= R[i].sum()
    return R


def main():
    t = np_data.full_pairs()
    P, _ = S.build_kernel(t)
    Q = truncate(P)
    print(f'12.5% APR doubles money in {DOUBLING:,.0f} days ({DOUBLING/365:.2f} years)\n')

    print('=' * 86)
    print('THE PREMISE IS CORRECT -- but look at how long "eventually" is')
    print('=' * 86)
    rows = []
    for L in [70, 80, 100, 130, 200, 300, 1000]:
        pr, days = hitting(P, 65, L)
        rows.append({'reach': L, 'multiple': L / 65, 'P(ever)': pr, 'E[years]': days / 365,
                     'years the bank needs': np.log2(L / 65) * DOUBLING / 365})
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:20.2f}'))
    print('  Every level is reached with probability 1. Doubling 65 -> 130 takes 22 years,')
    print('  against the 5.5 the bank needs. Recurrence is real and far too slow to matter.')

    print('\n' + '=' * 86)
    print('EFFECTIVE APY: hold from 65, sell at THRESHOLD, liquidate at day X if unsold')
    print('=' * 86)
    H = 18250
    horizons = [1825, 3650, 7300, 18250]
    grid = {}
    for s in [70, 80, 100, 150]:
        f, a = cashflows(Q, 65, s, H)
        grid[s] = [apy(f, a, h, 65.0) for h in horizons]
    # Pure buy-and-hold has no stopping, so E[price at day h] is just a vector iteration --
    # and it is the one case that needs the untruncated tail, since nothing caps the walk.
    mu = np.zeros(len(P))
    mu[65 - S.PMIN] = 1.0
    ev = {}
    for h in range(1, max(horizons) + 1):
        mu = mu @ P
        if h in horizons:
            ev[h] = mu @ X
    grid['no exit'] = [365 * ((ev[h] / 65) ** (1 / h) - 1) * 100 for h in horizons]
    out = pd.DataFrame(grid, index=['5y', '10y', '20y', '50y']).T
    out.index.name = 'exit at'
    print(out.to_string(float_format=lambda v: f'{v:10.2f}'))
    print('  Nothing on this grid reaches 12.5%. Short horizons are badly negative because a')
    print('  forced sale lands in the mean-reverted 15-20 range; long horizons creep up to')
    print('  the ceiling below.')

    best = max((apy(*cashflows(Q, 65, s, H), H, 65.0), s)
               for s in [66, 67, 68, 70, 72, 75, 80, 90, 110, 140])
    print(f'\n  Best of every threshold at an unbounded horizon: {best[0]:.2f}% APY '
          f'(exit {best[1]}).')
    print('  That ceiling is not a coincidence -- "sell at 65" is precisely the statement')
    print('  that no way of continuing from 65 clears 12.5%.')

    print('\n' + '=' * 86)
    print('MARGINAL APY OF HOLDING ONE MORE DAY, by price')
    print('=' * 86)
    rows = [{'price': p, 'marginal APY %': apy(*cashflows(Q, p, p + 1, H), H, float(p))}
            for p in [20, 30, 40, 50, 55, 60, 62, 64, 65, 66, 70, 80, 100]]
    d = pd.DataFrame(rows)
    print(d.to_string(index=False, float_format=lambda v: f'{v:14.2f}'))
    print(f'  Crosses 12.5% at {int(d[d["marginal APY %"] < 12.5].price.min())} NP.')

    print('\n' + '=' * 86)
    print('HOW WRONG WOULD THE ARCHIVE HAVE TO BE?')
    print('=' * 86)
    lo, hi = 0.0, 4.0
    for _ in range(45):
        mid = (lo + hi) / 2
        top = S.hold_region(S.solve_stopping(tilt(P, 65, 150, mid))[1])[1] + 1
        lo, hi = (lo, mid) if top > 72 else (mid, hi)
    Pt = tilt(P, 65, 150, hi)
    Qt = truncate(Pt)
    shift = np.mean([100 * ((Pt[p - S.PMIN] @ X) / p - 1) - 100 * ((P[p - S.PMIN] @ X) / p - 1)
                     for p in (70, 80, 100, 130)])
    s = t[(t.x >= 65) & (t.x <= 150)].copy()
    s['r'] = s.y / s.x - 1
    m = s.r.mean()
    se = np.sqrt(s.groupby('ticker').r.apply(lambda z: (z - m).sum() ** 2).sum()) / len(s)
    print(f'  65-150 is the stretch a hold-past-65 trade has to cross.')
    print(f'  measured drift there: {100*m:+.2f} %/day, clustered SE {100*se:.2f} (n={len(s)}, '
          f'{s.ticker.nunique()} tickers)')
    print(f'  pushing the exit past 72 needs about {shift:+.2f} %/day more drift'
          f'  -- {shift/(100*se):.1f} standard errors.')
    print('  That is real but not remote: roughly a 1-in-30 shot on a normal approximation.')
    print('  So the honest reading is that the exit sits somewhere in 62-73, not that it is')
    print('  pinned at exactly 65. What that scenario does NOT support is holding forever:')
    exits = [67, 70, 80, 100, 150, 10 ** 9]
    cf_base = {s_: cashflows(Q, 65, s_, H) for s_ in exits}
    cf_adv = {s_: cashflows(Qt, 65, s_, H) for s_ in exits}
    rows = []
    for h, lab in [(1825, '5y'), (3650, '10y'), (7300, '20y'), (18250, '50y')]:
        rows.append({'horizon': lab,
                     'base APY %': max(apy(*cf_base[s_], h, 65.0) for s_ in exits),
                     'adverse-case APY %': max(apy(*cf_adv[s_], h, 65.0) for s_ in exits)})
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:16.2f}'))
    print(f'  Even there the solver only moves the exit to '
          f'{S.hold_region(S.solve_stopping(Pt)[1])[1]+1} NP, and the gain over the bank is'
          ' about a point.')

    print('\n' + '=' * 86)
    print('WHY THE THIN HIGH-PRICE ROWS DO NOT CONTAMINATE THE ENTRY DECISION')
    print('=' * 86)
    c = np.where(S.STATES < 65)[0]
    A = np.eye(len(c)) - P[np.ix_(c, c)]
    for L in [100, 150, 200]:
        h = np.linalg.solve(A, P[np.ix_(c, np.where(S.STATES >= L)[0])].sum(1))
        print(f'  P(price reaches {L} before it reaches 65 | bought at 15) = {h[15-S.PMIN]:.1e}')
    print('  A trade that exits in the 60s never visits the rows the archive measures worst,')
    print('  so the 15-buy / 65-sell pair rests only on well-sampled prices.')


if __name__ == '__main__':
    main()
