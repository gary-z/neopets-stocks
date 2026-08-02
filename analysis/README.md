# What the archive says about buying and selling

Analysis of `data/archived_prices.csv` — 43 tickers, 4,451 consecutive days
(2006-04-24 to 2018-06-30), 145,379 observed prices, 144,774 one-day transitions.
1,069–1,073 days are missing for *every* ticker at once, so whole days are absent
from the archive rather than individual listings; those are dropped, never interpolated.

```
python analysis/markov_tests.py    # is tomorrow a function of today alone?
python analysis/strategy.py        # optimal stopping -> when to sell, what to pay
python analysis/backtest.py        # the same rules replayed on real paths, no model
python analysis/capacity.py        # what the 1000-shares/day cap changes
```

## Answers

| Question | Answer |
| --- | --- |
| Are price moves Markov? | Yes. Nothing in the history predicts tomorrow once today's price is known. |
| Do tickers move alike? | Yes. One transition law fits all 43. |
| When to sell at 12.5% APR? | **65 NP.** Anything in 62–72 is within 1% of optimal. |
| Best entry price? | **As cheap as the game allows — 15 NP.** |
| Do 15 / 60 hold up? | Both are right. 60 leaves 2.2% on the table versus 65. |

---

## 1. The moves are Markov

Six tests, each conditioning on today's price and then asking whether some piece of
history still carries information.

| Test | Result |
| --- | --- |
| Correlation of today's move with yesterday's, within price level | r = +0.0022, p = 0.41 |
| …with the move two days back | r = −0.0017, p = 0.51 |
| CMH test on the *sign* of yesterday's move, stratified by price | χ²(1) = 0.23, p = 0.63 |
| LR test, 1st- vs 2nd-order chain (34 price states) | LR = 3519 on 3622 df, p = 0.89 |
| Held-out log-likelihood, 2nd-order minus 1st-order | **−0.033 nats/obs** (memory *hurts*) |
| Extra R² from three days of history, over price fixed effects | +0.00002 |
| P(up tomorrow) after an up-run of 0,1,2,3,4,5 days | 0.380, 0.373, 0.368, 0.377, 0.359, 0.364 |

**One trap worth flagging.** Run the same 1st- vs 2nd-order test on 8 lumped price
states and it rejects overwhelmingly, LR/df = 26. That is an artifact, not memory. A
coarse-grained function of a Markov chain is generally not itself Markov: if "35–69" is
one state, yesterday's state tells you *where inside the bin* you are today. Reshuffling
successors within each exact price — which makes the data first-order Markov by
construction — reproduces LR/df = 26.3, 26.7, 28.9. `markov_tests.py` runs those shuffled
controls alongside the real test. At the true state resolution, integer price, LR/df = 0.97.

## 2. Tickers move alike

Homogeneity χ² across all 43 tickers, per origin price state, gives χ²/df of
1.00, 1.15, 1.02, 1.02, 0.87, 1.13 for prices 6–34 — indistinguishable from sampling
noise. Ticker-level means agree too: at prices 10–20 the spread of mean daily move
across tickers is sd 0.054 against a typical sampling SE of 0.057, and the spread of
P(up) is sd 0.0110 against a binomial SE of 0.0116.

The two top bins do reject, but they span 35–69 and 70–1505 — the same lumping problem.
Testing *relative* moves inside 41–80 instead: χ²/df = 1.005, p = 0.46 across 40 tickers.

Pairwise correlation of daily log-moves across tickers averages −0.0001. The tickers
share one law and are independent draws from it.

**Caveat.** The chain is mildly non-stationary. Pooled across eras, χ²/df = 2.06
(p = 2×10⁻⁶); mean daily move at prices 10–20 drifts from +0.095 (2006–09) to +0.009
(2010–13) to −0.037 (2014–18). Refitting the whole model inside each era moves the
sell threshold only to 72 / 67 / 64, so it does not change any conclusion below.

## 3. The shape of the process

One-day expected return, by price:

