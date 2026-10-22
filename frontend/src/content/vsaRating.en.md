## What the VSA rating is

The VSA rating is the number from 0 to 100 shown next to every company on the Dashboard, the Watchlist and the stock page. It is StockPilot's own reading of **Volume Spread Analysis** (VSA) — a way of looking at a chart that compares how much was traded (volume) with how far the price moved (the spread) and where the day closed.

- **50** means nothing notable has happened lately.
- **Above 70** (green) means recent bars showed signs of strength.
- **Below 30** (red) means recent bars showed signs of weakness.

The rating describes the **last 120 days** of trading. It is not a price target and not a recommendation. How well it has actually predicted anything is covered honestly in "How well it has worked" below.

![A spring and an upthrust illustrate opposing contributions to a VSA rating scale from 0 to 100, centred on 50.](/education/images/vsa-rating.png "Signs of strength add weight and signs of weakness subtract it, after the background checks described below. A spring and an upthrust illustrate the two sides. Older signals gradually fade; 50 is neutral, above 70 indicates strength and below 30 weakness. The rating is not a forecast. Schematic example, not market data. Select the image to enlarge.")

## The six patterns the engine looks for

For every trading day the engine compares the bar with the **previous 20 sessions**: their average spread, their average volume, and their highest high and lowest low. A day can carry at most one pattern. The table shows the default settings; you can change most of the numbers on the Scanner page, and the rating then follows your settings.

| Pattern | Direction | What the engine checks (default settings) | Weight |
|---|---|---|---:|
| Spring | bullish | The low breaks below the lowest low of the previous 20 sessions, but the close is back above it, in the top 40% of the bar. Either a wide bar (spread over 1.2× average) on high volume (over 1.2× average, but not more than 4×), or low volume (under 0.7× average) with only a shallow dip (at most half an average spread below). | 0.9 |
| Sign of Strength (SOS) | bullish | A wide up bar (spread over 1.5× average) on high volume (over 1.5×, not more than 4×) that closes in the top 35% of the bar, above the previous close and above the highest high of the previous 20 sessions. | 1.0 |
| Successful Test | bullish | The bar dips below the previous bar's low into the lowest quarter of the 20-session range (no more than half an average spread below it), closes in the top 35% of the bar, on volume under 0.7× average and lower than each of the two previous days. | 0.75 |
| Upthrust | bearish | The high reaches the highest high of the previous 20 sessions, but the close falls back below it, in the bottom 30% of a wide bar (spread over 1.2× average). Volume either high (over 1.3×) or low (under 0.7×). | 0.85 |
| Sign of Weakness (SOW) | bearish | A wide down bar (spread over 1.5× average) on high volume (over 1.5×) that closes in the bottom 35% of the bar, below the previous close. | 1.0 |
| No Demand | bearish | A narrow up bar (spread under 0.7× average) on volume under 0.7× average and lower than each of the two previous days, not closing in the top 35%. | 0.6 |

<!-- definition-diagrams:rating-spring -->
![Spring](/education/definitions/rating-spring.en.svg "The low breaks below the lowest low of the previous 20 sessions, but the close is back above it, in the top 40% of the bar. Either a wide bar (spread over 1.2× average) on high volume (over 1.2× average, but not more than 4×), or low volume (under 0.7× average) with only a shallow dip (at most half an average spread below). Schematic example. Select the image to enlarge.")

![Sign of Strength (SOS)](/education/definitions/rating-sos.en.svg "A wide up bar (spread over 1.5× average) on high volume (over 1.5×, not more than 4×) that closes in the top 35% of the bar, above the previous close and above the highest high of the previous 20 sessions. Schematic example. Select the image to enlarge.")

![Successful Test](/education/definitions/rating-successful-test.en.svg "The bar dips below the previous bar's low into the lowest quarter of the 20-session range (no more than half an average spread below it), closes in the top 35% of the bar, on volume under 0.7× average and lower than each of the two previous days. Schematic example. Select the image to enlarge.")

![Upthrust: engine rules](/education/definitions/rating-upthrust.en.svg "The high reaches the highest high of the previous 20 sessions, but the close falls back below it, in the bottom 30% of a wide bar (spread over 1.2× average). Volume either high (over 1.3×) or low (under 0.7×). Schematic example. Select the image to enlarge.")

![Sign of Weakness (SOW)](/education/definitions/rating-sow.en.svg "A wide down bar (spread over 1.5× average) on high volume (over 1.5×) that closes in the bottom 35% of the bar, below the previous close. Schematic example. Select the image to enlarge.")

