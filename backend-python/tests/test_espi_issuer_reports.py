"""Regression coverage for matching exchange notices to the issuer archive."""

from datetime import date

from app.services.espi_issuer_reports import issuer_report_matches, parse_issuer_report_candidates

INDEX_URL = "https://investors.cyberfolks.pl/raporty/"
STUB = {
    "report_number": "34/2026",
    "publication_date": date(2026, 9, 16),
    "title": "Powiadomienie o transakcjach nabycia w trybie art. 19 MAR",
}


def test_archive_groups_attachments_by_report_number_and_detail_url():
    archive = """
    <div class="reports__result">
      <a class="reports__result-title" href="raport-biezacy-34-2026/">Raport bieżący 34/2026</a>
      <div class="reports__result-files">
        <a href="/wp-content/uploads/notice.pdf">Powiadomienie</a>
        <a href="/wp-content/uploads/second.pdf">Drugi załącznik</a>
        <a href="/wp-content/uploads/notice.pdf">Powtórzony link</a>
        <a href="https://other.example/notice.pdf">Link zewnętrzny</a>
        <a href="/wp-content/uploads/archive.zip">Archiwum</a>
      </div>
    </div>
    <div class="reports__result">
      <a class="reports__result-title" href="raport-biezacy-034-2026/">Raport bieżący 034/2026</a>
      <div class="reports__result-files">
        <a href="/wp-content/uploads/other-report.pdf">Inne powiadomienie</a>
      </div>
    </div>
    <div class="reports__result">
      <a class="reports__result-title" href="https://other.example/">Raport bieżący 35/2026</a>
      <div class="reports__result-files">
        <a href="/wp-content/uploads/unverified.pdf">Załącznik</a>
      </div>
    </div>
    """
    uploads = "https://investors.cyberfolks.pl/wp-content/uploads/"
    assert parse_issuer_report_candidates(archive, INDEX_URL) == {
        "34/2026": [
            (
                INDEX_URL + "raport-biezacy-34-2026/",
                (uploads + "notice.pdf", uploads + "second.pdf"),
            ),
            (INDEX_URL + "raport-biezacy-034-2026/", (uploads + "other-report.pdf",)),
        ]
    }


def test_detail_requires_number_date_and_mar_subject_or_legal_basis():
    detail = """
    <main>
      <h2>Raport bieżący 34/2026</h2><p>16/09/2026 • 17:07</p>
      <p>Temat:</p><p></p><p>Powiadomienie o transakcjach nabycia w trybie art. 19 MAR</p>
      <h5>Podstawa prawna:</h5><p>Art. 19 ust. 3 Rozporządzenia MAR</p>
    </main>
    """
    assert issuer_report_matches(detail, STUB)
    wrong_subject = detail.replace(STUB["title"], "Rozpoczęcie negocjacji")
    assert issuer_report_matches(wrong_subject, STUB)
    assert not issuer_report_matches(wrong_subject.replace("Art. 19", "Art. 17"), STUB)
    assert not issuer_report_matches(detail.replace("34/2026", "33/2026"), STUB)
    assert not issuer_report_matches(detail.replace("16/09/2026", "15/09/2026"), STUB)
