## The idea in plain language

Stan Weinstein looks at every stock on a **weekly** chart and sees its life as a cycle of four stages, read against its **30-week moving average** (the average weekly close of the last 30 weeks):

| Stage | Name | What the chart looks like | What Weinstein does |
|---|---|---|---|
| 1 | Basing | after a fall, the stock drifts sideways for months; the 30-week average stops falling and flattens | waits |
| 2 | Advancing | the stock breaks out of the base and rises; the average turns up | **buys at the start** |
| 3 | Topping | the stock goes sideways again, this time at the top | sells / stays out |
| 4 | Declining | the stock falls below a falling average | stays away |

The whole method is about buying **the moment Stage 1 turns into Stage 2**: the week the stock breaks out of a long, dull base on heavy volume. That is what StockPilot looks for. It is **long-only** and **medium-term** — a Stage 2 advance usually lasts months.

## Where it comes from

Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (1988). The best independent evidence for it comes from **Thomas Bulkowski**, who sorted 440 of his own real trades (1987–2010, after costs) by the stage he bought in:

- bought at the **Stage 1 → 2 breakout**: average **+13.2%**, **69%** winners (127 trades);
- bought **well inside Stage 2**: average **+4.1%**, **57%** winners (116 trades);
- bought in Stage 3 or 4: lost money.

Those are one trader's own decisions rather than a mechanical test — which is why the app measures the method again on its own data (below).

## Why weekly bars

Weinstein's stages, his 30-week average and his volume test are all defined on **weekly** bars. Running them on daily bars would be a different rule wearing his name. StockPilot builds the weekly candles from the daily prices it already stores, so nothing extra is downloaded.

The **week still in progress is ignored**. Weinstein buys on a weekly *close*, and a half-finished week carries only part of a week's volume, which would make the volume test meaningless. So from Monday to Thursday the method shows the result of the last completed week. A breakout week shows as "fired" on its Friday and over the weekend; from Monday on it shows as "Broke out 3d ago", "Broke out 4d ago" and so on, counted from the latest session. If the following week breaks out again, that is the same move: it gets no new marker on the chart and is not shown as "fired" either.

## The six conditions StockPilot checks

All six must hold on the same completed week for a breakout to **fire**:

| # | Condition | How StockPilot measures it |
|---:|---|---|
| 1 | There was a real base | the 20 weeks before this one stayed within 30% from their highest high to their lowest low |
| 2 | The week breaks out of it | the weekly close is above the highest high of those 20 weeks |
| 3 | It is on the Stage 2 side | the weekly close is above the 30-week moving average |
| 4 | The decline is over | the 30-week average is no lower than it was 10 weeks ago |
| 5 | The advance is only beginning | the 30-week average has risen no more than 10% over those 10 weeks |
| 6 | Buyers are really there | the week's volume is at least 2× the average of the previous 10 weeks |

**Condition 5 is the heart of the method.** Without it, the same rules also fire on a stock that has already risen a long way and merely paused: a flat 20-week stretch on top of a steep advance still has a steeply *rising* 30-week average. That is Bulkowski's weaker "well inside Stage 2" buy. The limit keeps the method on the **transition** Weinstein actually buys. On GPW history it alone rejected 4,467 candidate weeks.

Weinstein's Stage 1 follows a Stage 4 fall, but the fall is **not** checked separately: a stock may have been basing for a year or more, which would put the fall outside the history the app holds. Conditions 4 and 5 already require the flat average that defines Stage 1.

The stock needs **at least 40 completed weeks** of history (the 30-week average plus the 10 weeks it is compared over).

## What you see in the app

- **Score (0–100):** how much of the Stage 1 → 2 picture is in place. Six checks, about 17 points each: a tight base; the 30-week average has stopped falling; it has not already risen more than 10%; the price is above the 30-week average now; the price is no more than 20% above the top of the base (still in the buy zone); and a breakout in the last four weeks. When a breakout was recent, the base is judged as it was on the breakout week — otherwise the breakout's own rise would make the base look "not tight" exactly when the setup has just fired.
- **Detail text:** "Stage 2 breakout x6.9 vol" on the breakout week, "Broke out 12d ago, 5/6" afterwards, "3/6 below 30w MA" or "3/6 setup" otherwise.
- **Chart markers:** a blue dot with a green "Stage 2 breakout" label, placed on the **last trading day of the breakout week**.

## A real example: Dom Development, December 2022

By December 2022 Dom Development (DOM, GPW) had moved sideways in a base for about five months. In the **week of 19 December 2022** (closing on Friday 23 December) it closed above the top of that base on **122,201 shares — 6.9× its average weekly volume of the previous ten weeks** — with the 30-week average flat. The method fires on that week, and the detail reads "Stage 2 breakout x6.9 vol". Over the next four months the stock rose about **44%**.

The same stock broke out again in **July 2023**, but by then the 30-week average had been rising steeply for months — a pause inside a mature Stage 2. That breakout returned at most about +12% and stood near −1% by the end of the year. The method **refuses** it, because of condition 5.

Both cases are checked automatically in the app's tests on the real weekly prices. One good example proves nothing on its own — the measurements below are what count.

## How well it has worked

- **How often it fires:** rarely. Over the whole stored GPW history it fired **0.32 times per company per year** — 174 times, on 69 of 292 companies.
- **The app's back-test gate** (GPW, 288 companies, measured 2026-09-23): after a breakout the stock beat its own typical move **51.0%** of the time over 10 sessions, with an average edge of **+0.64** percentage points and winners 1.27× the size of losers: it **passes** the gate there. Over 30 sessions the edge grows to **+2.07** points with winners **1.96×** the size of losers, but the hit rate drops to 45.9%, so it formally fails (the gate asks for more than 50% winners).
- **Compared with a random day:** a randomly chosen GPW day gets +0.59 and +1.20 points in the same test. At 10 sessions Weinstein is only just above that; at 30 sessions it is clearly above it.
- **Compared with Minervini**, measured the same way: Minervini −0.38 / −0.57, Weinstein +0.64 / +2.07. Buying where the trend *begins* instead of where it is already established turned a negative edge into a positive one.
- **The direction test** (2026-09-26, six markets) had only **85** Weinstein signals at 10 sessions — far too few to conclude anything either way.

**In short:** the most promising of the classic methods in the app, on thin evidence. It is rare by design, so every measurement rests on a small number of trades.

## What the app does not do

- It does not check **relative strength** against the market, which Weinstein also uses.
- It does not manage the trade. Weinstein's own exits rely on stops below support and on the 30-week average; the app gives no stop, target or exit signal.
- It does not read the market's own stage (Weinstein prefers to buy when the overall market is also in Stage 2).

## Sources

- Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (McGraw-Hill, 1988).
- Thomas Bulkowski, [Stage analysis results](https://thepatternsite.com/Stages.html) — 440 trades sorted by buying stage.
