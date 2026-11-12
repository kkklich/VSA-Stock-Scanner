"""The official exchange directory expands, rather than replaces, our catalogue."""

import json
from html import escape

import pytest

from scripts.refresh_gpw_companies import main, merge_companies, parse_gpw_companies


def directory(*entries):
    rows = "".join(
        '<tr><td><a href="spolka?isin=PL0000000000"><strong class="name">'
        f'{escape(name)} <span class="grey">({escape(ticker)})</span></strong></a>'
        "<small>Główny Rynek | Biotechnologia</small></td><td>100</td></tr>"
        for ticker, name in entries
    )
    return f'<table id="lista-spolek"><tbody id="search-result">{rows}</tbody></table>'


def test_parse_extracts_exchange_ticker_and_registered_name_without_guessing_sector():
    html = directory(("S2B", "Syn2bio Spółka Akcyjna"), ("CRQ", "Creotech Quantum S.A."))
    assert parse_gpw_companies(html) == [
        {"ticker": "crq", "name": "Creotech Quantum S.A.", "sector": None},
        {"ticker": "s2b", "name": "Syn2bio Spółka Akcyjna", "sector": None},
    ]


def test_parse_only_reads_the_official_company_table_and_collapses_layout_whitespace():
    html = '<a href="spolka?isin=PL0000000000"><strong class="name">Other (BAD)</strong></a>'
    html += directory(("06N", "  Example\n  Spółka\tAkcyjna  "))
    assert parse_gpw_companies(html) == [
        {"ticker": "06n", "name": "Example Spółka Akcyjna", "sector": None},
    ]


def test_identical_directory_duplicates_are_deduplicated_but_conflicting_names_fail():
    assert len(parse_gpw_companies(directory(("CRQ", "Same"), ("CRQ", "Same")))) == 1
    with pytest.raises(ValueError, match="Conflicting GPW"):
        parse_gpw_companies(directory(("CRQ", "One"), ("CRQ", "Another")))


@pytest.mark.parametrize(
    "html",
    [
        "<h1>GPW temporarily unavailable</h1>",
        directory(("AAPL.US", "Foreign symbol")),
        directory(("BAD TICKER", "Bad symbol")),
        directory(("CRQ", "")),
        '<table id="lista-spolek"><tbody id="search-result"><tr><td>Bad</td></tr></tbody></table>',
    ],
)
def test_missing_or_ambiguous_directory_structure_is_rejected(html):
    with pytest.raises(ValueError):
        parse_gpw_companies(html)


def test_merge_preserves_all_existing_metadata_and_historical_symbols():
    existing = [
        {"ticker": "old", "name": "Historical company", "sector": "Legacy", "extra": 42},
        {"ticker": "crq", "name": "Custom name", "sector": "Technology"},
        {"ticker": "nul", "name": "Known without sector", "sector": None},
    ]
    official = parse_gpw_companies(
        directory(
            ("CRQ", "New registered name"),
            ("S2B", "Syn2bio S.A."),
            ("NUL", "New name"),
        )
    )
    merged = merge_companies(existing, official)
    assert [company["ticker"] for company in merged] == ["crq", "nul", "old", "s2b"]
    assert all(company in merged for company in existing)
    assert merged[-1] == {"ticker": "s2b", "name": "Syn2bio S.A.", "sector": None}
    assert merge_companies(merged, official) == merged
    assert existing[0]["extra"] == 42


def test_merge_rejects_duplicate_existing_keys_instead_of_discarding_one():
    with pytest.raises(ValueError, match="Duplicate existing"):
        merge_companies([{"ticker": "crq"}, {"ticker": "CRQ"}], [])


def test_cli_incomplete_source_never_changes_existing_file(tmp_path, capsys):
    source = tmp_path / "source.html"
    source.write_text(directory(("CRQ", "Example")), encoding="utf-8")
    output = tmp_path / "companies.json"
    original = '[{"ticker":"old","name":"Keep me"}]\n'
    output.write_text(original, encoding="utf-8")
    assert main(["--source-html", str(source), "--output", str(output)]) == 1
    assert output.read_text(encoding="utf-8") == original
    assert "only 1 distinct companies" in capsys.readouterr().err


def test_cli_merges_complete_saved_source_as_sorted_utf8_json(tmp_path):
    source = tmp_path / "source.html"
    entries = [(f"T{index:03}", f"Spółka {index}") for index in range(300)]
    source.write_text(directory(*reversed(entries)), encoding="utf-8")
    output = tmp_path / "companies.json"
    existing = {"ticker": "old", "name": "Existing name", "sector": "Technology"}
    output.write_text(json.dumps([existing]), encoding="utf-8")
    args = ["--source-html", str(source), "--output", str(output)]
    assert main(args) == 0
    content = output.read_text(encoding="utf-8")
    merged = json.loads(content)
    assert len(merged) == 301
    assert merged[0] == existing
    assert merged[1] == {"ticker": "t000", "name": "Spółka 0", "sector": None}
    assert "Spółka" in content
    assert content.endswith("\n")
    assert main(args) == 0
    assert output.read_text(encoding="utf-8") == content
