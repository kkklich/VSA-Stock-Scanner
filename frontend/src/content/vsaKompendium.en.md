# VSA: a compendium of the price and volume analysis method

## Scope and how to read this material

This compendium organises the material of the VSA course from the VSA-films catalogue: lessons 1–30, four lessons from the 2018 course, their SRT transcripts and the visual maps. Copies of maps in duplicated folders were treated as duplicates, and the write-up already present in the source catalogue as secondary material. Current transcripts are also available for the lessons that an older document wrongly described as having none. This does not mean that each of the roughly 189,000 words is quoted here, nor that every recording was watched in full. The text synthesises definitions, examples, processes and limitations that can be checked in the texts and maps; in addition, individual frames from lessons 8, 25 and 26 were spot-checked, rather than the videos being reviewed in full. Time references point to timestamp ranges in the corresponding SRT files.

For clarity, four kinds of information are distinguished (the letters follow the Polish original):

- **[K] Course** — a definition or rule spoken in the transcript. It reports what the educational material says; it is not independent evidence of a market edge.
- **[M] Map** — a detail visible on a diagram or map. A map is often a shorthand and sometimes disagrees with the narration.
- **[F] Formalisation** — a neutral way of writing down or operationally checking an idea from the course. A formalisation helps repeat the analysis, but it is not in itself a rule promised by the instructor.
- **[L] Gap** — a parameter, threshold or rule that the source does not settle. Implementing it requires an explicit choice and a test; such a choice must not be presented as a course fact.

In the chapters that follow, the word "signal" means an observed pattern, not a certain price reversal or an automatic instruction to buy or sell. The course repeatedly stresses context, the reaction of the following bars, the background on the higher timeframe and the location of a potential stop loss. A single pattern without these elements is incomplete information.

## 1. What VSA is

VSA stands for Volume Spread Analysis: the analysis of the relationship between volume, the price range and where the bar closes. Unlike looking only at the shape of a candle, VSA asks what price movement accompanied a given amount of trading and whether the market achieved the result one could expect from such an effort. It also asks where the bar appears relative to the preceding move: after a decline, after a rise, at a local high or low, in a correction, at support or resistance, and relative to earlier signals. In the course this foundation appears at the start of the series and returns in the discussion of signals, sequences and the decision process [K: lesson 1, SRT; 2018 course, lesson 1, SRT 01:18:01–01:21:38].

In the language of the course, high volume is "effort" and the price movement and close are the "result". If an up move shows higher volume but price cannot hold a high close, this may indicate supply absorbing demand. If volume falls on a decline and the range narrows, this may indicate weakening supply. These are interpretations of observations, not a direct reading of any particular participant's intentions. An OHLCV chart cannot tell you who made each trade, what their motivation was, or whether a particular bank or fund was accumulating a position.

The course describes the market cycle with the words accumulation, mark-up, redistribution, distribution and mark-down. It is useful to treat these terms as hypotheses about the phase of the market: after a decline, high volume with little progress downward may be interpreted as supply being stopped; after a rise, high volume with no progress upward may be interpreted as demand being absorbed. Only later price behaviour can support or weaken such a hypothesis. High volume alone does not prove accumulation, and a consolidation alone does not prove distribution [K: lesson 1; category split: lesson 7, SRT 00:00:06–00:04:14].

## 2. Data and the anatomy of a bar

### Range (spread)

In this material, spread means the range from the bar's high to its low: H − L. It is not the difference between the open and the close. A wide spread means a large price range within the period, a narrow one a small range. "Wide", "average" and "narrow" are relative: a bar is compared with others of the same instrument and timeframe, especially the nearest bars and the area in which the signal appears. The course does not define a universal number of ticks or a percentage that always separates a narrow spread from a wide one [K; lesson 1; the discrepancy is detailed below].

A narrow spread on high volume may mean that despite heavy trading price did not travel far. VSA describes this as effort without a proportional result. A wide spread on low volume may mean that price moved easily, against little resistance. Neither observation means anything without the direction of the move and the background.

### Where the bar closes

The lectures and maps discuss a close high, in the middle or low in the range. Operationally, the relative position can be expressed as the close's position between the low and the high: (close − low) / (high − low), when the range is positive [F]. Then 0 means a close at the low and 1 a close at the high. This is only a convenient description. In 2018 the instructor speaks of the approximate upper or lower third and explicitly advises against treating the boundaries with "pharmacist's precision" [K: 2018 course, lesson 2, SRT 00:09:47–00:10:07]. One map gives 30/70% thresholds; they should be read as a visual shorthand, not as a universal constant of the whole course [M]. In later use, adopting a boundary such as 30% or 70% is an implementation choice [F/L] that has to be described and verified.

The course sometimes describes the close position in thirds and sometimes uses the words "high" and "low" qualitatively. It is worth staying precise: "a close in the lower part of the range" is an observation; "supply won" is its interpretation.

### Up Bar, Down Bar and body colour

An Up Bar is a bar whose close is higher than the previous bar's close; a Down Bar — lower [K; lesson 1]. This classification compares the close with the previous close. The colour of a candle body usually compares the close with the open, so it is not the same thing. A bar can close above the previous close and at the same time below its own open; it can then be an Up Bar even though the candle has a red body. Likewise a Down Bar can have a rising body.

The difference is practical: the Up/Down classification describes the relation to the previous bar and is used in the definitions of No Supply, No Demand and the two-bar formations; the body colour describes the relation within the candle. The colour of volume bars on a platform may in turn depend on the candle colour or on the indicator's settings. Three different things should not be confused: the direction of the close versus the previous close, the body colour versus the open, and the colour of the volume bar.

### Volume

Volume is counted for a specific instrument and data feed. For exchange-traded contracts it may mean the number of contracts traded in the period. In some OTC markets and on CFD platforms the displayed measure may come from a particular provider — for example tick volume, or the volume available for the instrument on that platform — and need not represent the whole market. The 2018 course lessons criticise tick volume and promote volume from real transactions; the remark on how the xStation platform calculates its own volume should be read as a description of the solution used at the time, not as a universal guarantee for every instrument and current platform [K: 2018, lesson 1, SRT 01:15:10; lesson 4, SRT 00:34:29–00:37:43].