| price | 6 | 8 | 10 | 15 | 20 | 30 | 40 | 50 | 55 | 60 | 70 | 100 | 200 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E[return] %/day | **+15.5** | +1.9 | −0.1 | +0.4 | −0.2 | +0.5 | +0.7 | −2.7 | −5.2 | −4.0 | −3.5 | −0.8 | −0.8 |

Three regimes:

- **A hard floor at 6.** No down-move from 6 was ever recorded in 10,512 chances. It is a
  reflecting barrier with a strong upward push (+15.5%/day at 6, +5.6% at 7, +1.9% at 8).
  There is no ruin in this market, which is why holding is nearly free.
- **A flat middle, 9–40.** Drift within ±0.5%/day. 76% of all ticker-days sit at 20 or below.
- **Heavy mean reversion above ~45.** −3.1%/day averaged over 41–80. This is the single
  most robust fact in the data: all 43 tickers are individually negative there, all three
  eras agree (−3.2%, −3.0%, −3.0%), and leave-one-ticker-out never moves it outside
  [−3.15%, −3.05%]. Above ~90 the drift dies back to roughly zero.

## 4. When to sell — 65 NP

Optimal stopping. Holding costs the 12.5% APR the money would earn in the bank, so
δ = 1/(1 + 0.125/365) per day and

V(p) = max( p, δ · E[V(next) | p] ).

Solved exactly by policy iteration over integer prices 6–1600: **hold while the price is
6–64, sell the moment it reaches 65.**

| sell at | 40 | 50 | 55 | 58 | **60** | 62 | **65** | 68 | 70 | 75 | 80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| value of a 15 NP share | 41.47 | 49.19 | 51.62 | 53.05 | **54.10** | 54.96 | **55.33** | 55.25 | 55.15 | 54.13 | 51.54 |
| vs. optimum | −25.1% | −11.1% | −6.7% | −4.1% | **−2.2%** | −0.7% | — | −0.1% | −0.3% | −2.2% | −6.9% |
| expected days held | 210 | 297 | 347 | 399 | 466 | 543 | 664 | 832 | 943 | 1326 | 1835 |

The peak is broad: 62–72 all land within 1% of optimal.

Note this is *not* the myopic rule. Expected drift turns negative at ~45, so a
"sell when it stops rising" reading of the data would exit around 40 and give up 25% of
the value. Holding is still right at 50 or 60 because the floor at 6 means a position
that falls back is never lost — you simply wait for the next run. What eventually
overwhelms that option value is the discount, not the drift.

**Robustness.** Bootstrapping the 43 tickers and refitting: median optimal threshold 65,
90% interval [65, 71]. Refitting by era: 72 / 67 / 64. Against the assumed opportunity
cost the threshold is stable — 5% APR → 79, 10% → 71, 12.5% → 65, 15% → 64, 20% → 62,
30% → 58.

**Model-free confirmation.** `backtest.py` ignores the chain entirely: buy on every one of
the 6,888 days a stock actually traded at 15, follow the real path, sell the first day it
reaches the target. Restricting to buys with 5+ years of archive left so that ~99% of
trades close:

| sell at | 50 | 55 | 60 | 65 | 70 | 75 | 80 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PV multiple | 3.30× | 3.46× | 3.57× | **3.72×** | 3.74× | 3.64× | 3.43× |
| % sold | 100 | 100 | 99.5 | 98.9 | 95.6 | 89.1 | 78.8 |

3.72× against the fitted chain's 3.69×. Bootstrapping tickers on the full sample, the
winning threshold is 65 in 49% of replicates and 60 in 34% — 60 and 65 are not
statistically separable, and the point estimate favours 65.

## 5. What to pay — 15 NP

| buy at | 6 | 10 | 15 | 20 | 30 | 40 | 60 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| the share is worth | 54.87 | 54.98 | 55.33 | 55.85 | 57.23 | 58.70 | 62.97 |
| profit per share | 48.87 | 44.98 | **40.33** | 35.85 | 27.23 | 18.70 | 2.97 |
| profit per NP spent | 9.14× | 5.50× | **3.69×** | 2.79× | 1.91× | 1.47× | 1.05× |