![No Demand: engine rules](/education/definitions/rating-no-demand.en.svg "A narrow up bar (spread under 0.7× average) on volume under 0.7× average and lower than each of the two previous days, not closing in the top 35%. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->


An "up bar" means the close is higher than the **previous day's close** — not higher than the day's own open. That is the VSA definition, and it is why the colour of a candle and the direction of a VSA bar can differ.


<!-- definition-diagrams:example-reference-window -->
![The candidate is outside its reference window](/education/definitions/example-reference-window.en.svg "The average spread, average volume and range extrema come from the previous twenty sessions. The candidate bar is evaluated against them. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## The background check

VSA insists that a pattern means only what its background lets it mean. The engine reads the background from the **average close of the previous 30 sessions**:

- if the previous close is at least 3% above that average, the background is **rising**;
- if it is at least 3% below, the background is **falling**;
- otherwise it is **neutral**.

A Spring or a Successful Test is ignored in a falling background (a break lower in a downtrend is a breakdown, not strength). An Upthrust or No Demand is ignored in a rising background (a quiet pause in a strong advance is not a warning).

Two cases are read as a **climax** instead. A Sign-of-Strength bar on more than 4× average volume in a rising background is treated as a **buying climax** and counted as bearish (it is shown as an Upthrust). A Sign-of-Weakness bar on more than 4× volume that makes a new low in a falling background may be professional buying into panic ("stopping volume"), so it produces no signal at all.


<!-- definition-diagrams:rating-background -->
![Rising, neutral or falling background](/education/definitions/rating-background.en.svg "The previous close is compared with the prior 30-session average. The neutral band lies between −3% and +3%. Schematic example. Select the image to enlarge.")

![Climax exceptions](/education/definitions/rating-climax-filter.en.svg "More than four times average volume changes how the engine treats certain extreme bars: an upward climax is bearish, and a downward stopping-volume case is ignored. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## From patterns to one number

Every pattern carries its weight (the last column of the first table), and that weight **halves every 30 days**, so an old signal fades away gradually. Bullish weights are added, bearish ones subtracted, giving a *net score*. The rating is:

<!-- definition-diagrams:rating-decay -->
![Signal weights fade with age](/education/definitions/rating-decay.en.svg "A signal retains half its weight after 30 days and one quarter after 60 days. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->


> rating = 50 + 50 × tanh(net score ÷ 2), rounded

`tanh` is a smooth curve that keeps the result between 0 and 100, so a single signal never pushes the rating to an extreme. The verdict badge (Strong Buy … Strong Sell) is read from the **same** net score, which is why a green rating can never carry a "Sell" badge.

| Net score | Rating (about) | Verdict | Typical cause |
|---|---:|---|---|
| +3 or more | 95+ | Strong Buy | several fresh bullish signals |
| +1.2 to +3 | 77–95 | Strong Buy | a fresh strong signal plus support |
| +0.45 to +1.2 | 61–77 | Buy | one fresh Sign of Strength (≈ 73) |
| −0.45 to +0.45 | 39–61 | Hold | nothing recent, or signals cancelling out |
| −1.2 to −0.45 | 23–39 | Sell | one fresh No Demand (≈ 35) |
| −1.2 or less | 23 or less | Strong Sell | fresh strong bearish signals |


<!-- definition-diagrams:example-offsetting-signals -->
![Opposing signals can cancel out](/education/definitions/example-offsetting-signals.en.svg "A bullish contribution of +1 and a bearish contribution of −1, with equal decay, sum to zero. The formula then returns a rating of 50. Schematic example. Select the image to enlarge.")

![One signal fades toward neutral](/education/definitions/example-rating-decay-example.en.svg "With no new signals, an initial bullish weight of 1 becomes 0.5 after 30 days and 0.25 after 60. The corresponding rounded ratings are 73, 62 and 56. Schematic example. Select the image to enlarge.")

![Net score → rating](/education/definitions/rating-transform.en.svg "The tanh transformation keeps the rating between 0 and 100. Opposing weights can cancel around neutral 50. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## Where you see it in the app

- **Dashboard, Watchlist, Filters:** the *Rating* column, the verdict badge and "days ago" (how long since the last signal of any kind).
- **The "1W" chip:** the same engine run on **weekly** candles built from the same daily bars. A green "1W ✓" means the weekly chart leans the same way as the daily one; a red "1W ✗" means it leans the other way. Nothing is shown when either side is neutral.
- **The stock chart:** green arrows for bullish patterns, red arrows for bearish ones.
- **The Scanner page:** switch individual patterns on or off, change their thresholds, and see back-test statistics for each pattern.


<!-- definition-diagrams:example-timeframe-conflict -->
![Daily strength and weekly weakness](/education/definitions/example-timeframe-conflict.en.svg "Opposite non-neutral daily and weekly verdicts indicate a conflict. They describe different timeframes; agreement is not a forecast of the next move. Schematic example. Select the image to enlarge.")

![Daily and weekly confirmation](/education/definitions/weekly-confirmation.en.svg "The weekly chip compares directions from the daily and weekly engines; a neutral side produces no confirmation chip. Schematic example. Select the image to enlarge.")
<!-- /definition-diagrams -->

## How well it has worked

StockPilot measures its own methods, and the results for the VSA rating are **not good**. They are stated here so that nobody mistakes the rating for a forecast.

- **The app's back-test gate** (GPW, 288 companies, measured 2026-09-23): after a bullish VSA signal the stock beat its own typical move only **44.6%** of the time over the next 10 sessions and **44.0%** over 30 sessions. The gate asks for more than 50%, so the method **fails**. Its average edge (+0.03 and +1.06 percentage points) is no better than what a **randomly chosen day** gets in the same test (+0.59 and +1.20).
- **The direction test** (2026-09-26, 1,010 companies on six markets): after a bullish marker the stock beat the market over 10 sessions **50.1%** of the time, and after a bearish marker it lagged the market **49.3%** of the time. A random pick scores 49.7%. The Buy/Sell verdict gives the same picture: **no better than chance**.
- **The Spring works in reverse on the GPW:** after a Spring the stock beat the market only **42%** of the time over 10 sessions and **37%** over 20. This is one of the few statistically clear results, and it points the wrong way.
- **Across four years of GPW history the rating buckets run backwards:** stocks rated 0–29 went on to beat their own typical 60-session move 53.6% of the time, stocks rated 70–100 only 45.1%.

**In short:** read the rating as a compact description of what volume and price did recently, not as a prediction of what they will do next.

## Further reading

- [VSA Kompendium](/education/vsa-kompendium) — the full compendium behind the app's VSA methods: bar anatomy, the signal catalogue, tests, sequences and risk.
- Tom Williams, *Master the Markets* — the classic VSA text the engine's six patterns are taken from.
- Richard Wyckoff's work on accumulation and distribution, which VSA builds on.
