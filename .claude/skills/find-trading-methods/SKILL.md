---
name: find-trading-methods
description: >-
  Research and present PROVEN, volume-based, medium-term, LONG-ONLY (bullish)
  trading methods from sources with verifiable track records — this is a
  research report ONLY; it must NEVER write code, scripts, or change the app.
  Use whenever the user wants to find, discover, or research trading methods,
  strategies, setups, or "trades" — especially ones built on volume /
  relative-volume, held over days-to-months (swing/position, not intraday and
  not buy-and-hold-forever), and designed to profit from RISING prices (no
  shorting / no bearish setups). For every method it always names the source
  (author / book / paper / site + link) and shows a few REAL historical examples
  with EXACT dates on real market data. Trigger on "find me good trading
  methods", "search for volume-based strategies", "what swing setups actually
  work", "show me bullish setups with real examples and dates", or a bare "find
  me some good trades" — even when the user doesn't name a specific method. Do
  NOT use this to write, build, or scaffold a scanner or any code.
---

# Find proven trading methods (research only)

## Scope — read this first

This skill **only researches and reports**. It produces a written answer: a set
of vetted trading methods, each with its source and real dated examples.

**It must never:** write code or scripts, create/edit files in the app, build a
scanner, add an endpoint or a page, run a backtest script, or query the
database. If the user later wants one of these methods turned into an actual
scanner in the app, that is a **separate** task — say so and stop here. The
value of this skill is the research and the honesty of the evidence, not code.

## What every method must be (all three, or reject it)

The user trades a specific way — filter hard to it. A method qualifies only if
it satisfies **all three**:

1. **Volume-based.** Volume (or relative volume / effort-vs-result) is *central*
   to the entry signal, not a footnote. This app is built on Volume Spread
   Analysis, so pure price-only methods with no volume logic don't fit.
2. **Medium-term.** The intended holding period is roughly **days to a few
   months** — swing or position trading. Exclude intraday/scalping (needs data
   the owner doesn't have and isn't how he trades) and exclude pure
   buy-and-hold-for-a-decade.
3. **Long-only / bullish.** Entries that profit when the price **rises**. The
   owner explicitly does **not** short. Drop any method whose edge is selling
   short, fading rallies, or betting on declines. (A method may still *exit* to
   cash on weakness — that's fine; what's excluded is profiting from the fall.)

If a promising method is close but fails one test (e.g. it's a great volume
setup but intraday), say so and offer the nearest qualifying cousin rather than
bending the criteria.

## Where to look and how to vet

Use `WebSearch` / `WebFetch` to pull the actual rules, the source, and dated
examples. Follow the **Sourcing** and **Vetting** guidance in the repo's
playbook, `agent/TRADING-METHODS-RESEARCH.md` — but **ignore its "From method →
scanner / build" section**, which is out of scope here.

Strong candidates that already match volume + medium-term + bullish are
catalogued in **`references/method-shortlist.md`** — start there, then confirm
each with live sources and real examples. Don't treat the shortlist as the final
answer; it's a head start, and the user may want methods beyond it.

Prefer **durable, evidence-backed** sources over course-selling gurus: trading
books that codify the method, academic/factor research, and platforms with
verified track records. For each candidate quickly vet: multi-year record across
*both* bull and bear markets, risk-adjusted (drawdown, not just headline %),
many trades, transparent about losers, author earns from trading not from
selling the system. Red flags: "guaranteed", no drawdown shown, only recent
months, an upsell funnel.

## Sources are mandatory

Every method **and every example** must carry its source, so the owner can check
it himself:
- **For the method:** author + book/paper/site and a link where possible (e.g.
  "Gil Morales & Chris Kacher, *Trade Like a Market Wizard*; virtueof
  selfishinvesting.com").
- **For each example:** where the dated instance comes from — either the source
  material's own case study, or the real price/volume data you inspected (name
  the data source, e.g. stooq.pl / Yahoo Finance, and the ticker + date).

## Real examples with exact dates (the core deliverable)

For each method, show **2–3 concrete instances where the setup actually
occurred on real data**, each with an **exact date** (`YYYY-MM-DD`). This is what
turns an abstract rule into something believable.

Rules for examples — these protect the owner from being misled:
- **Never invent** a ticker, a date, a volume figure, or an outcome. A fabricated
  example is worse than none. If you cannot find or verify a real dated example,
  say "no verified example found" for that method — that is an acceptable,
  honest result.
- **Give the exact date** of the signal bar, the market/ticker, what made it a
  valid setup (e.g. "volume ~3× the 50-day average on the breakout above the
  base"), and the **medium-term outcome that followed** (e.g. "+18% over the next
  6 weeks, by 2024-03-15") — because the method is bullish and medium-term, the
  example should show a *rise over that horizon*, or honestly note when it failed.
- **Label the evidence:** mark whether an example is (a) documented in the source
  itself, or (b) one you verified by looking at real historical price/volume via
  the web. Both are fine; conflating them is not.
- **Prefer GPW (Warsaw) examples** when you can verify them on real data, since
  that's the app's market — but a well-sourced example from any market is
  acceptable and better than a shaky GPW one. Do this by *reading* real data
  through web tools, **not** by writing a script.

## Output format

Present a short intro, then one block per method using this template:

```
## <Method name>
**Source:** <author, book/paper/site + link>. <one line: why it's credible / its track record>
**Fits because:** volume — <why volume is central>; medium-term — <typical hold>; bullish — <why it's a long/up setup>
**The setup (in plain language):** <the volume condition> + <the price/trend condition> → entry. Typical exit/stop: <…>.
**Real examples (real data, exact dates):**
  1. <TICKER> (<market>) — signal on <YYYY-MM-DD>: <volume vs its average, price/base context>. Outcome: <+X% by YYYY-MM-DD> (medium-term). Evidence: <documented in source | verified on stooq/Yahoo>, <link>.
  2. <…second example…>
**Watch-outs:** <where it fails — e.g. earnings gaps, choppy markets, false breakouts>
```

Close with a one-paragraph summary: which method looks strongest for a
volume-based, medium-term, long-only trader on the GPW, and why — as an
observation, not personalized investment advice.

## Defaults & honesty

- Default to **3–5 methods** unless the user asks for more or fewer.
- Keep the language plain — the owner is not a coder or a quant.
- This is educational research into published methods, **not** personalized
  investment advice, and past performance never guarantees future results. State
  that once, briefly, and don't nag.
- If the evidence for a "proven" method turns out to be thin or marketing-driven,
  say so and drop it. A shorter, honest list beats a padded one.