V(p) is almost flat from 6 to 20 — once you are holding for the same exit, where you got
in stops mattering, and a share is worth about 55 NP whatever you paid. So both columns
fall monotonically and the rule is simply *buy as cheap as the game allows*. Neopets
will not sell you a stock under 15 NP, which makes 15 the constrained optimum. The
backtest agrees, monotone from 7.80× at a (hypothetical) 6 NP entry down to 1.01× at 60.

Nothing about 15 is special in the data itself. It is the right answer because it is the
floor, not because the process does anything there.

In practice the entry is available: on the 3,382 archive days with any stock at 15+, the
cheapest such stock is exactly 15 on 87.8% of them and ≤ 17 on 99.8% — which is what
`index.html` already picks.

## 6. The 1000-shares-per-day cap

Purchases are capped at 1,000 shares/day regardless of price; selling is unrestricted.

**It does not change what to buy.** The cap is denominated in shares, so the relevant
figure is profit *per share* — and that falls with the entry price just as profit per NP
does (48.87 at 6, 40.33 at 15, 35.85 at 20). Both objectives point the same way. If
anything the cap sharpens the argument: your daily budget is 1,000 shares each worth
~55 NP, so paying more for one is pure loss.

**It does change how long you can afford to wait, through your bankroll.** Running the
quota at a 65 exit means carrying 1,000 × 664 days of inventory — about 10.0M NP at cost.

| sell at | 20 | 30 | 40 | 50 | 60 | 65 | 70 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| working capital for a full quota | 0.53M | 1.84M | 3.15M | 4.45M | 7.00M | 9.96M | 14.2M |
| PV earned per day at full quota | 5.9k | 16.7k | 26.5k | 34.2k | 39.1k | **40.3k** | 40.2k |

Below that, capital rather than the quota is binding and the exit should come sooner:

| bankroll | 0.5M | 1M | 2M | 3M | 5M | 7M | ≥10M |
| --- | --- | --- | --- | --- | --- | --- | --- |
| best exit | 20 | 23 | 32 | 40 | 54 | 60 | **65** |

Above ~10M NP the cap binds, spare NP genuinely does sit in the bank at 12.5%, and 65
stops moving. That is worth stating plainly, because it retires the one objection to
using 12.5% as the discount rate at all: the strategy's own internal return at a 65 exit
is ~181% APR, and if freed capital could be recycled into fresh 15 NP buys without limit
then *that*, not the bank rate, would be the opportunity cost and the right exit would be
far lower. The 1,000-share cap is what stops the recycling. For a player who can fill the
quota, 12.5% is the correct hurdle and 65 is the correct answer.

## 7. Verdict on the rules of thumb

**Enter at 15 — correct**, though not for the reason it is usually given. 15 is not a
level the market respects; it is the cheapest share Neopets will sell you, and the data
says buy the cheapest share you can.

**Exit at 60 — correct.** The optimum is 65 and 60 costs 2.2% of value, inside the noise
of what the archive can resolve (bootstrap: 65 wins 49% of the time, 60 wins 34%). The
reason it works is worth knowing though: not that 60 is a ceiling, but that mean
reversion above ~45 eventually outweighs the option value created by the floor at 6.
If you hold a smaller bankroll than ~7M NP, exit earlier than 60 — the capital
constraint, not the price process, is what should set your threshold.

## Caveats

- Modelling assumes you transact at the archived daily price with no fee or slippage.
- The archive ends in 2018; the era split shows the low-price drift trending downward
  across the sample, and the optimal threshold with it (72 → 67 → 64). If that trend
  continued past 2018, the current threshold is likelier below 65 than above it.
- Expected holding times are long (664 days to a 65 exit) and heavily right-skewed;
  the median is 600 days in the uncensored backtest. These are multi-year positions.
- Tail transition rows above ~100 NP rest on thin data dominated by two tickers
  (KSON, VPTS). The optimal policy sells long before there, and the scattered
  high-price hold-states the solver reports are noise — deleting them leaves V(15)
  unchanged to four decimals.
