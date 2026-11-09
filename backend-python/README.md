# StockPilot — Python backend (FastAPI)

A Python port of the StockPilot backend: a VSA stock scanner API for the Warsaw
Stock Exchange (GPW). It serves the same JSON contract as the .NET backend, so
the React frontend works against either one. This version is the foundation for
the upcoming **statistics** and **VSA calculation** modules (`app/analysis/`).

## What it does today

| Endpoint | Purpose |
|---|---|
| `GET /api/stocks` | The tracked GPW company list (from `app/data/gpw-companies.json`). |
| `GET /api/stocks/{ticker}/history?from=&to=` | End-of-day OHLCV history pulled live from stooq.pl, cached 6h. `from`/`to` are `YYYY-MM-DD`, both optional. |
| `GET /health` | Liveness probe. |

stooq.pl protects its CSV feed with a proof-of-work anti-bot challenge; the
client (`app/services/stooq_client.py`) solves it automatically, exactly like the
.NET version. Note stooq blocks datacenter IPs ("Odmowa dostępu") — that surfaces
as HTTP **502**. Expect it to work from a Polish residential IP; a VPS may need a
stooq subscription or a proxy.

## Tech

- **Python 3.11+**, **FastAPI** (web framework) + **uvicorn** (server)
- **httpx** for async outbound HTTP (shared cookie jar keeps the stooq auth cookie)
- **pydantic** v2 for models / validation, **pydantic-settings** for config
- In-process **TTL cache** standing in for .NET's `IMemoryCache`

## Run it (Windows, easiest)

Double-click **`run-backend-python.bat`** in the repo root. On first run it
creates a virtual environment, installs dependencies, and starts the server at
<http://localhost:5111> (interactive API docs at <http://localhost:5111/docs>).

> You need Python 3.11+ installed first: <https://www.python.org/downloads/>
> (tick *"Add python.exe to PATH"* during install).

## Run it (manual / cross-platform)

```bash
cd backend-python
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 5111
```

The .NET backend uses port 5123; this one defaults to 5111 so both can run side
by side. Point the frontend's API base URL at whichever you want to use.

## Configuration

All optional, via environment variables (or a local `.env` — copy `.env.example`).
Variables use the `STOCKPILOT_` prefix, e.g. `STOCKPILOT_HISTORY_CACHE_SECONDS=21600`.
See `app/config.py`.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Transakcje insiderów GPW — osobny skrypt

Ten sam odczyt raportów ESPI działa w aplikacji w sekcji insiderów pod wykresem.
Endpoint `/api/stocks/{ticker}/insider-transactions` zwraca szczegóły transakcji,
`byInsider` z sumami według osoby i waluty oraz `warnings` z uwagami do odczytu.
Przycisk „Odśwież ESPI” korzysta z `?refresh=true`, aby ponownie pobrać raporty.
Znaczniki na wykresie pozostają przy dacie publikacji informacji.

Skrypt `scripts/espi_insiders.py` pobiera z gpw.pl raporty ESPI dotyczące art. 19 MAR,
odczytuje załączniki PDF i pokazuje osobę/podmiot, funkcję, zakup lub sprzedaż,
datę transakcji, datę publikacji, liczbę akcji, cenę, walutę i wartość. Wyświetla też
podsumowanie zakupów i sprzedaży według osoby, osobno dla każdej waluty.
Nie wymaga uruchomienia serwera ani bazy danych; korzysta z zależności backendu
zainstalowanych według instrukcji powyżej.

Z głównego folderu repozytorium w PowerShell:

```powershell
.\backend-python\.venv\Scripts\python.exe .\backend-python\scripts\espi_insiders.py --ticker CBF --html insiderzy.html --csv insiderzy.csv --open
```

Zmień `CBF` na ticker wybranej spółki, np. `CDR` lub `PKO`. Raport HTML otworzy się
w przeglądarce, a CSV można otworzyć w Excelu (separator `;`, polskie przecinki
dziesiętne, kodowanie UTF-8 z BOM). CSV zawiera transakcje; podsumowanie osób jest
w konsoli i HTML. Jeśli spółki nie ma w lokalnej liście, podaj jej nazwę:
`--ticker XYZ --company "Pełna nazwa emitenta"`.

Można też odczytać wcześniej pobrany **załącznik z formularzem MAR**:

```powershell
.\backend-python\.venv\Scripts\python.exe .\backend-python\scripts\espi_insiders.py --pdf powiadomienie.pdf --published 2026-09-16 --html insiderzy.html --open
```

`--published` to rzeczywista data publikacji raportu ESPI, a nie data transakcji
ani dzień uruchomienia skryptu. Filtry `--insider "nazwisko"`, `--from YYYY-MM-DD`
i `--to YYYY-MM-DD` zawężają wynik. Daty filtrują **datę transakcji**; rekordy bez
tej daty zostają wtedy pominięte z odpowiednią uwagą.

Ograniczenia odczytu:

- Domyślnie skrypt przeszukuje do 50 ostatnich raportów emitenta i odczytuje do 15
  pasujących raportów MAR, maksymalnie 10 PDF-ów na raport. `--limit` (1–500) oraz
  `--reports` (1–100) zmieniają dwa pierwsze limity. To nie jest pełna historia;
  filtr dat nie powoduje pobrania starszych stron archiwum.
- PDF-y muszą mieć warstwę tekstową. Skany wymagają OCR; nietypowe formularze
  mogą zostać odczytane częściowo. Limit pliku wynosi 10 MB i 50 stron.
- Nieodczytane pola pozostają oznaczone jako brak danych. Nieznana liczba akcji
  powoduje też nieznaną sumę dla danej osoby i kierunku, zamiast zaniżonego wyniku.
- Bilans obejmuje odczytane zakupy i sprzedaż, także poza giełdą. Darowizny,
  przyznania akcji i opcje nie wchodzą do bilansu. To nie jest stan posiadania.
  Korekty i ponowne publikacje wymagają sprawdzenia w źródle.
- Błędy pobierania i nieodczytane załączniki są opisane w uwagach. Brak rekordów
  nie jest potwierdzeniem braku transakcji. Jeśli nie uzyskano żadnych rekordów
  i wystąpił błąd odczytu, skrypt kończy się kodem 1; błędne argumenty — kodem 2.

## Project layout

```
backend-python/
├── app/
│   ├── main.py            FastAPI app: CORS, lifespan, router wiring
│   ├── config.py          Settings (env-driven)
│   ├── dependencies.py    Shared singletons + FastAPI dependency providers
│   ├── models/            Pydantic API models (the JSON contract)
│   ├── routers/           HTTP endpoints (transport layer)
│   ├── services/          Data sources: stooq client, GPW list, TTL cache
│   ├── analysis/          ← statistics & VSA calculations live here (stubs today)
│   └── data/              gpw-companies.json seed list
└── tests/
```

## Where the new modules go

`app/analysis/` is deliberately isolated from the web and data layers so the maths
can be built and unit-tested against plain OHLCV bars:

- **`app/analysis/statistics.py`** — close-position-in-spread, relative volume,
  trailing median volume, and the ranking pre-filters (liquidity & market cap).
- **`app/analysis/vsa.py`** — VSA signal detection (Spring, Upthrust, Test, SOS,
  SOW, No Demand) and the 0–100 rating with Time Decay.

Both ship today as documented stubs (`NotImplementedError`) that define the
intended contract. The planned `GET /api/stocks/ranking` and
`GET /api/stocks/{ticker}/signals` endpoints (see `agent/DOCUMENTATION.md` §5)
will build on them.
