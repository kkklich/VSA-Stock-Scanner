"""Commission extraction must distinguish a reported zero from a missing cell."""

import importlib.util
from pathlib import Path

import pytest

PARSER_PATH = Path(__file__).resolve().parents[2] / "deploy/n8n/xtb_pdf_to_object.py"
spec = importlib.util.spec_from_file_location("n8n_xtb_parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def summary_page(fee=None, *, include_column=True, fee_before_price=False):
    cells = [
        ("Lp.", "1"),
        ("Nr zlecenia", "2955645632"),
        ("Zlecenie", "Kupno"),
        ("Symbol instrumentu bazowego", "KTY.PL"),
        ("Nazwa instrumentu", "Grupa Kety SA"),
        ("Wolumen", "0.2954"),
        ("Waluta instrumentu", "PLN"),
        ("Cena realizacji zlecenia", "1225.00000"),
    ]
    if include_column:
        cells.insert(-1 if fee_before_price else len(cells), ("Prowizja", fee or ""))
    return "\n".join(
        [
            "Najważniejsze informacje na temat zleceń wykonanych w dniu 20.11.2026",
            f"{'Imię i nazwisko':<40}Konto",
            f"{'Test User':<40}52446029",
            "".join(f"{label:<40}" for label, value in cells).rstrip(),
            "".join(f"{value:<40}" for label, value in cells).rstrip(),
        ]
    )


@pytest.mark.parametrize("fee", ["0.00", "0,00", "0", "1.25", "-1,25"])
@pytest.mark.parametrize("fee_before_price", [False, True])
def test_summary_reads_commission_column_including_zero(fee, fee_before_price):
    page = summary_page(fee, fee_before_price=fee_before_price)
    result = parser.transform_item({"pages": [{"text": page}]})
    assert result["status"] == "ready", result
    assert result["brokerAccountId"] == "52446029"
    trade = result["transactions"][0]
    assert trade["price"] == "1225.00000"
    assert trade["fees"] == ("0" if fee in {"0.00", "0,00", "0"} else "1.25")


@pytest.mark.parametrize("include_column", [False, True])
def test_missing_commission_is_distinct_from_zero(include_column):
    result = parser.transform_item(
        {"pages": [{"text": summary_page(include_column=include_column)}]}
    )
    assert result["status"] == "needs_review"
    assert result["candidates"][0]["fees"] is None
    assert result["transactions"] == []


@pytest.mark.parametrize("fee", ["0.00", 0])
def test_explicit_confirmation_accepts_zero(fee):
    result = parser.transform_item(
        {
            "pages": [{"text": summary_page(include_column=False)}],
            "confirmedOrders": {"2955645632": {"fees": fee}},
        }
    )
    assert result["status"] == "ready"
    assert result["transactions"][0]["fees"] == "0"


def test_confirmation_cannot_replace_reported_nonzero_commission():
    result = parser.transform_item(
        {
            "pages": [{"text": summary_page("1.25")}],
            "confirmedOrders": {"2955645632": {"fees": "0.00"}},
        }
    )
    assert result["status"] == "needs_review"
    assert "conflicts" in result["error"]
    assert result["transactions"] == []


EXPECTED_OBJECT = {
    "status": "ready",
    "brokerAccountId": "52446029",
    "reportDate": "2026-11-20",
    "transactions": [
        {
            "orderId": "2955645632",
            "ticker": "kty",
            "date": "2026-11-20",
            "side": "buy",
            "quantity": "0.2954",
            "price": "1225.00000",
            "fees": "0",
            "currency": "PLN",
        }
    ],
}


def test_ready_output_matches_requested_object_exactly():
    result = parser.transform_item({"pages": [{"text": summary_page("0.00")}]})
    assert result == EXPECTED_OBJECT


def test_paste_ready_node_returns_requested_object_with_confirmed_fee():
    source = PARSER_PATH.with_name("xtb_pdf_code_node.txt").read_text(encoding="utf-8")
    namespace = {}
    exec(
        "def execute_node(_item):\n" + "\n".join("    " + line for line in source.splitlines()),
        namespace,
    )
    result = namespace["execute_node"](
        {"json": {"pages": [{"text": summary_page(include_column=False)}]}}
    )
    assert result == {"json": EXPECTED_OBJECT}


def all_items_node(items):
    source = PARSER_PATH.with_name("xtb_pdf_code_node_all_items.txt").read_text(encoding="utf-8")
    namespace = {}
    exec(
        "def execute_node(_items):\n" + "\n".join("    " + line for line in source.splitlines()),
        namespace,
    )
    return namespace["execute_node"](items)


def test_all_items_node_displays_exact_requested_array():
    input_json = {"pages": [{"text": summary_page(include_column=False)}]}
    result = all_items_node([{"json": input_json}])
    assert [item["json"] for item in result] == [EXPECTED_OBJECT]
    assert result[0]["pairedItem"] == {"item": 0}
    assert "confirmedOrders" not in input_json


def test_all_items_node_preserves_each_reports_commission_and_input_link():
    second_page = summary_page("1.25").replace("2955645632", "2955645633")
    result = all_items_node(
        [
            {"json": {"pages": [{"text": summary_page(include_column=False)}]}},
            {"json": {"pages": [{"text": second_page}]}},
        ]
    )
    assert len(result) == 2
    assert result[0]["json"] == EXPECTED_OBJECT
    assert result[1]["json"]["status"] == "ready"
    assert result[1]["json"]["transactions"][0]["orderId"] == "2955645633"
    assert result[1]["json"]["transactions"][0]["fees"] == "1.25"
    assert result[1]["pairedItem"] == {"item": 1}


def test_all_items_node_does_not_assume_zero_for_other_orders():
    page = summary_page(include_column=False).replace("2955645632", "2955645633")
    [result] = all_items_node([{"json": {"pages": [{"text": page}]}}])
    assert result["json"]["status"] == "needs_review"
    assert result["json"]["transactions"] == []
