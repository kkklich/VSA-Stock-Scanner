## The idea in plain language

Mark Minervini buys only stocks that are **already in a strong, established uptrend**. His *Trend Template* is a checklist that answers one question: is this stock in the healthy, rising phase of its life, or not? A stock that fails the checklist is not bought, however cheap it looks.

The template is a **filter, not an entry signal**. Minervini uses it to decide which stocks are worth watching, and then waits for a separate, precise entry point (for example a breakout from a tight base — see the Volume Breakout article). StockPilot implements the filter.

The method is **long-only** (it looks for rising prices) and **medium-term**: the trend it describes lasts weeks to months.

## Where it comes from

Mark Minervini, *Trade Like a Stock Market Wizard* (2013). Minervini is a two-time winner of the U.S. Investing Championship, a real-money trading competition — an independently verifiable track record, which is why this method was chosen for the app. His idea of a "Stage 2" uptrend comes from Stan Weinstein's stage analysis (see the Weinstein article).

## The eight rules StockPilot checks

A moving average (MA) is the average closing price over the last N sessions; a "200-day MA" is the average of the last 200 closes. The 52-week high and low are the highest high and lowest low of the last 252 sessions.

| # | Rule | How StockPilot measures it |
|---:|---|---|
| 1 | Price is above the 150-day and the 200-day MA | today's close above both averages |
| 2 | The 150-day MA is above the 200-day MA | compared today |
| 3 | The 200-day MA is rising | higher today than 20 sessions (about a month) ago |
| 4 | The 50-day MA is above the 150-day and the 200-day MA | compared today |
| 5 | Price is above the 50-day MA | today's close above it |
| 6 | Price is well off its 52-week low | at least 30% above the lowest low of 252 sessions |
| 7 | Price is near its 52-week high | no more than 25% below the highest high of 252 sessions |
| 8 | Relative strength is in the top 30% of the market | see below — only on ranking pages |

**Rule 8, relative strength.** Minervini wants a stock that is stronger than most others. StockPilot computes it the way Investor's Business Daily does: a weighted return — **40%** of the return over the last 3 months plus **20%** each of the returns over the last 6, 9 and 12 months — and then ranks every company **within the same market** from 0 (weakest) to 100 (strongest). Rule 8 passes at **70 or more**. Because it compares a stock with all the others, it exists only on the pages that rank the whole market (the Dashboard, Watchlist and Filters). The stock page, which looks at one company alone, uses rules 1–7.

A stock needs **at least 252 sessions** (about a year) of history. With less, the method says "not enough history" rather than guessing — otherwise a three-month high would pass for a 52-week high.

One simplification: Minervini asks for the 200-day MA to be rising for **at least a month, preferably four to five**. The app checks the one-month minimum.

## What you see in the app

- **Score (0–100):** the share of rules the stock meets. On the ranking pages it is out of 8 (the detail reads e.g. "7/8 rules"); on the stock page out of 7 ("6/7 structural"). 100 means every rule holds.
- **"Fired recently" chip:** the setup counts as having fired on a day when **all seven price rules** held. The chip shows how many days ago that last happened (looking back up to 90 sessions). Rule 8 does not affect the chip, only the score.
- **Chart markers:** an amber dot with a green "Trend Template" label on each day the full seven-rule template **switched on** (the day before it did not hold). While the template stays on, no further markers are drawn, so each marker is the start of a qualifying period.
- **Combined column and Analytics summary:** the score takes part in the combined cross-method score and in the stock page's summary.

## How well it has worked

- **The app's back-test gate** (GPW, 288 companies, measured 2026-09-23): after the template switched on, the stock beat its own typical move only **43.4%** of the time over 10 sessions and **41.4%** over 30, with a **negative** average edge (−0.38 and −0.57 percentage points). A randomly chosen day scores +0.59 and +1.20 in the same test. On the GPW this is the **weakest** method in the app.
- **The direction test** (2026-09-26, 1,010 companies on six markets, mostly 2025–2026): here Minervini did better than any VSA method — the stock beat the market **51.8%** of the time over 10 sessions and **54.1%** over 30 (a random pick: about 49.5%). Only the 30-session result is statistically meaningful, and nearly all of that data comes from a single period (2025–2026).
- **Why the GPW result is poor:** the template fires while a stock is **already deep in its uptrend**. Measured on the same data, Weinstein's method — which buys the moment the uptrend *begins* — turned the same idea from a negative edge into a positive one. See the Weinstein article.

**In short:** on the Warsaw exchange, "already in a strong uptrend" has not been a good reason to buy on its own. Treat a high score as "this stock is trending well", not as "buy now".

## What the app does not do

- It does not look for Minervini's entry points (the *Volatility Contraction Pattern*, a tightening base). The closest thing in the app is the Volume Breakout method.
- It does not manage the trade. Minervini keeps losses small with a stop set before buying; the app gives no stop, target or exit signal.
- It does not check earnings or fundamentals, which Minervini also uses.

## Sources

- Mark Minervini, *Trade Like a Stock Market Wizard* (McGraw-Hill, 2013) — the Trend Template.
- Mark Minervini, [minervini.com](https://www.minervini.com/).
- Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (1988) — the stage model the template assumes.
