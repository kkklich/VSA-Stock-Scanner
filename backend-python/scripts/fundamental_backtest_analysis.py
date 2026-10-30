"""Annual-report sensitivity study, explicitly separate from a causal PIT backtest."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean, median
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.analysis import fundamentals as production
from app.markets import below_liquidity_floor, below_market_cap_floor, get_market
from app.models.stocks import GpwCompany
from app.services.fundamental_data import extract_fundamental_details, finite
from scripts.fundamental_backtest import ROOT, SCHEMA, cache_path, save


def frame(raw):
    if not raw or not raw.get("data"):
        return pd.DataFrame()
    result = pd.DataFrame(raw["data"], index=raw["index"], columns=raw["columns"])
    result.columns = pd.to_datetime(result.columns)
    return result.sort_index(axis=1, ascending=False)


def prices(raw, market):
    if not raw or not raw.get("data"):
        return pd.DataFrame()
    result = pd.DataFrame(raw["data"], index=raw["index"], columns=raw["columns"])
    result.index = pd.Index(
        pd.to_datetime(result.index, utc=True).tz_convert(get_market(market).tz).date
    )
    result = result[~result.index.duplicated(keep="last")].sort_index()
    for key in ("Open", "Close", "Adj Close", "Volume"):
        if key not in result:
            result[key] = np.nan
    result = result[(result.Close > 0) & (result.Open > 0) & (result["Adj Close"] > 0)]
    result["Adjusted Open"] = result.Open * result["Adj Close"] / result.Close
    return result


def val(table, column, *keys):
    if column is None or column not in table.columns:
        return None
    for key in keys:
        if key in table.index and (value := finite(table.at[key, column])) is not None:
            return value
    return None


def ratio(a, b):
    if a is None or b is None or b <= 0:
        return None
    return finite(a / b)


def matching_previous(columns, latest):
    return next((d for d in columns if 330 <= (latest - d).days <= 400), None)


def reconstruct(company, raw, formation: date, lag: int):
    """Never substitute current Yahoo ratios for historical ones.

    These are actual historical ANNUAL statement values, with an ASSUMED lag;
    annual inputs replace quarterly/TTM definitions and may be restated.
    """
    corporate = company["profile"] == "corporate"
    pillars = production.PILLARS if corporate else production.FINANCIAL_PILLARS
    inputs = dict.fromkeys(k for keys in pillars.values() for k in keys)
    item = {
        "ticker": company["ticker"],
        "market": company["market"],
        "name": company["name"],
        "profile": company["profile"],
        "formation": formation.isoformat(),
        "lag_days": lag,
        "fiscal_end": None,
        "excluded": [],
        "inputs": inputs,
    }
    daily = raw["daily"]
    if daily.empty:
        item["excluded"].append("prices_missing")
        return item
    history = daily.loc[daily.index <= formation]
    if len(history) < 20 or (formation - history.index[-1]).days > 7:
        item["excluded"].append("prices_stale_or_short")
        return item
    close = float(history.Close.iloc[-1])
    item["price_date"] = history.index[-1].isoformat()
    item["formation_close"] = close
    turnover = float((history.Close.iloc[-20:] * history.Volume.iloc[-20:]).median())
    try:
        if below_liquidity_floor(turnover, company["currency"]):
            item["excluded"].append("liquidity")
    except ValueError:
        item["excluded"].append("quote_currency_unknown")

    cutoff = formation - timedelta(days=lag)
    income, balance, cashflow = raw["income"], raw["balance"], raw["cashflow"]
    income = income.loc[:, [c for c in income.columns if c.date() <= cutoff]]
    # Some Yahoo columns exist but contain no usable statement; reject them.
    dates = [c for c in income.columns if val(income, c, "Total Revenue", "Net Income") is not None]
    if not dates:
        item["excluded"].append("annual_report_missing")
        return item
    latest = max(dates)
    item["fiscal_end"] = latest.date().isoformat()
    item["assumed_available"] = (latest.date() + timedelta(days=lag)).isoformat()
    if (formation - latest.date()).days > 550:
        item["excluded"].append("annual_report_stale")
        return item
    previous = matching_previous(income.columns, latest)
    revenue = val(income, latest, "Total Revenue")
    profit = val(income, latest, "Net Income Common Stockholders", "Net Income")
    eps = val(income, latest, "Diluted EPS", "Basic EPS")
    shares = val(income, latest, "Diluted Average Shares", "Basic Average Shares")
    if shares is None and profit is not None and eps not in (None, 0):
        shares = ratio(profit, eps) if eps > 0 else finite(profit / eps)
    cap = close * shares if shares is not None and shares > 0 else None
    item["market_cap_proxy"] = cap
    # Currency metadata is current; it is an explicit unit assumption, not a PIT fact.
    major = "GBP" if company["currency"] == "GBp" else company["currency"]
    units_match = company.get("financial_currency") == major
    if not units_match:
        cap = None
        item["excluded"].append("reporting_currency_mismatch_or_unknown")
    try:
        if cap is None or below_market_cap_floor(cap, company["currency"]):
            item["excluded"].append("market_cap_unavailable_or_small")
    except ValueError:
        item["excluded"].append("quote_currency_unknown")

    equity = val(balance, latest, "Stockholders Equity", "Common Stock Equity")
    old_equity = val(balance, previous, "Stockholders Equity", "Common Stock Equity")
    assets = val(balance, latest, "Total Assets")
    old_assets = val(balance, previous, "Total Assets")
    inputs["roe"] = (
        ratio(profit, (equity + old_equity) / 2)
        if (equity is not None and old_equity is not None and equity > 0 and old_equity > 0)
        else None
    )
    inputs["roa"] = (
        ratio(profit, (assets + old_assets) / 2)
        if (assets is not None and old_assets is not None and assets > 0 and old_assets > 0)
        else None
    )
    loss = (profit is not None and profit <= 0) or (eps is not None and eps <= 0)
    inputs["earningsYield"] = 0.0 if loss else ratio(eps, close) if units_match else None
    if previous is not None:
        for name, keys in (
            ("revenueGrowthYoy", ("Total Revenue",)),
            ("epsGrowthYoy", ("Diluted EPS", "Basic EPS")),
        ):
            growth = ratio(val(income, latest, *keys), val(income, previous, *keys))
            inputs[name] = growth - 1 if growth is not None else None

    annual = extract_fundamental_details({}, income, balance, today=formation)
    inputs["revenueCagr3y"] = annual.revenue_cagr_3y
    inputs["epsCagr3y"] = annual.eps_cagr_3y
    if not corporate:
        inputs["bookYield"] = ratio(equity, cap) if equity is not None and equity > 0 else None
        return item
    operating = val(income, latest, "Operating Income")
    ebitda = val(income, latest, "EBITDA", "Normalized EBITDA")
    debt = val(balance, latest, "Total Debt")
    cash = val(
        balance,
        latest,
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
    )
    ocf = val(cashflow, latest, "Operating Cash Flow")
    fcf = val(cashflow, latest, "Free Cash Flow")
    capex = val(cashflow, latest, "Capital Expenditure", "Purchase Of PPE")
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf - abs(capex)
    inputs["netMargin"], inputs["operatingMargin"] = (
        ratio(profit, revenue),
        ratio(operating, revenue),
    )
    inputs["roic"] = annual.return_on_invested_capital
    inputs["marginVolatility"] = annual.operating_margin_volatility
    inputs["fcfMargin"], inputs["ocfMargin"] = ratio(fcf, revenue), ratio(ocf, revenue)
    inputs["cashConversion"] = ratio(ocf, profit)
    inputs["fcfYield"] = ratio(fcf, cap)
    inputs["interestCoverage"] = annual.interest_coverage
    inputs["netDebtToEbitda"] = (
        ratio(debt - cash, ebitda)
        if (debt is not None and debt >= 0 and cash is not None and cash >= 0)
        else None
    )
    enterprise_value = cap + debt - cash if None not in (cap, debt, cash) else None
    inputs["ebitdaYield"] = ratio(ebitda, enterprise_value)
    if ebitda is not None and ebitda <= 0:
        inputs["ebitdaYield"], inputs["netDebtToEbitda"] = 0.0, None
    return item


def rank_reconstructed(items, companies, formation):
    """Inject annual raw inputs at the evidence boundary, reuse the exact scorer.

    The production file and weights are untouched. No synthetic quarterly
    statements, acquisition dates or earnings publication dates are fabricated.
    This research process never serves application requests.
    """
    models = [GpwCompany.model_validate(c) for c in companies]
    evidence = {
        r["ticker"]: production._Evidence(
            company=m,
            profile=r["profile"],
            inputs=r["inputs"],
            excluded=r["excluded"],
            latest=date.fromisoformat(r["fiscal_end"]) if r["fiscal_end"] else None,
        )
        for r, m in zip(items, models, strict=True)
    }
    with patch.object(production, "_evidence", side_effect=lambda c, *_: evidence[c.ticker]):
        return production.assess_fundamentals(models, {}, as_of=formation, exclusions={})


def forward_return(daily, formation, months, cost_bps):
    following = daily[(daily.index > formation) & (daily.Volume > 0)]
    if following.empty:
        return {"status": "entry_missing"}
    entry_date = following.index[0]
    if (entry_date - formation).days > 7:
        return {"status": "entry_gap"}
    target = (pd.Timestamp(entry_date) + pd.DateOffset(months=months)).date()
    if target > daily.index[-1]:
        return {"status": "not_mature"}
    exit_rows = daily[(daily.index >= target) & (daily.Volume > 0)]
    if exit_rows.empty or (exit_rows.index[0] - target).days > 7:
        return {"status": "exit_missing_or_gap"}
    entry = float(following["Adjusted Open"].iloc[0])
    exit_price = float(exit_rows["Adj Close"].iloc[0])
    fee = cost_bps / 10_000
    return {
        "status": "evaluated",
        "entry_date": entry_date.isoformat(),
        "exit_date": exit_rows.index[0].isoformat(),
        "return_gross_pct": 100 * (exit_price / entry - 1),
        "return_net_pct": 100 * (exit_price * (1 - fee) / (entry * (1 + fee)) - 1),
    }


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_groups(scored, spec):
    returns, cohort_details, censoring = [], [], Counter()
    for (market, profile, formation, lag), group in scored.items():
        for metric in ["overall", *production.PILLARS]:
            available = [r for r in group if r["scores"].get(metric) is not None]
            if len(available) < 8:
                continue
            values = [r["scores"][metric] for r in available]
            low, high = map(float, np.quantile(values, [0.25, 0.75]))
            if low >= high:
                continue  # No arbitrary ticker tie-break creates a fake signal.
            for months in spec["horizons_months"]:
                observed = []
                for row in available:
                    outcome = row["forward"][months]
                    censoring[(market, profile, metric, months, lag, outcome["status"])] += 1
                    if outcome["status"] != "evaluated":
                        continue
                    observed.append((row, outcome))
                if not observed:
                    continue
                baseline = mean(out["return_net_pct"] for _, out in observed)
                counts = Counter()
                for row, outcome in observed:
                    value = row["scores"][metric]
                    memberships = ["all"]
                    if value >= high:
                        memberships.append("top_quartile")
                    if value <= low:
                        memberships.append("bottom_quartile")
                    if value >= 70:
                        memberships.append("score_ge70")
                    if value <= 30:
                        memberships.append("score_le30")
                    for membership in memberships:
                        counts[membership] += 1
                        returns.append(
                            {
                                "market": market,
                                "profile": profile,
                                "formation": formation,
                                "lag_days": lag,
                                "months": months,
                                "metric": metric,
                                "group": membership,
                                "ticker": row["ticker"],
                                "score": value,
                                **outcome,
                                "benchmark_net_pct": baseline,
                                "excess_pp": outcome["return_net_pct"] - baseline,
                            }
                        )
                cohort_details.append(
                    {
                        "market": market,
                        "profile": profile,
                        "formation": formation,
                        "lag_days": lag,
                        "months": months,
                        "metric": metric,
                        "score_coverage": len(available),
                        "evaluated": len(observed),
                        "benchmark_net_pct": baseline,
                        "q25": low,
                        "q75": high,
                        **counts,
                    }
                )
    return (
        returns,
        cohort_details,
        [
            {
                "market": k[0],
                "profile": k[1],
                "metric": k[2],
                "months": k[3],
                "lag_days": k[4],
                "status": k[5],
                "n": n,
            }
            for k, n in censoring.items()
        ],
    )


def summarize(rows):
    grouped = defaultdict(list)
    keys = ("market", "profile", "lag_days", "months", "metric", "group")
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    result = []
    for key, values in sorted(grouped.items()):
        returns = [v["return_net_pct"] for v in values]
        result.append(
            {
                **dict(zip(keys, key, strict=True)),
                "observations": len(values),
                "companies": len({v["ticker"] for v in values}),
                "cohorts": len({v["formation"] for v in values}),
                "mean_net_pct": mean(returns),
                "median_net_pct": median(returns),
                "up_pct": 100 * mean(r > 0 for r in returns),
                "mean_excess_pp": mean(v["excess_pp"] for v in values),
                "beat_sample_pct": 100 * mean(v["excess_pp"] > 0 for v in values),
            }
        )
    return result


def uncertainty(rows, spec):
    """Stock-block AND formation-cohort resampling; very few years remain a limit."""
    rng = np.random.default_rng(spec["bootstrap_seed"])
    output = []
    selected = [
        r
        for r in rows
        if r["profile"] == "corporate"
        and r["metric"] == "overall"
        and r["lag_days"] == 180
        and r["group"] in ("top_quartile", "bottom_quartile")
    ]
    for market in spec["markets"]:
        for months in spec["horizons_months"]:
            subset = [r for r in selected if r["market"] == market and r["months"] == months]
            top = [r for r in subset if r["group"] == "top_quartile"]
            bottom = [r for r in subset if r["group"] == "bottom_quartile"]
            if not top or not bottom:
                continue
            actual = mean(r["return_net_pct"] for r in top) - mean(
                r["return_net_pct"] for r in bottom
            )
            tickers = sorted({r["ticker"] for r in subset})
            cohorts = sorted({r["formation"] for r in subset})
            out = {
                "market": market,
                "months": months,
                "top_minus_bottom_pp": actual,
                "companies": len(tickers),
                "cohorts": len(cohorts),
                "ci95_low": None,
                "ci95_high": None,
            }
            if len(cohorts) >= 2 and len(top) >= 10 and len(bottom) >= 10:
                stock_index = {v: i for i, v in enumerate(tickers)}
                time_index = {v: i for i, v in enumerate(cohorts)}
                t_idx = np.array([stock_index[r["ticker"]] for r in subset])
                c_idx = np.array([time_index[r["formation"]] for r in subset])
                value = np.array([r["return_net_pct"] for r in subset])
                is_top = np.array([r["group"] == "top_quartile" for r in subset])
                samples = []
                for _ in range(spec["bootstrap_replicates"]):
                    sw = rng.multinomial(len(tickers), np.full(len(tickers), 1 / len(tickers)))
                    cw = rng.multinomial(len(cohorts), np.full(len(cohorts), 1 / len(cohorts)))
                    weights = sw[t_idx] * cw[c_idx]
                    if weights[is_top].sum() and weights[~is_top].sum():
                        samples.append(
                            np.average(value[is_top], weights=weights[is_top])
                            - np.average(value[~is_top], weights=weights[~is_top])
                        )
                if samples:
                    out["ci95_low"], out["ci95_high"] = map(
                        float, np.quantile(samples, [0.025, 0.975])
                    )
            output.append(out)
    return output


def html_table(rows, columns):
    labels = {
        "market": "Rynek",
        "months": "Miesiące",
        "group": "Grupa",
        "observations": "Spółka–roczniki",
        "companies": "Spółki",
        "cohorts": "Roczniki",
        "mean_net_pct": "Średnio netto %",
        "median_net_pct": "Mediana netto %",
        "up_pct": "Udział wzrostów %",
        "mean_excess_pp": "Ponad próbę p.p.",
        "top_minus_bottom_pp": "Mocne − słabe p.p.",
        "ci95_low": "Przedział: dół",
        "ci95_high": "Przedział: góra",
        "metric": "Obszar",
        "lag_days": "Założony lag",
        "selected": "Wybrano",
        "downloaded_prices": "Ceny",
        "annual_statements": "Raporty",
        "scored_companies": "Spółki z pełną oceną",
        "evaluated_12m": "Spółki z wynikiem 12 mies.",
        "corporate_evaluated_12m": "Operacyjne: wynik 12 mies.",
    }
    names = {
        "us": "USA",
        "fr": "Francja",
        "gpw": "Polska",
        "all": "Cała oceniona próba",
        "top_quartile": "Górne 25%",
        "bottom_quartile": "Dolne 25%",
        "score_ge70": "Ocena ≥70",
        "score_le30": "Ocena ≤30",
        "profitability": "Rentowność",
        "growth": "Wzrost",
        "cashflow": "Gotówka",
        "debt": "Zadłużenie",
        "valuation": "Wycena",
    }

    def cell(value):
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.2f}"
        return html.escape(str(names.get(str(value), value)))

    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join(f"<th>{html.escape(labels.get(c, c))}</th>" for c in columns)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{cell(r.get(c))}</td>" for c in columns) + "</tr>" for r in rows
        )
        + "</tbody></table></div>"
    )


def report(out, spec, coverage, summary, intervals, cohorts):
    primary = [
        r
        for r in summary
        if r["profile"] == "corporate"
        and r["lag_days"] == 180
        and r["months"] == 12
        and r["metric"] == "overall"
    ]
    primary = sorted(
        primary,
        key=lambda r: (
            spec["markets"].index(r["market"]),
            ["top_quartile", "bottom_quartile", "all", "score_ge70", "score_le30"].index(
                r["group"]
            ),
        ),
    )
    pillars = [
        r
        for r in summary
        if r["profile"] == "corporate"
        and r["lag_days"] == 180
        and r["months"] == 12
        and r["metric"] != "overall"
        and r["group"] in ("top_quartile", "bottom_quartile")
    ]
    sensitivity = [
        r
        for r in summary
        if r["profile"] == "corporate"
        and r["months"] == 12
        and r["metric"] == "overall"
        and r["group"] in ("top_quartile", "bottom_quartile")
    ]
    cols = [
        "market",
        "group",
        "observations",
        "companies",
        "cohorts",
        "mean_net_pct",
        "median_net_pct",
        "up_pct",
        "mean_excess_pp",
    ]
    coverage_table = html_table(
        coverage,
        [
            "market",
            "selected",
            "downloaded_prices",
            "annual_statements",
            "scored_companies",
            "evaluated_12m",
            "corporate_evaluated_12m",
        ],
    )
    intervals_table = html_table(
        intervals,
        [
            "market",
            "months",
            "top_minus_bottom_pp",
            "companies",
            "cohorts",
            "ci95_low",
            "ci95_high",
        ],
    )
    pillars_table = html_table(
        pillars,
        [
            "market",
            "metric",
            "group",
            "observations",
            "companies",
            "mean_net_pct",
            "median_net_pct",
            "up_pct",
            "mean_excess_pp",
        ],
    )
    sensitivity_table = html_table(
        sensitivity,
        [
            "market",
            "lag_days",
            "group",
            "observations",
            "companies",
            "mean_net_pct",
            "up_pct",
            "mean_excess_pp",
        ],
    )
    cfa_url = (
        "https://www.cfainstitute.org/insights/professional-learning/"
        "refresher-readings/2026/backtesting-and-simulation"
    )
    sec_url = "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
    source_url = "https://ranaroussi.github.io/yfinance/reference/yfinance.financials.html"
    names = {"us": "USA", "fr": "Francja", "gpw": "Polska"}
    findings = "; ".join(
        f"{names[r['market']]}: {r['top_minus_bottom_pp']:+.2f} p.p."
        for r in intervals
        if r["months"] == 12
    )
    body = f"""<!doctype html><html lang="pl"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Badanie filtrów fundamentalnych — USA, Francja i Polska</title>
    <style>body{{font:16px/1.6 system-ui;margin:0;background:#f5f6fa;color:#182234}}
    main{{max-width:1240px;margin:auto;padding:40px 24px}}h1{{font-size:34px;line-height:1.2}}
    h2{{margin-top:36px}}.note{{padding:20px;border-left:5px solid #c67c11;background:#fff3d9}}
    .scroll{{overflow:auto;background:white;border-radius:10px}}
    table{{border-collapse:collapse;width:100%;font-size:13px}}
    th,td{{padding:10px 12px;text-align:right;border-bottom:1px solid #e3e7ee;white-space:nowrap}}
    th:first-child,td:first-child{{text-align:left}}th{{background:#eaf0f7}}code{{font-size:13px}}
    a{{color:#174f9b}}small{{color:#526078}}img{{width:100%;max-width:1100px}}</style><main>
    <small>StockPilot · dane pobrane 30.10.2026 · specyfikacja zamrożona przed pełną analizą</small>
    <h1>Czy filtry fundamentalne oddzielają spółki rosnące od spadających?</h1>
    <div class="note"><strong>To test eksploracyjny danych rocznych,
    nie potwierdzenie skuteczności nowego modelu.</strong>
    Archiwum ocen aplikacji zaczyna się 22.10.2026. Nie ma zatem ani jednego dojrzałego wyniku
    6–36 miesięcy po rzeczywistym zapisaniu nowej oceny. Dalsze tabele pokazują rekonstrukcję
    z historycznych raportów rocznych pobranych dzisiaj, z założeniem publikacji po 180 dniach.
    Prawdziwe terminy publikacji i pierwotne wersje raportów nie są dostępne w tym zbiorze.</div>
    <h2>Najważniejszy wynik</h2>
    <p><strong>Wyższa ocena nie dawała spójnej przewagi na trzech rynkach.</strong>
    Różnica średnich zwrotów górnego i dolnego kwartyla po 12 miesiącach: {findings}.
    Wszystkie opisowe przedziały niepewności dla tych różnic obejmują zero.</p>
    <h2>Zakres danych</h2>{coverage_table}
    <p>Próba pochodzi z dzisiejszej listy spółek aplikacji. Dobór: naprzemiennie sektory, w sektorze
    największe dzisiejsze kapitalizacje. Obejmuje firmy, które przetrwały do dziś; nie odtwarza
    dawnych składów indeksów ani upadłych i wycofanych spółek.</p>
    <h2>Główny wynik: 12 miesięcy</h2>{html_table(primary, cols)}
    <p>„Wzrost” oznacza dodatnią stopę zwrotu po kosztach. Wyniki uwzględniają korektę o dywidendy
    i splity dostawcy. „Ponad próbę” oznacza różnicę względem równo ważonych spółek z dostępną
    pełną oceną w tym samym rynku, profilu i roczniku — nie względem indeksu giełdowego.</p>
    <img src="comparison.png" alt="Zwroty po 12 miesiącach: mocne i słabe oceny na trzech rynkach">
    <h2>Różnica mocne minus słabe w różnych horyzontach</h2>
    {intervals_table}
    <p>Przedziały są opisowym bootstrapem blokowym spółek i roczników (2000 losowań), nie dowodem
    przyczynowym. Brak przedziału oznacza zbyt mało roczników lub obserwacji. Kilka lat oraz
    nakładające się okresy 24–36 miesięcy mocno ograniczają ocenę niepewności.</p>
    <p>Dla pełnej oceny są tylko dwa dojrzałe roczniki 12-miesięczne (wejścia 2024 i 2025),
    jeden 24-miesięczny (wejścia 2024) i brak dojrzałych obserwacji 36-miesięcznych.
    Dodatkowe wyniki 36 miesięcy dla pojedynczych obszarów nie są testem pełnej oceny.</p>
    <h2>Poszczególne obszary — 12 miesięcy</h2>
    {pillars_table}
    <p>To wyniki dodatkowe, liczne porównania bez korekty na wielokrotne testowanie. Nie wybierano
    na ich podstawie wag ani progów w aplikacji.</p>
    <h2>Wrażliwość na założoną datę dostępności raportu</h2>
    {sensitivity_table}
    <h2>Co dokładnie przetestowano</h2><ul>
    <li>Daty oceny: 30 czerwca 2023, 2024, 2025 i 2026. Raport musi kończyć się co najmniej
    180 dni przed oceną; wariant kontrolny: 270 dni. Roczny raport starszy niż 550 dni odpada.</li>
    <li>Oryginalne reguły punktacji aplikacji: percentyle w ramach tego samego rynku i profilu,
    preferencja sektora, minimum 5 spółek na wskaźnik i równe wagi właściwych obszarów.
    Górny i dolny kwartyl wyznaczono przed sprawdzeniem przyszłych zwrotów.</li>
    <li>Roczne dane zastępują kwartalne tempo wzrostu i TTM przepływów. To inny wariant wejść.
    Nie tworzono fikcyjnych kwartałów ani fikcyjnych historycznych zapisów w bazie aplikacji.</li>
    <li>Historyczna kapitalizacja jest przybliżeniem z kursu i rocznej średniej rozwodnionej
    liczby akcji. Dane o liczbie akcji i EPS mogą być przeliczone później po splitach.</li>
    <li>Zakup na pierwszym dostępnym otwarciu po dacie oceny; wyjście na pierwszym zamknięciu
    po 6/12/24/36 miesiącach od wejścia. Koszt 0,25% przy wejściu i 0,25% przy wyjściu.
    Bez podatków, finansowania, wpływu dużego zlecenia na cenę i zmiennych spreadów.</li>
    <li>Brak przyszłego kursu nie jest zerowym zyskiem. Niedojrzałe obserwacje i luki są
    zapisane oddzielnie w <a href="censoring.csv">wykazie brakujących wyników</a>.</li>
    <li>Banki, ubezpieczyciele i inne firmy finansowe mają odrębne profile; główne tabele
    obejmują spółki operacyjne. Ich dodatkowe wyniki znajdują się w pełnym zestawieniu.</li></ul>
    <h2>Wniosek, który wolno wyciągnąć</h2>
    <p>Można opisać, jak zachowywały się mocne i słabe oceny w tej próbie i przy tych założeniach.
    Nie można na tej podstawie uznać, że dzisiejszy model przewiduje przyszłe wzrosty lub
    spadki. Do takiego wniosku potrzebne są historyczne dane z rzeczywistymi datami publikacji,
    pierwotnymi wersjami raportów oraz spółkami usuniętymi z rynku, a następnie test na
    okresie niewykorzystanym przy projektowaniu modelu.</p>
    <h2>Materiały do sprawdzenia</h2><ul>
    <li><a href="summary.csv">Wszystkie wyniki zbiorcze</a> ·
    <a href="cohorts.csv">Wyniki roczników</a></li>
    <li><a href="returns.csv">Pojedyncze stopy zwrotu</a> ·
    <a href="scores.csv">Oceny i surowe wskaźniki</a></li>
    <li><a href="universe.json">Lista spółek</a> ·
    <a href="database_audit.json">Audyt archiwum aplikacji</a></li>
    <li><a href="specification.json">Specyfikacja badania</a> ·
    <a href="verification.json">Kontrole poprawności</a></li>
    </ul><p><small>Źródła metodologiczne:
    <a href="{cfa_url}">CFA Institute — backtesting</a>,
    <a href="{sec_url}">SEC — dane i daty zgłoszeń</a>,
    <a href="{source_url}">Dokumentacja źródła danych</a>.
    </small></p></main></html>"""
    (out / "report.html").write_text(body, encoding="utf-8")


def analyze(out):
    spec = json.loads((out / "specification.json").read_text(encoding="utf-8"))
    engine_hash = hashlib.sha256(
        (ROOT / "backend-python/app/analysis/fundamentals.py").read_bytes()
    ).hexdigest()
    if engine_hash != spec["production_scorer_sha256"]:
        raise RuntimeError("Production scoring changed after the protocol was frozen.")
    companies = json.loads((out / "universe.json").read_text(encoding="utf-8"))
    data = {}
    source_checks = []
    for company in companies:
        path = cache_path(company["symbol"])
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != SCHEMA:
            continue
        data[company["ticker"]] = {
            "income": frame(raw.get("income_stmt")),
            "balance": frame(raw.get("balance_sheet")),
            "cashflow": frame(raw.get("cashflow")),
            "daily": prices(raw.get("prices"), company["market"]),
        }
        source_checks.append(
            {
                "symbol": company["symbol"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "fetched_at": raw["fetched_at"],
                "errors": raw["errors"],
            }
        )
    scored, score_rows, exclusions = {}, [], []
    for lag in spec["publication_lags_days"]:
        for formation_text in spec["formation_dates"]:
            formation = date.fromisoformat(formation_text)
            for market in spec["markets"]:
                scope = [c for c in companies if c["market"] == market and c["ticker"] in data]
                reconstructed = [reconstruct(c, data[c["ticker"]], formation, lag) for c in scope]
                assessments = rank_reconstructed(reconstructed, scope, formation)
                for row in reconstructed:
                    assessment = assessments[row["ticker"]]
                    row["scores"] = {"overall": assessment.score, **assessment.pillars}
                    row["forward"] = (
                        {
                            months: forward_return(
                                data[row["ticker"]]["daily"],
                                formation,
                                months,
                                spec["cost_bps_each_side"],
                            )
                            for months in spec["horizons_months"]
                        }
                        if not data[row["ticker"]]["daily"].empty
                        else {
                            months: {"status": "prices_missing"}
                            for months in spec["horizons_months"]
                        }
                    )
                    scored.setdefault((market, row["profile"], formation_text, lag), []).append(row)
                    score_rows.append(
                        {k: v for k, v in row.items() if k not in ("inputs", "forward", "scores")}
                        | {
                            "excluded": ";".join(row["excluded"]),
                            "coverage": assessment.coverage,
                            "missing": ";".join(assessment.missing),
                            **{f"score_{k}": v for k, v in row["scores"].items()},
                            **row["inputs"],
                        }
                    )
                    exclusions.extend(
                        {
                            "market": market,
                            "ticker": row["ticker"],
                            "formation": formation_text,
                            "lag_days": lag,
                            "reason": reason,
                        }
                        for reason in assessment.missing
                    )
    returns, cohorts, censoring = make_groups(scored, spec)
    summary, intervals = summarize(returns), uncertainty(returns, spec)
    coverage = []
    for market in spec["markets"]:
        scope = [c for c in companies if c["market"] == market]
        scored_companies = {
            r["ticker"]
            for r in score_rows
            if r["market"] == market and r["lag_days"] == 180 and r["score_overall"] is not None
        }
        evaluated = {
            r["ticker"]
            for r in returns
            if r["market"] == market
            and r["lag_days"] == 180
            and r["months"] == 12
            and r["metric"] == "overall"
        }
        coverage.append(
            {
                "market": market,
                "selected": len(scope),
                "downloaded_prices": sum(
                    c["ticker"] in data and not data[c["ticker"]]["daily"].empty for c in scope
                ),
                "annual_statements": sum(
                    c["ticker"] in data and not data[c["ticker"]]["income"].empty for c in scope
                ),
                "scored_companies": len(scored_companies),
                "evaluated_12m": len(evaluated),
                "corporate_evaluated_12m": len(
                    {
                        r["ticker"]
                        for r in returns
                        if r["market"] == market
                        and r["lag_days"] == 180
                        and r["months"] == 12
                        and r["metric"] == "overall"
                        and r["profile"] == "corporate"
                    }
                ),
            }
        )
    for name, rows in (
        ("scores", score_rows),
        ("returns", returns),
        ("summary", summary),
        ("cohorts", cohorts),
        ("censoring", censoring),
        ("exclusions", exclusions),
        ("coverage", coverage),
        ("uncertainty", intervals),
    ):
        write_csv(out / f"{name}.csv", rows)
    save(out / "source_checksums.json", source_checks)
    save(out / "summary.json", {"coverage": coverage, "summary": summary, "uncertainty": intervals})
    checks = {
        "production_engine_unchanged": engine_hash == spec["production_scorer_sha256"],
        "no_current_ratios_used": True,
        "historical_publication_dates_verified": False,
        "raw_statements_may_be_restated": True,
        "survivorship_free_universe": False,
        "no_app_database_writes": True,
        "all_assumed_dates_before_formation": all(
            not r.get("assumed_available") or r["assumed_available"] <= r["formation"]
            for r in score_rows
        ),
        "all_entries_after_formation": all(r["entry_date"] > r["formation"] for r in returns),
        "gross_minus_cost_is_positive": all(
            r["return_gross_pct"] > r["return_net_pct"] for r in returns
        ),
        "no_duplicate_results": len(
            {
                tuple(
                    r[k] for k in ("ticker", "formation", "lag_days", "months", "metric", "group")
                )
                for r in returns
            }
        )
        == len(returns),
        "scores_rows": len(score_rows),
        "group_return_rows": len(returns),
    }
    assert checks["all_assumed_dates_before_formation"] and checks["all_entries_after_formation"]
    assert checks["no_duplicate_results"] and checks["gross_minus_cost_is_positive"]
    save(out / "verification.json", checks)
    plot(out, summary)
    report(out, spec, coverage, summary, intervals, cohorts)
    print(
        json.dumps(
            {
                "coverage": coverage,
                "overall_12m": [
                    r
                    for r in summary
                    if r["metric"] == "overall"
                    and r["months"] == 12
                    and r["lag_days"] == 180
                    and r["profile"] == "corporate"
                ],
                "uncertainty": intervals,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def plot(out, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4.5), layout="constrained")
    labels = ["USA", "Francja", "Polska"]
    colors = ["#2a6e9f", "#b4693c", "#8292a4"]
    groups = [
        ("top_quartile", "Górne 25%"),
        ("bottom_quartile", "Dolne 25%"),
        ("all", "Cała próba"),
    ]
    for offset, (group, label) in enumerate(groups):
        values = []
        for market in ("us", "fr", "gpw"):
            row = next(
                (
                    r
                    for r in summary
                    if r["market"] == market
                    and r["profile"] == "corporate"
                    and r["lag_days"] == 180
                    and r["months"] == 12
                    and r["metric"] == "overall"
                    and r["group"] == group
                ),
                None,
            )
            values.append(row["mean_net_pct"] if row else np.nan)
        ax.bar(
            np.arange(3) + (offset - 1) * 0.24,
            values,
            width=0.22,
            label=label,
            color=colors[offset],
        )
    ax.set_xticks(np.arange(3), labels)
    ax.set_ylabel("Średnia stopa zwrotu netto po 12 mies. (%)")
    ax.set_title("Badanie rocznych danych zastępczych — wynik eksploracyjny")
    ax.axhline(0, color="#8993a1", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.savefig(out / "comparison.png", dpi=160)
    plt.close(fig)
