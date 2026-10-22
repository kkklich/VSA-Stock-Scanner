## The idea in plain language

A stock that has been rising often pauses and moves sideways for a few weeks or months. Traders call that sideways stretch a **base**. In a good base the stock goes quiet: the price range narrows and fewer shares change hands, because the sellers have mostly left.

<!-- definition-diagrams:base-definition -->
![Base: a sideways pause](/education/definitions/base-definition.en.svg "A base is a sideways pause. In the illustrated quiet base, price swings and volume contract. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->


A **breakout** is the day the price finally leaves the base upward — to a new high for the whole stretch — on a **burst of volume**. That volume is the point: it suggests large buyers such as funds are stepping in, not just a drift through resistance. The method buys that day.

It is **long-only** and **medium-term**: a breakout is meant to start a move that lasts weeks to months.

![A tightening sideways base followed by a candle closing above resistance and a surge in volume.](/education/images/volume-breakout.png "1 — Price swings and volume quieten inside the base. 2 — The close breaks above the base high. 3 — Volume expands; the app requires at least 1.5× the prior 50-session average. The dashed lower line represents average volume. Schematic example, not market data. Select the image to enlarge.")


<!-- definition-diagrams:example-quiet-base-breakout -->
![Quiet consolidation, then expansion](/education/definitions/example-quiet-base-breakout.en.svg "The example links a contracting price range and fading volume to a later wide bar above resistance. It illustrates the sequence, not a guaranteed outcome. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## Where it comes from

Two of the best-known growth-stock traders buy the same event:

- **William O'Neil**, founder of Investor's Business Daily, in *How to Make Money in Stocks* (the CANSLIM method): buy as the stock breaks out of a proper base, on volume at least 40–50% above normal.
- **Mark Minervini**, in *Trade Like a Stock Market Wizard*: the *Volatility Contraction Pattern* — a base in which the price swings and the volume keep shrinking before the breakout.

In VSA terms it is close to a **Sign of Strength**: a wide up bar on high volume that pushes through old resistance.

## The conditions StockPilot checks

All of these must hold on the same day for a breakout to **fire**:

| # | Condition | How StockPilot measures it |
|---:|---|---|
| 1 | A new high for the base | the close is above the highest high of the previous 50 sessions (about 10 weeks) |
| 2 | A burst of volume | volume is at least 1.5× the average of the previous 50 sessions |
| 3 | Buyers won the day | the close is in the upper half of the day's range |
| 4 | Volume dried up before the breakout | on the day before: the average volume of the last 10 sessions is no higher than the average of the 40 sessions before them |
| 5 | A real, tight base | the previous 50 sessions spanned no more than 35% from their highest high to their lowest low |

<!-- definition-diagrams:volume-breakout-rule-1 -->
![Volume Breakout 1 — A new high for the base](/education/definitions/volume-breakout-rule-1.en.svg "the close is above the highest high of the previous 50 sessions (about 10 weeks) Schematic example. Select the image to enlarge.")

![Volume Breakout 2 — A burst of volume](/education/definitions/volume-breakout-rule-2.en.svg "volume is at least 1.5× the average of the previous 50 sessions Schematic example. Select the image to enlarge.")

![Volume Breakout 3 — Buyers won the day](/education/definitions/volume-breakout-rule-3.en.svg "the close is in the upper half of the day's range Schematic example. Select the image to enlarge.")

![Volume Breakout 4 — Volume dried up before the breakout](/education/definitions/volume-breakout-rule-4.en.svg "on the day before: the average volume of the last 10 sessions is no higher than the average of the 40 sessions before them Schematic example. Select the image to enlarge.")

![Volume Breakout 5 — A real, tight base](/education/definitions/volume-breakout-rule-5.en.svg "the previous 50 sessions spanned no more than 35% from their highest high to their lowest low Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->


Conditions 4 and 5 are what separate a breakout from a **real base** from other big up-days: a gap on news, or a stock that is already running almost straight up with no base underneath. Condition 4 is measured on the day **before** the breakout so that the breakout's own volume cannot spoil it. O'Neil's proper bases are about 12–33% deep; the 35% limit leaves a little room.

The stock needs **at least 160 sessions** of history for the method to judge it.


<!-- definition-diagrams:example-wick-without-breakout -->
![A wick above the base is not enough](/education/definitions/example-wick-without-breakout.en.svg "The last high reaches 109, but the close is 102, below resistance at 104. This example fails the closing-price breakout rule. Schematic example. Select the image to enlarge.")

![Two volume levels at the same threshold](/education/definitions/example-breakout-volume-cases.en.svg "With reference volume 100, the minimum is 150. Volume 180 passes this check; 120 fails even if price has broken above the base. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## What you see in the app

- **Score (0–100):** how ready the stock looks for a breakout right now. Five checks, 20 points each:
  1. the close is above the 50-day moving average (an uptrend);
  2. the 50-day moving average is above the 150-day one (the trend is established);
  3. the price is within 15% of its 52-week high;
  4. volume has dried up (the same test as condition 4 above);
  5. a breakout fired in the last 10 days.

  So a stock tightening quietly just under its high can score 80 before it breaks out, while a stock in a downtrend scores close to 0.
- **Detail text:** "Breakout x2.3 vol" on the breakout day (volume 2.3× its average), "Broke out 4d ago" afterwards, or "3/5 setup" when there has been no breakout in the last 60 sessions.
- **Chart markers:** an indigo dot with a green "Volume Breakout" label on the **first** day of each breakout (a strong move can print several breakout days in a row; only the first is marked).


<!-- definition-diagrams:breakout-readiness -->
![Readiness score versus breakout](/education/definitions/breakout-readiness.en.svg "Four setup checks can score 80 before a breakout; the recent-breakout check contributes the remaining 20 points. The score is not the firing checklist. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## How well it has worked

- **The app's back-test gate** (GPW, 288 companies, measured 2026-09-23): after a breakout the stock beat its own typical move **44.1%** of the time over 10 sessions and **45.1%** over 30. The average edge (+0.20 and +0.49 percentage points) is **smaller than a randomly chosen day gets** in the same test (+0.59 and +1.20). The method **fails** the gate.
- **The direction test** (2026-09-26, 1,010 companies on six markets): after a breakout the stock beat the market **47.0%** of the time over 10 sessions and **45.7%** over 20; a random pick scores about 49.6%. Statistically this is **no better than chance**.

**In short:** with the literature's standard thresholds, a volume breakout has not given an edge on the data the app holds. The thresholds were deliberately left at O'Neil's and Minervini's defaults rather than tuned to past GPW data, because tuning to the past would only make the history look better.

## What the app does not do

- It does not check earnings growth or the other CANSLIM criteria (O'Neil's "C", "A", "N" and so on) — only the price and volume part.
- It does not manage the trade. O'Neil's own rule is to sell a stock that falls 7–8% below the purchase price; the app gives no stop, target or exit signal.
- It does not look at the wider market, which O'Neil treats as decisive ("M" in CANSLIM).


<!-- definition-diagrams:example-breakout-next-paths -->
![A breakout can continue or fail](/education/definitions/example-breakout-next-paths.en.svg "Both hypothetical paths start at the same breakout close. A scanner signal alone does not determine the following price path or manage the exit. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## Sources

- William J. O'Neil, *How to Make Money in Stocks* (McGraw-Hill, several editions) — CANSLIM, base breakouts, the volume rule.
- Mark Minervini, *Trade Like a Stock Market Wizard* (2013) — the Volatility Contraction Pattern.
- [Investor's Business Daily](https://www.investors.com/).