Compare like with like: the same instrument, data source, timeframe and — where it matters — a similar time of the session. Contract volume, share volume, tick counts and open positions are not interchangeable. Volume measures the contracts that changed hands during the period; open interest is the number of futures contracts still open. The two answer different questions [CME Group, Open Interest](https://www.cmegroup.com/education/lessons/open-interest).

In the No Supply and No Demand maps, pink marks volume lower than the two previous bars in the platform configuration used. The lessons say so explicitly [K: lesson 12, SRT 00:00:06–00:01:19; lesson 19, SRT 00:00:06–00:01:08]. Pink is not a natural property of volume, nor a market signal on its own. An algorithm should state explicitly whether it means a value lower than on the previous two bars or merely the indicator's colour. If a platform colours volume differently, the meaning has to be translated into numbers.

## 3. The core logic: effort-result, background and timeframe

### Effort-result

Effort versus result compares relative volume with what price did. High volume is great effort, but it does not dictate a direction. The result is judged by the spread, the direction, the close and the next move.

- **High volume and clear progress upward, closing high:** a consistent result for demand, unless the background says otherwise.
- **High volume on an up move but little progress, an upper wick or a low close:** a possible lack of result from effort, supply entering or demand being absorbed; the following bars are needed to confirm it.
- **High volume on a down move with a low close:** may mean active supply, but at the end of a move it may also be a selling climax; location and the later reaction are decisive.
- **Low volume and a narrow down bar after a rise:** a possible correction with falling supply; in a bullish background it may be neutral or favour a resumption of the trend.
- **Low volume on an attempted rise after distribution:** may mean no demand; it is weakness only in context, not because one bar is small.

No Result From Effort is the named form of this principle in the course. The course example is a rise on high volume after which price cannot hold a high close. If demand dominated, the expected result would be a bar closing high; a low close is interpreted as a possible advantage for supply [K: lesson 17, SRT 00:00:06–00:01:04]. Volume on its own must not be equated with "buyers' effort", however: every trade has a buying and a selling side. VSA reads the effect of trading on price; it does not add up independent buyers and sellers.

### Background — the market backdrop

Background is the context preceding a local signal. It covers at least:

1. the direction and structure of the move on the timeframe being analysed;
2. whether the market is in an impulse or a correction;
3. the character of volume on the up and down waves;
4. earlier signs of strength and weakness and their tests;
5. areas of support/resistance and the relation to earlier extremes;
6. behaviour on the higher timeframe.

A local No Supply after strong distribution does not automatically carry the same meaning as a No Supply after accumulation. An Upthrust after a long rise may warn of supply, but in the middle of a strong uptrend it may be just a failed breakout attempt after which the trend continues. A Test matters only when there is an area of supply or earlier strength to test [K: lesson 13, SRT 00:00:06–00:01:13]. The 2018 course encourages looking for the last accumulation or distribution in the background rather than isolating a single candle [K: lesson 2, SRT 00:28:02 onward].

Background is not an excuse to change a signal's definition after the fact. It is worth keeping two notes apart: "the pattern meets definition X" and "here I interpret it as a confirmation/warning because of the earlier context Y". This helps avoid fitting the narrative to the outcome.

### The character of volume on waves

The lesson on bullish and bearish volume talks about a sequence of waves, not a single bar. Bullish volume: an up move tends to increase volume and a pullback to decrease it. Bearish volume: the down waves have higher or rising volume and the rebounds falling volume. This observation helps judge whether a correction is calmer than the move in the direction of the trend [K: lesson 6, SRT 00:00:06–00:02:39].

It does not mean that every up bar must be taller than the previous one, or that every pullback in a downtrend must have falling volume. The lecture describes the relative character of the waves. [F] It can be studied over segments by comparing the typical volume of the impulse and of the pullback in the same instrument and period, but the source gives no window, averaging or threshold values [L]. If the waves cannot be identified reliably, the assessment is uncertain.

### Timeframe

The course recommends first establishing the direction on the higher timeframe and then looking for a place to join it on the lower one. For example, for a decision on a 5-minute chart the hourly chart may be the higher one; for an hourly decision, the four-hour chart [K: lesson 6, SRT 00:01:49–00:02:39]. This is not an instruction to use only these pairs. Timeframes should match the instrument's liquidity, the position's horizon and your ability to watch the market.

The higher timeframe helps judge the trend and context but does not automatically resolve a conflict. If the daily chart is rising and the hourly chart shows distribution, a short-term decision depends on whether the aim is a trade against the correction or an entry with the main trend. It is worth writing down which timeframe provides the bias and which the trigger. Flipping through timeframes until a matching signal appears risks choosing after the fact.

## 4. Signal classes and the signal catalogue

Lesson 7 divides signs of strength into accumulation signals, supply-gathering signals and supply-testing signals, and signs of weakness into distribution signals, demand-flooding signals and demand-testing signals [K: lesson 7, SRT 00:01:25–00:04:14]. Signs of strength are sought after a decline or at the end of a downward correction in an uptrend; signs of weakness after a rise or at the end of an upward correction in a downtrend [K: lesson 7, SRT 00:00:06–00:01:25]. The course does not assign every pattern to one class without exception: depending on volume, a Two Bar Reversal can be a gathering signal or a test of supply/demand. The catalogue below therefore gives the class as an interpretation where it depends on volume and context.

In the descriptions, "confirmation" means a later observation that supports the hypothesis; it is not statistical confirmation or a guarantee of the outcome. "Invalidation" means behaviour that weakens the original interpretation or requires reassessment. The course does not always give a formal invalidation price; where it does not, this is marked as a gap.

### Signs of strength

#### 1. Bag Holding

**Pattern [K].** After a decline a bar appears with a narrow spread and very high or ultra-high volume, not seen in a comparable stretch to the left on the chart. With such volume, price no longer falls freely. The course's classic variant describes a Down Bar closing roughly in the middle of the range. The instructor also allows an Up Bar, however, if the narrow spread and volume point to the market being stopped. The difference matters: the colour or direction of the bar should not outweigh the relation between range, volume and reaction [K: lesson 8, SRT 01:58–04:35].

**Interpretation.** In the course's language this is accumulation/absorption of supply: heavy trading at low prices but little further progress downward. The pattern should prompt you to watch whether the market can rebound and whether a later test happens on lower volume.

**Support and failure.** A rebound, a successful test or subsequent high closes support the hypothesis. New lows, wide Down Bars and rising volume after the signal weaken it. Bag Holding on its own indicates neither an entry point nor a specific stop loss.

#### 2. Selling Climax

**Pattern [K].** After a clear decline the market makes a wide move down on high or ultra-high volume, but does not close at the very low; a close in the middle of the range indicates a reaction from demand. Comparing the volume with the recent stretch to the left is important. High volume that is not exceptional in the local context does not automatically meet the climax condition [K: lesson 8, SRT approx. 08:45–10:06; contrasting example approx. 14:08].

**Interpretation.** The course interprets this as a selling climax in which demand takes over part of the supply. A climax does not mean "the final bottom" by definition. Price may still revisit the low afterwards, and the market should show whether supply has been tested successfully.

**Confirmation/invalidation.** A rebound and a later test on lower volume support the hypothesis. Further wide declines on high volume closing low suggest supply still dominates. The course sets no required percentage threshold for volume [L].

#### 3. Stopping Volume

**Pattern [K].** A two-bar observation after a decline: the first bar is a Down Bar with rising or pronounced volume; it is followed by an Up Bar closing high, sometimes within the body of the previous red bar. No condition should be added that the second bar must close in the upper part of the first bar's range. The lecture speaks of increased volume on the first bar and a response from demand on the second [K: lesson 9, SRT 00:00:06–01:29].

**Interpretation.** Supply comes in but cannot hold price down; demand absorbs part of the selling. It should not be confused with any red bar on high volume: the later response is part of the pattern.

**Variants and assessment.** The course discusses various relations between the two volume bars; the price reaction matters more than a mechanical requirement that the second bar's volume always exceed the first. A subsequent test of supply on lower volume is further support. New lows on an intensifying Down Bar weaken the interpretation.

#### 4. Shakeout

**Pattern [K].** Price drops sharply, often breaching an earlier low or the lower boundary of a range, and then closes in the upper third of a wide bar. What matters is the lower wick, the reaction from the low and volume, which may be substantial. The course says explicitly that body colour is not a condition: it may be green or red [K: lesson 10, SRT 00:00:06–01:55]. The map shows one variant with a green body [M]; this should not become an extra criterion.

**Interpretation.** A "shakeout" is meant to test supply and eliminate participants reacting to the downside break; in an accumulation background it can be a strong sign that supply has been taken. A similar-looking bar in the middle of a trend may mean something else.

**Confirmation/invalidation.** A rebound, a test on lower volume or subsequent Up Bars support the hypothesis. A low close, no rebound and new lows suggest sellers are still in control. The course also mentions the Shakeout as a test after earlier accumulation — that is a sequence, not a separate guarantee [K: lesson 10, SRT 01:27–01:55].

#### 5. Two Bar Reversal — the strength side

**Pattern [K].** First bar: a Down Bar closing low. Second: an Up Bar whose close reaches at least the first bar's open or higher. The course shows a variant in which the volume of the second, rising bar is greater than the first; an equal value is also allowed later in the discussion [K: lesson 11, SRT 00:36–01:33 and approx. 04:18]. With very low volume across the whole pair, the interpretation may shift from "gathering supply" towards a test [K: lesson 11, SRT 00:06–00:30].

**Interpretation.** Price recovering after a decline shows demand taking supply. On high volume it can be read as gathering supply, on low volume rather as a test. Its location — after a decline, at support or at the end of a correction — matters more than the mere resemblance of two candles.

**Confirmation/invalidation.** A further rise and successful tests support the strength variant; further low closes and new lows weaken it. If the second bar's actual close does not reach the level the course specifies, it should not be made to fit by the look of the body.

#### 6. No Supply

**Pattern [K].** A Down Bar with low volume, lower than on the two previous bars, which is why it is pink in the example platform configuration. The map adds a narrow spread as the typical picture [M]; the transcript specifies above all a Down Bar and pink/low volume [K: lesson 12, SRT 00:00:06–01:19]. A narrow range is common and useful as a feature of context, but it should not be raised, without checking, to a necessary condition stated in the narration.

**Interpretation.** This is a supply-testing signal, not an accumulation signal nor a supply-gathering signal on its own. A decline on falling volume may suggest that selling pressure is fading. It means most after earlier strength, in a correction or near an area of demand.

**Confirmation/invalidation.** A following Up Bar or a further upward reaction confirms that the test worked [K: lesson 12, examples after 11:04 and 12:25]. No upward reaction leaves the signal unconfirmed. If it is followed by a wide Down Bar on rising volume breaking support, the hypothesis of weakening supply loses its basis. "Pink" is a setting that compares volume with the two previous bars, not a property of the market.

#### 7. Test of supply

**Pattern [K].** After earlier strength, price returns to the area where supply was already gathered or where strong signs of demand appeared. A bar appears with an average or narrow spread, low volume and a lower wick. The body is not decisive; the course shows a high close as the favourable variant [K: lesson 13, SRT 00:00:06–02:07]. A Test may, but need not, also be classified as No Supply; the examples show both cases [K: lesson 13, SRT 00:04:07–00:04:35].

**Interpretation.** This is a test in the sense of a question: "does supply still appear in this zone?". Low volume alone does not answer the question until price has checked the earlier demand area. The lecture stresses that a test without earlier accumulation/strength has little value.

**Confirmation/invalidation.** A following Up Bar is the confirmation in the course's sense. A single test without such a response remains an attempt, not a successful test. New lows on rising volume contradict the interpretation. Lesson 21 develops the test as a whole process: strength appears after a decline, the market rebounds, returns to the area and, on falling supply, checks whether it can continue higher [K: lesson 21, SRT 00:01:07–04:40].

### Signs of weakness

#### 8. End of the Rising Market

**Pattern [K].** The classic End of the Rising Market appears after a rise as an Up Bar closing roughly in the middle of the range, with a narrow spread and the highest volume seen in that move [K: lesson 14, SRT 01:07–03:16]. The course describes the formation as rare. The move does not progress in proportion to the effort.

**Interpretation.** Possible distribution: volume is high but price stops rising. The course suggests vigilance, not automatically opening a short position. Repeated high closes after the signal or a continuation of the rise can refute the end-of-trend interpretation. A narrow spread on its own does not predict direction.

**Confirmation/invalidation.** Further weak reactions, an Upthrust, No Demand or a test of demand support the weakness scenario. If the market holds high prices and later rises achieve a good result on strong volume, the weakness thesis fades.

#### 9. Buying Climax

**Pattern [K].** After an extended rise a wide bar appears on exceptionally high volume, not closing at the high — often closing mid-range, with the upper part of the range rejected by supply [K: lesson 14, SRT 06:48–09:02]. The relation to the earlier rise and comparing volume with the local history are important; not every record bar on the screen is a climax.

**Interpretation.** Demand joining an already developed rise may meet supply. A "buying climax" does not prove that price will reverse immediately. The market may build a range, make a test or continue rising.

**Confirmation/invalidation.** Further weak reactions and failed attempts to rise support the distribution interpretation. New high closes and wide rises on volume weaken it. The course stresses the importance of where the bar closes and of the context before the move.

#### 10. Supply Coming In

**Pattern [K].** During an up move an Up Bar appears with an upper wick and increased volume, but the volume is not the highest of the observed rise [K: lesson 15, SRT 00:00:06–01:53]. This is an important feature distinguishing the course definition from the simplification "high volume on a rise".

**Interpretation.** An upper wick and heavier volume on a rise may mean supply entering at higher levels. It is a warning of possible weakening, not a direct sell signal. The instructor says explicitly that it is not an entry in itself and that it is worth waiting for further developments [K: lesson 15, approx. 03:13–04:06].

**Confirmation/invalidation.** A later Trap Upmove, No Demand, Upthrust or weak closes support the scenario. If the market makes progress upward and holds high closes, the Supply Coming In may have been only a pause in the trend.

#### 11. Trap Upmove

**Pattern [K].** After a rise or an upward correction, price makes a false attempt to go higher, sometimes breaking a local high, and then finishes the bar low on increased supply volume. The course's description stresses the low close as a trap for late buyers [K: lesson 16, SRT 00:06–02:14]. The pattern may appear at the end of the rising leg of a correction within a larger downtrend.

**Interpretation.** Participants who bought the breakout end up on the wrong side if price does not hold the move. Not every upper wick should be equated with a trap.

**Confirmation/invalidation.** A following Down Bar, a lower reaction and a failed test of demand support further weakness. Holding a high close, a return above the high and no supply undermine it. The size of the wick is no substitute for the condition of a low close on volume.

#### 12. No Result From Effort

**Pattern [K].** After upward effort — high volume — price does not achieve the expected result: instead of staying high, it closes low or leaves a rejection from the top. In this lesson the example is an inflow of even higher volume but a weaker close than on the previous bar [K: lesson 17, SRT 00:00:06–01:04; examples from 01:46].

**Interpretation.** A possible sign of supply in the background of a rise, in line with the effort-result rule. It is important that the "high volume" is high relative to the move being compared and that the result really is weak. The course gives it no universal threshold.

**Confirmation/invalidation.** Further low closes and no return to high levels support weakness. If price quickly regains the range and continues rising, the initial failure did not confirm a lasting supply advantage.

#### 13. Two Bar Reversal — the weakness side

**Pattern [K].** The first bar is an Up Bar. The second is a Down Bar closing at the first bar's open or lower; the second bar's volume should be similar to the first or higher. The demand-testing variant is when the volume of the whole pair is low relative to the earlier move, and the second bar still has volume similar to or greater than the first; V2 < V1 by itself does not mean a test [K: lesson 18, SRT 00:06–01:17, 02:05 and the further description].

**Interpretation.** After an attempt to rise, price returns below an important level of the first bar, which points to supply potentially taking control. The location after a rise and an earlier background of weakness matter. This is the mirror image of the strength variant from lesson 11.

**Confirmation/invalidation.** Further lower closes support weakness. When price comes back to test demand, falling or low volume on the approach and a subsequent downward reaction are consistent with a failed test of demand. New high closes and no follow-through invalidate it as an advantage for sellers.

#### 14. No Demand

**Pattern [K].** An Up Bar with volume lower than the two previous bars — pink in the configuration shown — is a test of demand [K: lesson 19, SRT 00:00:06–01:08]. The course explains it as an attempt to rise on low volume that shows no active demand.

**Interpretation.** The pattern is most significant against a weak background, after a rise that ended in distribution or after an earlier sign of supply. In an accumulation background the same Up Bar may simply be a low-volume pause before a further rise.

**Confirmation/invalidation.** A following Down Bar or further lower closes support the absence of demand. A strong rise and improving volume mean the supposed test showed no supply advantage. Repeated No Demand bars are not an automatic chain of shorts; you have to judge whether the market actually rejects higher prices after each attempt.

#### 15. Upthrust

**Pattern [K].** Price breaches or tests recent highs but comes back with an upper wick and closes in the lower third of the range. The course separates two variants by volume: on average or higher volume an Upthrust can be a demand-flooding signal; on low volume a demand-testing one [K: lesson 20, SRT 00:00:06–00:01:21]. A "hidden" Upthrust in some examples has a red body/Down Bar and an upper rejection; the name does not change the meaning of the close and the volume.

**Interpretation.** Price briefly tempts buyers above the high but does not hold the higher levels. A single Upthrust does not prove a change of trend. The lesson shows an example in which the first Upthrust does not remove all demand, and only the further reaction and tests clarify the background [K: lesson 20, examples approx. 09:04–09:49 and summary approx. 21:38].

**Confirmation/invalidation.** Lower closes, further failed attempts to rise and No Demand strengthen weakness. A break of the high with price holding and a good upward result weakens it. The level that formally invalidates the interpretation has to be set within each scenario [L].

## 5. The test as a process, not a single candle

Lesson 21 gives testing special weight. A test of supply in the full sequence begins after a decline, when signs of accumulation or strength appear in the market. Price rebounds; it then returns to the area where supply or demand previously appeared. If the descent happens on low or falling volume and the market then responds with a rise, this argues that supply has been checked and may be weaker. If volume rises and the decline does not stop, the test has not succeeded [K: lesson 21, SRT 00:01:07–04:40].

A practical breakdown of the process:

1. **Identify the hypothesis.** What was taken earlier: supply after a decline or demand after a rise? Point to the specific earlier signals.
2. **Mark the test area.** Use an earlier range, extreme or zone where a reaction appeared. Do not choose it only after you have seen a successful outcome.
3. **Watch the effort.** Is the return to the area happening on falling or on rising volume? Is the spread widening or contracting?
4. **Wait for the response.** For a test of supply the course points to a later Up Bar as confirmation; for a test of demand a downward response is needed.
5. **Record what did not work.** If price moves through the area on rising volume, the original interpretation needs revising.

The course's story of a large participant controlling how much supply is released should be read as a teaching model, not as evidence of who actually trades the instrument being watched. From the point of view of chart analysis, what can be checked is the relation of price and volume, not a story about the participant's identity.

## 6. VSA sequences, the WFO and corrections

### Rising and falling sequences

Lessons 23 and 24 describe sequences as ordered chains of three signals. For rises the course combines an accumulation signal, a supply-gathering signal and a test of supply; for declines — distribution, demand flooding and a test of demand. The response to the test should show whether the market is ready to move in the expected direction [K: lesson 23, SRT 00:00:05–03:37; lesson 24, SRT approx. 00:01:25–02:40]. Sequences are a way to organise signals and make the process more consistent, not an automatic entry.

The sources do not establish one exception-free permutation for all instruments. The maps show several combinations, and abbreviations such as "SZP" are not unambiguous everywhere: in some places they stand for "supply-gathering" and in others, on the falling map, they are labelled "demand-flooding". This text uses full names rather than the abbreviation. It should not be concluded that each of the 15 signals discussed has an assigned place in a sequence. If three relevant observations do not occur, their absence cannot be filled in with any similar-looking candles.

When practising sequences, it is worth recording: signal 1 and its background; the reaction area; signal 2; whether the market reached a test; what volume looked like during the test; and what the price response was. This separates correct identification of a pattern from the result of a trade. The course encourages reviewing earlier trades for sequences [K: lesson 23, SRT 01:42–02:20], but the claim that sequences "dramatically increase effectiveness" is the instructor's assertion, not an independent statistic.

### WFO — the volume reversal formation

The WFO (from the Polish *wolumenowa formacja odwrócenia*) of lessons 25 and 26 compares two successive extremes separated by a correction. The bearish WFO has two peaks, the second higher in price; the bullish WFO has two troughs, the second lower in price. In both descriptions the first extreme has the larger volume, and the second volume is smaller than the first but larger than every volume in the stretch between the extremes: V1 > V2 > every volume in between [K: lesson 25, SRT approx. 14:37; lesson 26, SRT 00:46–01:15 and 09:20–09:34]. This distinguishes the second extreme from an ordinary correction on falling volume.

A WFO is not just finding two peaks or two troughs. The course gives a minimum price difference of one tick between the extremes [K: lesson 25, SRT approx. 03:06; lesson 26, SRT approx. 00:38]. The extreme points, the correction interval and the comparability of volumes must all be determined; the source does not, however, establish full rules for detecting swings or a minimum correction depth [L]. For code, the choice of an extreme-detection algorithm will therefore be a formalisation [F], not the "original formula" of VSA.

A WFO is an area of interest and can support a scenario, but it does not settle whether price will immediately reverse the whole trend. The material discusses different later paths: a continuation of the earlier direction after a correction, and a change of direction after a rebound and a successful test [K: lesson 26, SRT 01:15–02:07]. A WFO can therefore supply a hypothesis, and a further test and the price structure are needed to tell the variants apart. The course mentions combining the WFO with another technique and with geometry [K: lesson 25, SRT 05:47–06:12].

### Corrections

Lesson 27 distinguishes a correction on dying volume from a correction ended by a clear "sweep" or "flush". In a classic trend correction the volume of the pullback is weaker than on the impulse in the direction of the trend. In the second kind, the end of the correction itself signals demand or supply re-entering, sometimes through a sharp bar on increased volume [K: lesson 27, SRT 00:00:54–01:15 and 06:31–08:17]. These words are descriptive; the source gives no numerical definition of "dying" volume and no threshold from which a correction counts as finished.

A correction may look like a move against the trend, but also like a consolidation or a sharp testing move. It is told apart by structure, the direction of the dominant waves and the character of volume; it is not enough to call every opposing move a "correction". If volume on a decline in an uptrend rises and price makes wide down bars, the hypothesis of a mild correction weakens. On the downtrend side the rebounds should be watched in the same way.

## 7. Geometry as a level to watch

Lesson 22 does not teach geometry as a standalone VSA system; it shows VSA as confirmation of geometry. The example retracement levels named in the lecture are 38.2%, 41.4%, 50% and 61.8%. They are measured from trough to peak or the other way round, but touching a line is not a trading signal in itself. The instructor stresses that price may turn at one of the levels, stop at none, or break through all of them [K: lesson 22, SRT 00:00:06–03:57; map and transcript].

A practical process: first decide which impulse is being measured and why; then record the earlier strength or weakness; then judge whether the approach to the level happened on impulse or corrective volume; finally wait for the price reaction and a VSA signal. In the course's scenario no. 5, the 0.5 and 0.618 geometry also appears as a planning zone, not a certain turning point [K: 2018 course, lesson 3, SRT 01:00:40–01:03:40]. One map reads a handwritten level as 0.878; the narration clearly says 0.5 and 0.618, so the map's reading is not reliable here.

This compendium does not prescribe the width of the zone around a Fibonacci level, the rule for choosing anchors, how to combine several levels, or how to filter false reactions. These elements have to be written down explicitly before a test [L]. VSA can describe behaviour at a level; it does not remove the uncertainty about whether the chosen geometry matters.

## Candles and bars as a complement to VSA

Lessons 3 and 4 present candlestick formations as an extra filter for location and price behaviour. The course does not recommend trading on candle shape alone: a formation must appear in the right background and receive volume confirmation. For the hammer the instructor describes a long lower wick, a close near the high, a body no larger than about one third of the range, a location after a decline, and body colour being irrelevant. A tall upper wick disqualifies the classic shape. The narration ties the entry to the close of a confirmed hammer and the level below its low to invalidation [K: lesson 3, SRT 00:00:06–02:50].

The mirror-image shooting star appears after a rise, has a long upper wick, a close near the low and a small body; a large lower wick weakens the qualification. The course describes a stop loss above the formation's high and the requirement of a VSA background [K: lesson 4, SRT 00:00:06–02:04]. The other examples in these lessons include the piercing line and the morning star after a decline, and the evening star, dark cloud cover and bearish engulfing after a rise. For the evening star the map has no separate strategy slide, so rules from neighbouring formations should not be carried over to it mechanically.

Lesson 5 distinguishes entering on the close of a candlestick pattern from entering on a breakout. In an Inside Bar the second bar lies entirely between the high and low of the first; only the third bar, when it breaks the first bar's high or low, triggers the directional variant [K: lesson 5, SRT 00:01:01–03:53]. Body colour does not define this formation. The strategy map shows a short setup, but the narration clearly discusses the Inside Bar for both rises and declines. These formations can help set a trigger and an invalidation level, but they do not replace VSA or an assessment of the cost of entering after a breakout.
## 8. The decision process from observation to trade

Lesson 29 separates a directional assessment from a scenario. The directional assessment says whether the current background looks bullish, bearish or ambiguous. A scenario additionally has defined conditions for entry, stop loss and trade management [K: lesson 29, SRT 03:33–05:09]. A direction without an entry point is not yet a finished plan. You can have a clear background but no sensible place with a close stop; then "no position" is a fully legitimate outcome of the process [K: lesson 29, SRT 11:03–11:28].

The order below is a formalisation [F] of the course's process, not a quotation from a single checklist:

1. **Check your readiness and state of mind.** Are you able to carry out a plan set in advance, or are you trying to win back a previous loss, chasing the market or ignoring signals? The course begins the scenario with a self-assessment [K: lesson 29, SRT 01:05–01:34].
2. **Choose the instruments and timeframes.** It is better to understand one market than to get lost in many positions at once [K: lesson 28, SRT 08:26–09:15]. Note which timeframe defines the trend and which should provide the entry.
3. **Define the background.** Mark the trend, the impulse and correction waves, earlier signals, zones and the quality of the volume data. Do not call the background accumulation just because it is a consolidation.
4. **Write down the hypothesis.** For example: "the decline into the area of earlier strength is corrective; I want to see a test of supply and a response from demand". Also state which observation would refute the hypothesis.
5. **Set the trigger.** It can be a confirmed test, a signal in a sequence or another explicit element of the scenario. Do not open a position merely because a Fibonacci level was touched or one bar of pink volume appeared.
6. **Set the invalidation level and the stop.** The stop loss should be tied to the point beyond which the original reason for entering no longer holds, not chosen to get a convenient position size.
7. **Calculate the position size and cost.** Include the point/tick value, the quote currency, the spread, commission, any financing, the minimum lot and expected slippage.
8. **Assess reward to risk.** The course uses 3:1 as a target minimum ratio or an illustration of the scenario, not as a law of the market. Record whether the potential target has a basis on the chart and whether costs do not consume the edge.
9. **Manage according to rules written down before entry.** The course examples include moving the stop to breakeven and exiting on a strong opposite signal; the exact rule for when to do so should be specified in the strategy being tested.
10. **Record the result and its classification.** Separate correct execution of the plan from the outcome of a single trade. A planning error, a data error, an execution error and a normal loss are different categories.

### Scenario no. 5 as an example of the process, not a universal template

In lesson 29 the condition for choosing an "important place" is one of several variants: the end of an ABC correction, a WFO or a geometric level [K: lesson 29, SRT 12:38–14:22]. They are not three conditions that must occur together. The further stages of this particular scenario are more detailed: no strong supply at the earlier peak, a corrective descent in volume, a candlestick formation confirmed by a VSA signal, and a potential of at least 3R [K: lesson 29, SRT 16:04–18:04; details at 16:24, 16:46, 17:12 and 17:41–18:04 among others]. The scenario illustrates the relation between direction, zone and entry; it should not be applied automatically to every position.

### The trade plan as a card filled in before entry

A minimal record that lets the process be checked later may contain:

| Field | What to record |
|---|---|
| Instrument and feed | Symbol, instrument type, volume provider, session and timeframe |
| Background | Trend/range, impulses and corrections, relevant signals from the higher timeframe |
| Hypothesis | What the market may be doing and which data support it |
| Pattern | Name of the signal/section, the bars and the exact criteria it meets |
| Trigger | The observable condition that permits entry |
| Invalidation/SL | The level and its justification; which move invalidates the hypothesis |
| Size | Risk capital, stop distance, point value, costs, quantity |
| Target and management | Target level or exit rule; conditions for moving the stop |
| Uncertainty | Missing signal, timeframes disagreeing, data limitations, upcoming macro events |
| Result | R, costs, slippage, plan execution, a chart screenshot from the moment of decision |

## 9. Risk, stop loss, position size and costs

### Stop loss and position size

The course rightly separates the directional assessment from the placement of the stop loss and risk management. Lesson 28 describes the percentage of capital put at risk on a single trade: 0.5% is given as a reference point for beginners, and further values depend on experience; in different places 1%, up to 1.5% and 2.5% as a ceiling for the experienced appear. This is not a consistent, universal recommendation. These values should be read as statements and examples from the course, not as a recommendation to the reader [K: lesson 28, SRT 13:30–14:20, 15:55–16:58, 22:03–23:02]. What matters more is limiting the loss amount in advance, not fitting the chart to an arbitrary percentage.

General planning arithmetic [F]:

- capital allotted to the loss = account capital × chosen risk percentage;
- loss per unit before costs = abs(entry − SL) × value of a full point, or abs(entry − SL) / tick size × value of one tick;
- quantity = rounded down to the quantity step: risk amount / loss per unit including entry and exit costs.

A purely arithmetic example, not a recommendation of any instrument: capital of 10,000 units of the account currency, 1% risk gives 100; entry 100, SL 95, point value per unit 1, cost of a full round trip 0.20 per unit. The risk per unit is 5 + 0.20 = 5.20, so 100 / 5.20 = 19.2307; with a quantity step of 0.01 this can be rounded down to 19.23. A gap and slippage can make the actual loss exceed this value. This is not a complete algorithm for every broker. The contract multiplier, the minimum volume step, the settlement currency, commission, spread, currency conversion and the possibility of a gap have to be taken into account. If, after allowing for the minimum position size, the risk exceeds the limit, the correct decision may be to skip the trade. The stop should not be tightened merely to "fit" a position that is too large.

The stop loss should correspond to the technical invalidation of the scenario. A stop that is too tight may be hit by ordinary noise; one that is too wide requires a smaller position. A stop order does not guarantee execution at the stop price: once triggered, a market order may be filled at a worse price in a fast move or a gap [FINRA, Stop Orders](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets). The mechanics and the available order types depend on the market, the broker and the product.

### Reward to risk

3:1 appears in the course as the minimum potential reward relative to risk in the scenario discussed and in the trade-management examples [K: lesson 28, SRT approx. 35:48–37:34; 2018 course, lesson 3, SRT 01:09:35]. The ratio of target to stop alone does not say whether a strategy is profitable. Under the simple assumption of one winning size of 3R and a loss of 1R, the breakeven point before costs is 25% winners, provided no positions are closed at breakeven. Commissions, slippage, different exits, gaps and partial fills change this arithmetic.

The lesson 28 example of a series of 20 trades with an illustrative combination of wins and losses is meant to show the role of how risk is distributed, not to prove the method's edge. Every such calculation should state its assumptions explicitly: whether the risk percentage is taken from variable or fixed capital; whether it includes costs; how it treats breakeven; how large the drawdown was; which sample was used. A small sample and selected chart examples do not allow future effectiveness to be judged.

### Costs and macro

A trade costs the spread, commission, overnight financing, any contract roll-over, slippage and execution in thin liquidity. If the signal and the stop are close together, costs can materially worsen the real reward-to-risk ratio. A back-test should apply costs appropriate to the instrument and period; conclusions about the whole market must not be drawn from CFD data if the volume source is broker-only.

Lesson 30 discusses four general kinds of reaction to data: a move in line with expectations; an initial move in line with the data after which price reverses; an initial reaction against expectations followed by strong continuation; and a delayed or ambiguous reaction [K: lesson 30, SRT 00:00:14–01:39]. Instead of assuming that "good data must lift the price", the course encourages watching the reaction of price and volume. The source sets no fixed waiting time after a release [L]. Before a release, the possible spread, gap, fast price changes and the risk of slippage have to be taken into account.

## 10. Formalising the method in code and its limits

Code can compute bar features repeatably and mark potential patterns. It cannot by itself establish that the market is "accumulating" unless rules for the background, swings, spread thresholds, volume comparisons, confirmation and invalidation have been defined and tested. Every parameter must have a status: from the course, explicitly adopted by the implementation, or not handled.

A minimal, auditable data layer should contain OHLCV, timestamp, symbol, timeframe, price unit, volume source and session rules. Check for missing candles, duplicates, time-zone changes, periods without trading and any contract changes. A candle with a zero spread needs careful handling, because the relative close position would divide by zero. Future data must not leak into the calculation of a signal or into a retrospective label.

A practical split of the implementation:

| Layer | Examples | Status |
|---|---|---|
| Base features | H − L, close vs previous close, close position, volume | [F], no threshold |
| Relative classification | Narrow/wide spread; low/exceptional volume | [L], window/method must be chosen |
| Patterns | No Supply, Upthrust, Two Bar Reversal, WFO | Course criteria plus formalisation |
| Context | trend, correction, test area, support | Partly [K], swing extraction [L] |
| Confirmation | next bar, retest or sequence | [K] in direction, timing [L] |
| Risk | SL level, risk amount, quantity, costs | [F], contract-dependent |
| Assessing results | forward test, costs, drawdown, stability | Requires data; does not follow from the VSA definition |

Example decisions that need an explicit description:

- What number of bars or what local characteristic defines a "narrow" spread?
- How do you determine "very high" volume: a local maximum, a percentile, the median, a z-score, or only a visual comparison? The course does not impose one method [L].
- Is "pink" volume exactly lower than the two previous bars? That is how the course describes it, but the actual indicator has to be checked.
- How do you detect the two WFO extremes and the correction range without using future bars?
- How long do you wait for confirmation, and what do you do when it does not come?
- Does the back-test include commission, spread, slippage, gaps, contract changes and lack of liquidity?
- Are signals computed after the bar closes? If so, entry can only happen later than the signal bar's closing price.

Only after these choices are written down is it worth studying results. The design period should be kept separate from validation, different market phases should be checked, and thresholds should not be tuned on individual examples from the course. A reasonable analysis covers the number of trades, the result after costs, the average R, drawdown, the distribution of losses, dependence on instrument and timeframe, and behaviour out of sample. These are rules for evaluating an algorithm [F], not a claim that VSA delivers a positive expected value in advance.

## 11. What the sources say, and what they do not prove

The course talks about "smart money", professional participants, accumulating shares, absorbing supply and trapping participants on the opposite side. These are useful metaphors for picturing possible market dynamics, but a single volume bar cannot identify who the parties to the trades were, or whether one coordinated group was acting. Every trade has a buyer and a seller. High volume on a small spread shows activity and limited progress, not the names or intentions of participants.

All chart examples are illustrations. They are not a test with a complete set of decisions, orders, costs and losses. Categorical claims about increased effectiveness, the repeatability of the WFO or the behaviour of professionals should be distinguished from a definition that can be checked in data. This compendium does not assume that VSA is profitable and promises no results. Historical charts do not tell you how many similar setups failed or whether a rule works after costs in new periods.

Be especially careful about:

- choosing only the successful examples visible on the slides;
- changing a signal's definition after seeing the next candles;
- confusing correlation with causation and interpretation with measurement;
- carrying volume over from one instrument or feed to another;
- repeatedly flipping through many timeframes and thresholds until a favourable picture emerges;
- counting effectiveness only from trades that ended in profit;
- attributing every formation to "smart money" without data on the participants.

The course is valuable above all as a catalogue of questions to ask the chart: what was the effort, what was the result, how did price close, what happened before, and what did the market do next? These questions can be turned into a consistent and controllable procedure. The answer must, however, remain a hypothesis until it has been checked against data and execution.

## 12. Exercises for learning and validation

### Exercise A — describing a bar without interpretation

Pick 50 random bars from one instrument. For each, record: the spread relative to the previous 10 bars, Up/Down by close versus the previous close, the close position in the range, and volume relative to the two previous bars and to the latest local stretch. Do not write "accumulation", "distribution" or "smart money" yet. The aim is to learn to separate observation from narrative. Compare your own narrow/average/wide label with the numerical rule you decide to test formally.

### Exercise B — signal and context

For each signal in the catalogue, find several examples on the chart, including ones that ended contrary to expectations. Cover the future bars. Write down the definition, the background, the hypothesis, the condition for further confirmation and the invalidation. Only then reveal the future data. This shows whether the pattern's name really helps make decisions before the outcome, or only makes it easy to describe history after the fact.

### Exercise C — a test of supply as a sequence

Mark the earlier strength after a decline, the rebound, the retest area, the volume during the descent and the response that followed. Mark a test as successful only if it meets the definition adopted beforehand and a reaction appears. Count separately: all attempts, confirmed attempts and negated attempts. Do not leave out the cases where the test did not lead to a rise.

### Exercise D — auditing VSA in code

Prepare synthetic bars by hand: narrow spread + high volume; wide spread + low volume; an Up Bar with a red body; a Down Bar with a green body; volume lower than the two previous bars; a candle with H = L. Check that the code classifies features independently of body colour, computes the close position correctly and handles a zero range. Every generated signal should carry a reason in the form of source features, so that it can be audited.

### Exercise E — out of sample and costs

Define the rules before the study. Split the data chronologically into a design sample and a later validation period. Measure a baseline variant with no signal, then check whether the VSA filter improves the result after costs, in different phases and on instruments not used before. Report the distribution of results, not just the share of profitable trades. If the result depends on one threshold, one market or a few best examples, its stability is poor.

### Exercise F — a decision journal

For at least one full cycle of exercises, also record the decisions not to enter. Attach a chart screenshot from the moment of planning, the feed, the timeframe, the hypothesis, the invalidation level and the cost. Afterwards, assess separately: the quality of the hypothesis, the quality of execution and the result. A profitable trade may be procedurally wrong; a loss may be in line with the plan.

## 13. The main discrepancies between maps, narration and secondary documents

| Topic | What follows from the narration / current material | What a map or older document simplifies or gets wrong | How this compendium treats it |
|---|---|---|---|
| Transcript availability | Current TXT and SRT files exist for lessons 1–30 and 4 items of the 2018 course | An older write-up claims a transcript exists only for lesson 1; maps 2–30 repeat "no audio/transcript" | The available transcripts were taken as current; the older information was treated as out of date |
| Spread in lesson 1 | The definition from the map/slide and repeated statements: high–low | A single fragment of the transcript confuses spread with open–close | H−L adopted; the single O−C treated as a slip/speech-recognition error |
| High/low close boundary | The 2018 course speaks of an approximate third and warns against pharmacist's precision | The map draws 30/70% | 30/70 may be used as an explicit formalisation, not as a timeless course threshold |
| Bag Holding | Classic Down Bar; the instructor also allows an Up Bar given the right picture of range and volume | The old algorithm/map may suggest only one bar type | Both variants included; what matters is the narrow spread, exceptional volume and the reaction |
| Bag Holding — which bar has the highest volume | A spot check of the lesson 8 frame at 02:30 showed volume rising over three bars, peaking under the last small bar | The map left this uncertain, and the old description suggested the peak might be under the middle bar | The resolution from the single-frame check is given; watching the whole video is not claimed |
| Shakeout | The narration says the body may be green or red; a high close is what matters | The map draws a green body | Colour is not a condition |
| Inside Bar | The narration defines the first bar's range, the second bar entirely inside it and a breakout by the third; it shows moves in both directions | One map/strategy illustrates only a downside entry, while the definition map shows an upside breakout | The direction was not generalised from a single illustration; lesson 5 requires a breakout of the first bar's range |
| 2018 course map, lesson 2 | The narration speaks of an approximate third | The map suggests an exact 30/70 and may imply an automatic entry after a T | A test signal requires a reaction; an arrow alone does not confirm an order |
| 2018 course map, lesson 3 | The SRT names the 0.5 and 0.618 levels and distinguishes scenario no. 5 from a fifth wave | The map reads a handwritten note as 0.878 and interprets the "5" uncertainly | The narration takes precedence; the 0.878 reading was not used |
| Money management 2018 | The SRT discusses the SL, the 3:1 potential and fitting the stop to capital | The map suggests there are no money-management rules | The narration was used; its numbers are given as course examples |
| Falling sequences | The narration describes distribution, demand flooding and the test of demand with full category names | The "SZP" abbreviation in the maps is sometimes ambiguous | Full names used; no mapping of every signal to a class was invented |
| WFO | Lessons 25 and 26 describe the volume relation of the two extremes and the correction | The maps show the geometry, but the implementation of the extremes is not defined numerically | The volume-relation condition was kept; the method of detecting swings is marked as a formalisation |

In the 2018 lesson, map no. 4 claims that the question of the volume source appears in only one place in the whole material. The SRT of lesson 1, however, already has a statement about tick versus real volume at 01:15:10. Lesson 4 additionally distinguishes tick volume, exchange volume of real futures contracts and the "real" XTB volume named in the lecture, described as based on the real volume of the given security [K: 2018, lesson 4, SRT 00:34:30–00:39:12, including the rejection of tick volume at 00:35:53–00:36:29]. This is a historical explanation of the platform in use, not a promise that a similar source is currently available for every instrument. The map also omits the explicit remark that buy and sell volume in a trade are equal; the colour of the bar is not a measure of net buyers [K: 2018, lesson 4, SRT approx. 00:25:58].

All four maps of the 2018 course were made from the image; where details conflict, the corresponding SRT takes precedence as the narrative source.

## 14. Map of the source material: lessons 1–30 and the 2018 course

The table helps you get back to the source. The time points to a verified moment or fragment of the SRT, not the length of the whole lesson. For ranges described as "later on", use the SRT header and search for the topic named.

| Material | Topic and use in the compendium | Approximate SRT timestamp |
|---|---|---|
| Lesson 1 | VSA, spread, volume, close, background and how to read the chart | The relevant terms in the first part; spread H−L discussed at the start |
| Lesson 2 | Chart types, decision background, HLC/OHLC and bar configuration | Topics at the start of the lecture |
| Lesson 3 | Bullish candlestick formations: hammer, piercing line, morning star and bullish engulfing among others; emphasis on VSA as confirmation | Hammer 00:06–02:50; the other formations later on |
| Lesson 4 | Bearish formations: shooting star, evening star, dark cloud cover, bearish engulfing; volume as confirmation | Shooting star 00:06–02:04; the other formations from approx. 11:35 |
| Lesson 5 | Bar formations and entering on a breakout, including the Inside Bar | Definition of the breakout by the third bar approx. 01:46–03:53 |
| Lesson 6 | Bullish/bearish volume on waves and judging direction | 00:06–02:39 |
| Lesson 7 | Categories of VSA signals and where to expect them | 00:06–04:14 |
| Lesson 8 | Bag Holding and Selling Climax | Bag Holding 01:58–04:35; Selling Climax approx. 08:45–10:06 |
| Lesson 9 | Stopping Volume | 00:06–01:29 |
| Lesson 10 | Shakeout | 00:06–01:55 |
| Lesson 11 | Two Bar Reversal after a decline | 00:06–01:33 |
| Lesson 12 | No Supply | 00:06–01:19; testing examples later on |
| Lesson 13 | Test of supply and the condition of earlier strength | 00:06–02:07 |
| Lesson 14 | End of the Rising Market and Buying Climax | End of Rising Market 00:20–03:16; BC approx. 06:48–09:02 |
| Lesson 15 | Supply Coming In | 00:06–01:53; the caveat about not entering without a further signal approx. 03:13–04:06 |
| Lesson 16 | Trap Upmove | 00:06–02:14 |
| Lesson 17 | No Result From Effort | 00:06–01:04; examples from approx. 01:46 |
| Lesson 18 | Two Bar Reversal after a rise | 00:06–01:17 |
| Lesson 19 | No Demand | 00:06–01:08 |
| Lesson 20 | Upthrust and its volume variant | 00:06–00:47 |
| Lesson 21 | Testing supply as a process | 00:35–04:40 |
| Lesson 22 | VSA as confirmation of geometry | 00:06–03:57 |
| Lesson 23 | Rising sequences | 00:05–03:37 |
| Lesson 24 | Falling sequences | Introduction approx. 00:05; example setups approx. 01:25–02:40 |
| Lesson 25 | Bearish WFO | Volume-relation condition approx. 14:37; role in the scenario 05:47–06:12 |
| Lesson 26 | Bullish WFO | Second trough and volume 00:46–01:15; role of the formation 01:15–02:07; condition 09:20–09:34 |
| Lesson 27 | Kinds of correction | Correction on dying volume 00:54–01:15; sweep/flush 06:31–08:17 |
| Lesson 28 | Risk, capital, stop loss and management | Beginners/exposure 13:30–14:20; risk amount 15:55–16:58; management 35:48–37:34 |
| Lesson 29 | Scenario no. 5 and the decision from direction to position | Self-assessment 01:05–01:34; bias/scenario split 03:33–05:09; important place 12:38–14:22; conditions 16:04–18:04 |
| Lesson 30 | Market reactions to macro data | 00:14–01:39; example of a volume reaction from approx. 03:17 |
| 2018 course, lesson 1 | VSA basics, spread, real volume and bullish/bearish volume | 01:15:10; 01:18:01–01:21:38; example 01:25:35 |
| 2018 course, lesson 2 | Laws of the market, accumulation/distribution, background | 00:09:47–00:10:07; 00:12:58–00:19:03; 00:28:02 |
| 2018 course, lesson 3 | A complete scenario, geometry and risk | 01:00:40–01:03:40; 01:09:35–01:10:19 |
| 2018 course, lesson 4 | The signal as a point of focus within the process | 00:07:52; 00:34:29–00:39:12; 00:43:05–00:45:32 |

In the lesson 8 map, part of the signal's title is transcribed as "Back Holding"; the compendium standardises the spelling to Bag Holding. In several SRT files automatic speech recognition misspells English terms, e.g. Up Bar as "abbar", Down Bar as "dąbar", Two Bar Reversal phonetically, or No Result as "No Resort". The names in the text have been standardised without changing the substance of the description.

## 15. Glossary of abbreviations and distinctions

| Term | Meaning in this compendium |
|---|---|
| Bar | One unit of data for one interval; a candle or a bar depending on the chart |
| Spread | The bar's high minus its low, i.e. the full price range |
| Close high / close low | Where the close sits relative to the bar's range |
| Up Bar / Down Bar | Close higher/lower than the previous bar's close |
| Effort-result | Comparing relative volume with the price move and the close |
| Background | Direction, wave structure, earlier signals and position on the higher timeframe |
| Test of supply / demand | Price returning to an area to check whether that side is still exerting pressure |
| Accumulation / distribution | The course's interpretation of supply/demand possibly being taken over; not a direct reading of intentions |
| WFO | Volume reversal formation with two extremes, a correction and a volume relation |
| SL / stop loss | The planned exit level that limits a loss; the execution price may differ |
| R | The unit of a position's initial risk, used to compare results |

## Conclusion

The most faithful summary of VSA in these materials is a discipline of asking questions about price and volume: how far the market travelled, on what volume, where the bar closed, what happened before it and what response followed. Context and the subsequent reactions are as important as the name of the signal itself. If the process is formalised in Python, every setting the course leaves undefined should be disclosed as a design choice; this makes it possible to compare the program's output with the actual content of the method and to judge its limitations honestly.




## Appendix A. From describing the market to a Python program

### A.1. What is actually calculated

VSA has no single function whose output unambiguously decides "buy" or "sell". The supplied program is an **explicit, experimental formalisation** of selected observations from the course. It processes closed candles of one instrument and one timeframe. It computes price and volume features, marks candidates for named signals, records later confirmations and tests a simplified entry sequence.

The word `candidate` in the output means that the program's conditions were met. It proves neither the involvement of particular market participants nor the future direction of price. Several names can fit the same candle; they are not independent "votes" that increase the probability of success.

| Element of the method | Scope of the supplied program |
|---|---|
| Spread, body, wicks, close position, Up Bar/Down Bar | Calculated directly from OHLC. The bar's direction depends on the previous close. |
| Relative volume and relative spread | Measured against an earlier window; the current candle is not part of its own reference level. |
| Named signs of strength and weakness | Candidates according to explicit rules described in the program's instructions. Thresholds and window lengths are assumptions. |
| WFO in both directions | A simplification based on local extremes, the volume relation and delayed confirmation of the extreme. |
| Market background | An approximation on one timeframe, without a full assessment of the higher timeframe's structure. |
| Trading sequence | Earlier strength → No Supply/Test → confirmation, or earlier weakness → No Demand → confirmation. |
| Scenario no. 5, full ABC and Fibonacci geometry | Described in the compendium; not fully implemented by the back-test. |
| Trade management | One position at a time, a fixed stop and target, commission and slippage, a risk and notional limit. |
| Macro data, session calendar, contract roll-over, financing and automated orders | Not integrated. |

The detailed, binding conditions of each detector are in `python/README.md` and `python/engine.py`. If you change the configuration, you also change the strategy variant being studied. Do not call the results of different configurations the results of one unchanging method.

### A.2. Running it

You need Python 3.10 or newer. The engine itself does not require installing any packages with `pip`. Open a terminal in the `python` subfolder of the unpacked package and run:

```text
python vsa.py --input sample_ohlcv.csv --output results
```

On Windows you can replace `python` with `py -3`. The example contains **synthetic data** prepared to demonstrate how it works. Its financial result is not a measurement of effectiveness in the market.

Prepare your own data as a CSV with a header:

```text
timestamp,open,high,low,close,volume
2026-01-01T10:00:00Z,100,102,99,101,1500
2026-01-01T10:05:00Z,101,103,100,102,1300
```

This only illustrates the format; two candles are not enough to warm up the model. Use a decimal point, a comma as the separator, one time zone and increasing, non-repeating timestamps. Choose one convention for labelling candles — their start or their end — and apply it consistently across the whole dataset. The calculations assume that all of a candle's values are known only after it closes. Naive timestamps without a zone are treated by the loader as UTC, so it is best to pass an explicit `Z` or a zone offset.

The dataset should contain one instrument and one timeframe. Do not splice a futures contract's volume onto another instrument's price, or data from different providers, without explicit synchronisation and a justification. The file must not contain an unfinished last candle. Prices must be positive, volume non-negative, and High and Low must enclose Open and Close. The model does not support instruments with zero or negative prices.

### A.3. How to read the output

`signals.csv` is for candle-by-candle auditing: it contains the input data, features, candidates and confirmation events. `trades.csv` describes the simulated trades. `equity.csv` shows the course of capital, including the valuation of an open position. `summary.json` is a summary of the results. The program's instructions list the exact files and columns.

Distinguish three moments:

1. **The candidate candle:** only its close reveals the full High, Low, Close and Volume.
2. **The confirmation candle:** a later reaction that could not have been known before. The WFO has an additional delay due to recognising local extremes.
3. **Execution:** in the back-test it happens at the earliest at the open of the next candle after confirmation.

Confirmation in the implementation is more mechanical than the instructor's observation: the README gives the full rules. Touching a level and closing beyond it are not the same thing. The model does not pretend to know, from OHLC alone, the order of every move within a candle. When, after entry, the stop and the target both fall within the range of the same candle, it assumes the stop was executed first. This is a conservative assumption, not a reconstruction of the actual price path.

### A.4. Risk and units

The planned risk amount is a fraction of capital. The position size depends on the distance from entry to the stop, costs and the notional limit. A target set as a multiple of the distance to the stop does not mean the market really has that potential: the program does not examine all the resistance, support or liquidity on the way to the target. This is a particularly important difference from assessing the potential in the course's scenario no. 5.

The basic model uses instrument units for which a price move of 1 changes the value by 1 per unit, in the capital currency. Do not substitute a number of futures contracts, FX lots or instruments with a different multiplier without converting. A fractional number of units in the simulation may not be allowed by a particular broker. In such use, the point value, the quote currency, the minimum position step and the margin have to be taken into account.

A stop is a level that triggers an exit, not a guarantee of the loss amount. A gap through the stop can increase the loss beyond the planned budget. This difference is also explained in [FINRA on the risk of stop orders](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets). In the model, commission is charged on both sides of the trade; the README gives the details of how the target and slippage are executed.

Drawdown is measured on successive candle closes, after the modelled exits. It is not the exact maximum drawdown within a candle. For an open position the valuation includes the estimated cost of closing it; it is not yet a realised trade. A fixed commission and slippage do not model the full variability of the bid-ask spread, position financing, order queues or the impact of one's own order on price.

### A.5. What the program's tests prove

Unit tests check the logic and calculations on controlled examples. The causality test compares the output on a prefix of the series with the same part of the output for the whole history: adding later candles must not change earlier features or earlier analytical events. Trade execution metadata and final statistics should be judged separately, because they appear later.

Passing the tests is not proof of an investment edge. Judging that requires a time-separated test set with real data, realistic costs and control over the number of variants tried. The package contains no real market data and no claim that the strategy makes money.

A reasonable experiment consists of freezing the configuration after a training period, checking the following period without changes, repeating the process over successive windows, and comparing the results with a simple benchmark. Report the number of trades, the net result, drawdown, the distribution of gains and losses, and sensitivity to costs. A chart of a few successful examples is not enough on its own.

### A.6. Provenance and reproducibility

The package contains an inventory, `zrodla_manifest.json`, with the names, sizes and SHA-256 hashes of the text materials. The inventory also covers copies; its presence does not mean the copies are independent sources. The recordings remain in the original folder. During the work, individual frames were spot-checked: lesson 8 at 02:30, lesson 25 at 03:30 and lesson 26 at 01:00. The videos were not all re-watched from start to finish.

Keep the input file, the configuration, the code version and the run date with every back-test of your own. A result without these elements is not enough to repeat the experiment.
