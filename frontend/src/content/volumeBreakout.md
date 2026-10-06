## Idea w prostych słowach

Spółka, która rosła, często robi przerwę i przez kilka tygodni lub miesięcy porusza się w bok. Inwestorzy nazywają taki boczny odcinek **bazą**. W dobrej bazie spółka się uspokaja: zakres cen się zwęża, a akcje zmieniają właściciela rzadziej, bo sprzedający w większości już wyszli.

**Wybicie** to dzień, w którym cena wreszcie opuszcza bazę w górę — do nowego maksimum całego odcinka — przy **skoku wolumenu**. Ten wolumen jest tu kluczowy: sugeruje, że wchodzą duzi kupujący, np. fundusze, a nie że cena po prostu przesunęła się przez opór. Metoda kupuje właśnie tego dnia.

Metoda jest **tylko na wzrosty** i **średnioterminowa**: wybicie ma rozpocząć ruch trwający od tygodni do miesięcy.

## Skąd pochodzi

Dwóch z najbardziej znanych inwestorów w spółki wzrostowe kupuje to samo zdarzenie:

- **William O'Neil**, założyciel Investor's Business Daily, w książce *How to Make Money in Stocks* (metoda CANSLIM): kupuj, gdy spółka wybija się z prawidłowej bazy, przy wolumenie co najmniej 40–50% powyżej normy.
- **Mark Minervini** w *Trade Like a Stock Market Wizard*: formacja *Volatility Contraction Pattern* — baza, w której wahania ceny i wolumen maleją aż do wybicia.

W języku VSA to bliskie **Sign of Strength**: szeroki bar wzrostowy na wysokim wolumenie, który przebija się przez dawny opór.

## Warunki, które sprawdza StockPilot

Aby wybicie **wystąpiło**, wszystkie warunki muszą być spełnione tego samego dnia:

| # | Warunek | Jak mierzy to StockPilot |
|---:|---|---|
| 1 | Nowe maksimum bazy | zamknięcie powyżej najwyższego maksimum z poprzednich 50 sesji (ok. 10 tygodni) |
| 2 | Skok wolumenu | wolumen co najmniej 1,5× średniej z poprzednich 50 sesji |
| 3 | Dzień wygrali kupujący | zamknięcie w górnej połowie dziennego zakresu |
| 4 | Wolumen wysechł przed wybiciem | dzień wcześniej: średni wolumen z ostatnich 10 sesji nie wyższy niż średnia z 40 sesji przed nimi |
| 5 | Prawdziwa, ciasna baza | poprzednie 50 sesji mieściło się w zakresie najwyżej 35% od najwyższego maksimum do najniższego minimum |

Warunki 4 i 5 odróżniają wybicie z **prawdziwej bazy** od innych mocnych dni wzrostowych: luki po informacji albo spółki, która już pędzi niemal pionowo w górę bez żadnej bazy pod spodem. Warunek 4 jest mierzony na dzień **przed** wybiciem, żeby wolumen samego wybicia go nie zepsuł. Prawidłowe bazy O'Neila mają ok. 12–33% głębokości; granica 35% zostawia trochę zapasu.

Spółka potrzebuje **co najmniej 160 sesji** historii, żeby metoda mogła ją ocenić.

## Co widać w aplikacji

- **Wynik (0–100):** na ile spółka wygląda teraz na gotową do wybicia. Pięć sprawdzeń, po 20 punktów:
  1. zamknięcie powyżej średniej kroczącej z 50 sesji (trend wzrostowy);
  2. średnia z 50 sesji powyżej średniej ze 150 sesji (trend jest ugruntowany);
  3. cena najwyżej 15% poniżej maksimum 52-tygodniowego;
  4. wolumen wysechł (ten sam test co warunek 4 powyżej);
  5. wybicie w ciągu ostatnich 10 dni.

  Spółka, która spokojnie zacieśnia się tuż pod maksimum, może więc mieć 80 punktów jeszcze przed wybiciem, a spółka w trendzie spadkowym — blisko 0.
- **Opis:** „Breakout x2.3 vol” w dniu wybicia (wolumen 2,3× średniej), „Broke out 4d ago” w kolejnych dniach albo „3/5 setup”, gdy w ostatnich 60 sesjach nie było wybicia.
- **Znaczniki na wykresie:** indygo kropka z zieloną etykietą „Volume Breakout” w **pierwszym** dniu każdego wybicia (mocny ruch może dać kilka dni wybicia z rzędu; oznaczany jest tylko pierwszy).

## Jak to działało w praktyce

- **Bramka testu wstecznego w aplikacji** (GPW, 288 spółek, pomiar z 2026-09-23): po wybiciu akcja pobiła swój typowy ruch w **44,1%** przypadków w ciągu 10 sesji i w **45,1%** w ciągu 30. Średnia przewaga (+0,20 i +0,49 punktu procentowego) jest **mniejsza niż ta, którą w tym samym teście uzyskuje losowo wybrany dzień** (+0,59 i +1,20). Metoda **nie przechodzi** bramki.
- **Test kierunku** (2026-09-26, 1010 spółek z sześciu rynków): po wybiciu akcja pobiła rynek w **47,0%** przypadków w ciągu 10 sesji i w **45,7%** w ciągu 20; losowy wybór daje ok. 49,6%. Statystycznie to **nie lepiej niż los**.

**Krótko mówiąc:** przy standardowych progach z literatury wybicie na wolumenie nie dało przewagi na danych, które ma aplikacja. Progi celowo pozostawiono na wartościach domyślnych O'Neila i Minerviniego zamiast dopasowywać je do historii GPW, bo dopasowanie do przeszłości poprawiłoby tylko wygląd historii.

## Czego aplikacja nie robi

- Nie sprawdza wzrostu zysków ani pozostałych kryteriów CANSLIM („C”, „A”, „N” itd. u O'Neila) — tylko część dotyczącą ceny i wolumenu.
- Nie prowadzi transakcji. Własna reguła O'Neila to sprzedać akcję, która spadnie 7–8% poniżej ceny zakupu; aplikacja nie podaje stopu, celu ani sygnału wyjścia.
- Nie patrzy na szeroki rynek, który O'Neil uważa za rozstrzygający („M” w CANSLIM).

## Źródła

- William J. O'Neil, *How to Make Money in Stocks* (McGraw-Hill, kilka wydań) — CANSLIM, wybicia z bazy, reguła wolumenu.
- Mark Minervini, *Trade Like a Stock Market Wizard* (2013) — formacja Volatility Contraction Pattern.
- [Investor's Business Daily](https://www.investors.com/).
