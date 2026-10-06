## The idea in plain language

Before a stock breaks out to new highs, it usually moves sideways for a few weeks in a **base**. The classic way to buy — [Volume Breakout](/education/volume-breakout) — waits for the day the price leaves that base on heavy volume. By then the price has often already risen, and a failed breakout can drop straight back.

The **pocket pivot** tries to get in earlier, **inside the base**. It looks for one day on which buyers clearly outweigh sellers: the price rises and volume is **at least as large as the biggest selling day of the previous two weeks**. If that happens while the stock is resting quietly on its moving average, it may mean a large buyer — a fund — is buying shares before the breakout.

The method is **long-only** and **medium-term**: like the breakout it tries to get ahead of, it aims to catch a move lasting weeks to months.

## Where it comes from

Gil Morales and Chris Kacher, *Trade Like an O'Neil Disciple: How We Made 18,000% in the Stock Market* (Wiley, 2010), and its sequel *In the Trading Cockpit with the O'Neil Disciples* (2012). Both managed money at William O'Neil + Co., the firm of the founder of Investor's Business Daily; Morales ran part of the firm's own capital there for eight years. The book calls the pocket pivot "an early base breakout indicator".

What the evidence shows, and what it does not:

- Kacher states that his personal account made **18,241% in 1996–2002**, which he says was verified by the audit firm KPMG. But the pocket pivot itself came **later**, in the mid-2000s, so that record is **not** evidence for this rule.
- Kacher himself says that **about half** of pocket pivots, even in good stocks, do not work — roughly as many as ordinary breakouts.
- **No independent test** of the rule was found.

So this is a clearly described method from experienced investors, not a proven edge. The app measures it on its own data (below).

## How it differs from a volume breakout

| | Volume Breakout | Pocket Pivot |
|---|---|---|
| Where it buys | on the day the price **leaves** the base, at a new high | **inside** the base, before the breakout |
| What volume is compared with | the average of the previous 50 sessions | the **biggest selling day** of the previous 10 sessions |
| Where the price must be | above the highest high of the base | close to the 10- or 50-session moving average, not far above it |

The volume comparison is the method's most interesting idea: it sets **demand against supply** — the buyers' day against the sellers' biggest day — exactly the way VSA reads a single bar.

## The six conditions StockPilot checks

All six must hold on the same day for a pocket pivot to **fire**:

| # | Condition | How StockPilot measures it |
|---:|---|---|
| 1 | Buyers won the day | the close is above the previous close |
| 2 | Demand outweighs supply | the day's volume is at least the volume of the **biggest down day** of the previous 10 sessions |
| 3 | The trend is healthy | the close is above the 50-session and the 200-session moving average |
| 4 | It starts from a line, not from thin air | the day's low is at, below, or no more than **2%** above the 10- or 50-session average, and the close is above that average |
| 5 | It was quiet beforehand | the 5 sessions before it averaged less volume than the 50 sessions before them |
| 6 | No wedge | the 5 sessions before it did **not** make a higher low on at least 4 days while the close rose |

Conditions 1–3 are the authors' own words: the book asks for up-day volume "equal to or greater than the largest down-volume day over the prior 10 days" and says pocket pivots are bought above the 50-day moving average; Kacher's rules add the 200-day average. **Three numbers are the app's reading**, because the authors describe these conditions only in words or on charts: "right near" the line (2%), volume "quiet over the previous several days" (5 sessions) and the "wedge" (4 of 5 rising lows). They were fixed before any measurement and not adjusted afterwards.

Conditions 5 and 6 together are the book's picture of a pocket pivot: a quiet pullback or pause on the moving average, then one day of demand heavier than any recent supply. They also cover two of the authors' warnings: a stock that "sells off hard" through its averages and shoots straight back up in a V does not do so on quiet volume, and a stock above its 200-session average is rarely in the multi-month downtrend Kacher warns against.

If there was no down day with volume in the previous 10 sessions, there is nothing to compare with and **no** pocket pivot fires. The stock needs **at least 200 sessions** of history (for the 200-session average).

## What you see in the app

