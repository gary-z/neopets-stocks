"""What the 1000-shares-per-day purchase cap does to the strategy.

The cap is on shares, not neopoints, and selling is unrestricted. Two consequences:

  * It does not change WHAT to buy. Your daily budget is denominated in shares, and a
    share is worth about the same however much you paid, so pay as little as possible.
  * It changes how long you can afford to WAIT, but only through your bankroll. Running
    the quota at 1000 shares/day means carrying an inventory of 1000 x E[days held]
    shares. Below that much capital the exit has to come sooner.

    python analysis/capacity.py
"""
import numpy as np
import pandas as pd

import np_data
import strategy as S

BUY = 15
SHARES_PER_DAY = 1000


def table(P, buy=BUY):
    rows = []
    for s in range(buy + 1, 101):
        e = S.evaluate(P, s)
        i = buy - S.PMIN
        rows.append({'sell_at': s, 'PV_per_share': e['V'][i] - buy,
                     'profit_per_share': e['EP'][i] - buy, 'E_days': e['tau'][i]})
    d = pd.DataFrame(rows)
    d['working_capital'] = buy * SHARES_PER_DAY * d.E_days
    d['PV_per_day'] = SHARES_PER_DAY * d.PV_per_share
    return d


def main():
    t = np_data.full_pairs()
    P, _ = S.build_kernel(t)
    d = table(P)

    print('=' * 92)
    print('DOES THE CAP CHANGE THE ENTRY PRICE?  No -- both objectives still fall with price.')
    print('=' * 92)
    V, _ = S.solve_stopping(P)
    rows = [{'buy_at': b, 'V(p)': V[b - S.PMIN], 'profit per SHARE (cap binds)': V[b - S.PMIN] - b,
             'profit per NP (capital binds)': V[b - S.PMIN] / b} for b in [6, 10, 15, 20, 30, 45, 60]]
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f'{v:29.3f}'))

    print('\n' + '=' * 92)
    print('CAPACITY OF THE STRATEGY AT 1000 SHARES/DAY, BUYING AT 15')
    print('=' * 92)
    show = d[d.sell_at.isin([20, 25, 30, 40, 50, 55, 60, 65, 70, 80, 100])].copy()
    show['working_capital_M'] = show.working_capital / 1e6
    show['PV_k_per_day'] = show.PV_per_day / 1e3
    print(show[['sell_at', 'PV_per_share', 'E_days', 'working_capital_M', 'PV_k_per_day']]
          .to_string(index=False, float_format=lambda v: f'{v:18.2f}'))
    top = d.loc[d.PV_per_share.idxmax()]
    print(f'\n  Unconstrained optimum is still sell at {top.sell_at:.0f}, but sustaining the full'
          f' quota there\n  ties up {top.working_capital/1e6:.1f}M NP of inventory.')

    print('\n' + '=' * 92)
    print('BEST EXIT AS A FUNCTION OF BANKROLL')
    print('=' * 92)
    print('  (objective: shares bought per day x present value per share, both at 12.5%)')
    for B in [1e5, 2.5e5, 5e5, 1e6, 2e6, 3e6, 5e6, 7e6, 1e7, 2e7, 5e7]:
        rate = np.minimum(SHARES_PER_DAY, B / (BUY * d.E_days))
        daily = rate * d.PV_per_share
        best = d.loc[daily.idxmax()]
        r = min(SHARES_PER_DAY, B / (BUY * best.E_days))
        print(f'  bankroll {B:12,.0f} NP -> sell at {best.sell_at:3.0f}  '
              f'({r:6.0f} shares/day, {daily.max()/1e3:5.1f}k NP/day PV, '
              f'quota {"full" if r >= 999 else "not full"})')
    print('\n  Below roughly 10M NP the binding constraint is capital, so take the quicker exit.')
    print('  Above it the spare NP just sits in the bank at 12.5%, which is exactly the')
    print('  opportunity cost the 65 threshold was solved against -- so 65 stops moving.')

    print('\n' + '=' * 92)
    print('DIVERSIFICATION: are the 43 tickers independent?')
    print('=' * 92)
    lr = np.log(np_data.panel()).diff()
    C = lr.corr(min_periods=500).values
    off = C[~np.eye(len(C), dtype=bool)]
    print(f'  mean pairwise correlation of daily log-moves = {np.nanmean(off):+.4f}'
          f'  (median {np.nanmedian(off):+.4f})')
    print('  Effectively zero. Spreading the daily 1000 shares over whatever is cheapest, day')
    print('  after day, builds a genuinely diversified book, so the averages above are what a')
    print('  player actually experiences rather than a lottery.')


if __name__ == '__main__':
    main()