- **Score (0–100):** how complete the pocket-pivot picture is right now. Six checks, about 17 points each: the close above the 50-session average; above the 200-session average; the stock at a buy line (the same test as condition 4); quiet volume; no wedge; and a pocket pivot in the last 10 days. Below the 200-session average the score is capped at 50, because the authors buy no pocket pivot there, so for such a stock the method never counts as positive in the analytics summary.
- **Detail text:** "Pocket pivot x1.4 down-vol" on the signal day (volume 1.4× the biggest down day), "Pocket pivot 3d ago, 6/6" on the following days, and otherwise "4/6 setup" or "2/6 below 200d MA".
- **Chart markers:** a cyan dot with a green label on the signal day — "Pocket Pivot 10d" when the day came off the 10-session average (the authors' usual case), or "Pocket Pivot 50d" when it came off the 50-session average. Two signal days in a row get one marker.

## A real example: XTB, July 2026

At the end of June 2026 XTB (XTB, GPW) spent a week quietly pulling back: its daily lows slipped from 106.84 to about 103.50 PLN, and the five sessions before 1 July averaged **246,074 shares** a day, little more than half the 448,527 of the fifty sessions before them. On **1 July 2026** the price dipped to 105.94 PLN, below its 10-session average of 107.98, and closed at **110.00 PLN** on **424,306 shares — 1.41× the biggest down day of the previous ten sessions** (300,361 shares on 24 June). It was well above its 50-session average (103.42) and its 200-session average (83.23). All six conditions held, and the detail reads "Pocket pivot x1.4 down-vol". Ten sessions later, on 15 July, the stock closed at 135.20 PLN: **+22.9%**.

The same months also show the method saying no. On **2 March 2026** XTB's volume was **2.0×** the biggest recent down day, but the price had come into that day with a higher low on four of the five previous sessions — a wedge (condition 6). On **9 July 2026** volume was **2.7×**, but after an almost vertical run from 110 to 124 PLN the day's low was 7% above the 10-session average — the price was too far from the line (condition 4).

A counter-example: **PZU** met all six conditions on **23 February 2026**, and ten sessions later its price was **8.3% lower**. The three XTB days are checked automatically in the app's tests on the real prices. One good example proves nothing on its own — the measurements below are what count.

## How well it has worked

- **How often it fires:** often. In the stored GPW history it fired about **5 times per company per year** — 2,765 times, on 198 of 288 companies. A little over half of those days (56%) fell on stocks liquid enough for the ranking; the rest were thinly traded days the ranking leaves out.
- **The app's back-test gate** (GPW, about four years, measured 2026-09-26): after a pocket pivot the stock beat its own typical move **46.3%** of the time over 10 sessions and **44.5%** over 30. The average edge (+0.26 and +0.39 percentage points) is **smaller than what a randomly chosen day gets** in the same test (+0.59 and +1.20). The method **fails** the gate.
- **Against the market** (2026-09-26, six markets, stocks above the liquidity floor, the same method as the direction test): after a pocket pivot the stock beat the market's median stock **49.7%** of the time over 10 sessions and **50.4%** over 20; a random pick on the same days scores about **49.6%**. That is **no better than chance**. On the GPW alone the result reached 52.6% over 30 sessions, but on the foreign markets only 46.1% — two results pointing opposite ways, which is exactly what chance looks like.
- **Off the 10-session or the 50-session line:** signals off the 50-session average did slightly better over 10 sessions (53.5% against 49.1%), but on only 254 cases — too few to mean anything.

**In short:** a clearly described rule from experienced investors, but on the data the app holds it has not given an edge. The thresholds were deliberately kept at the authors' values rather than fitted to history, because fitting to the past would only make the history look better.

## What the app does not do

- It does not check the company's fundamentals. The authors also want strong earnings and sales growth and a leader in its industry.
- It does not apply the authors' rare exception: a stock well below its 50-day average that finds support at its 200-day average.
- It does not manage the trade. The authors use moving averages as sell guides; the app gives no stop, target or exit signal.
- It does not look at the direction of the whole market, which the O'Neil school treats as decisive.

## Sources

- Gil Morales, Chris Kacher, *Trade Like an O'Neil Disciple: How We Made 18,000% in the Stock Market* (Wiley, 2010) — chapter 4, pocket pivots.
- Gil Morales, Chris Kacher, *In the Trading Cockpit with the O'Neil Disciples* (Wiley, 2012).
- Chris Kacher, "Ten Rules for Trading Pocket Pivots" — [reprint on NewTraderU](https://www.newtraderu.com/2012/08/21/ten-rules-for-trading-pocket-pivots-2/).
- [The Virtue of Selfish Investing](https://www.virtueofselfishinvesting.com/) — the authors' website.
