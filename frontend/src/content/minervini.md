## Idea w prostych słowach

Mark Minervini kupuje wyłącznie akcje, które są **już w silnym, ugruntowanym trendzie wzrostowym**. Jego *Trend Template* to lista kontrolna, która odpowiada na jedno pytanie: czy ta spółka jest w zdrowej, rosnącej fazie swojego życia, czy nie? Spółki, która nie przechodzi listy, się nie kupuje — nawet jeśli wygląda na tanią.

Szablon to **filtr, a nie sygnał wejścia**. Minervini używa go, aby zdecydować, które spółki warto obserwować, a potem czeka na osobny, precyzyjny punkt wejścia (na przykład wybicie z ciasnej bazy — zobacz artykuł o Volume Breakout). StockPilot realizuje sam filtr.

Metoda jest **tylko na wzrosty** (szuka rosnących cen) i **średnioterminowa**: opisywany trend trwa od tygodni do miesięcy.

## Skąd pochodzi

Mark Minervini, *Trade Like a Stock Market Wizard* (2013). Minervini dwukrotnie wygrał U.S. Investing Championship — konkurs inwestycyjny na prawdziwych pieniądzach — co jest niezależnie sprawdzalnym wynikiem i dlatego ta metoda trafiła do aplikacji. Pojęcie trendu wzrostowego w „Fazie 2” pochodzi z analizy faz Stana Weinsteina (zobacz artykuł o Weinsteinie).

## Osiem reguł, które sprawdza StockPilot

Średnia krocząca (MA) to średnia cena zamknięcia z ostatnich N sesji; „MA 200” to średnia z ostatnich 200 zamknięć. Maksimum i minimum 52-tygodniowe to najwyższe maksimum i najniższe minimum z ostatnich 252 sesji.

| # | Reguła | Jak mierzy to StockPilot |
|---:|---|---|
| 1 | Cena jest powyżej MA 150 i MA 200 | dzisiejsze zamknięcie powyżej obu średnich |
| 2 | MA 150 jest powyżej MA 200 | porównanie z dzisiaj |
| 3 | MA 200 rośnie | dziś wyżej niż 20 sesji (ok. miesiąc) temu |
| 4 | MA 50 jest powyżej MA 150 i MA 200 | porównanie z dzisiaj |
| 5 | Cena jest powyżej MA 50 | dzisiejsze zamknięcie powyżej niej |
| 6 | Cena jest daleko od minimum 52-tygodniowego | co najmniej 30% powyżej najniższego minimum z 252 sesji |
| 7 | Cena jest blisko maksimum 52-tygodniowego | nie więcej niż 25% poniżej najwyższego maksimum z 252 sesji |
| 8 | Siła względna w górnych 30% rynku | patrz niżej — tylko na stronach z rankingiem |

**Reguła 8, siła względna.** Minervini chce spółki silniejszej od większości innych. StockPilot liczy ją tak, jak robi to Investor's Business Daily: ważona stopa zwrotu — **40%** zwrotu z ostatnich 3 miesięcy plus po **20%** zwrotów z ostatnich 6, 9 i 12 miesięcy — a potem szereguje wszystkie spółki **z tego samego rynku** od 0 (najsłabsza) do 100 (najsilniejsza). Reguła 8 jest spełniona przy wyniku **70 lub więcej**. Ponieważ porównuje spółkę ze wszystkimi innymi, istnieje tylko na stronach, które szeregują cały rynek (Pulpit, Obserwowane i Filtry). Strona spółki, która patrzy na jedną firmę, używa reguł 1–7.

Spółka potrzebuje **co najmniej 252 sesji** (ok. roku) historii. Przy krótszej metoda pisze „za mało historii” zamiast zgadywać — inaczej trzymiesięczne maksimum uchodziłoby za 52-tygodniowe.

Jedno uproszczenie: Minervini wymaga, by MA 200 rosła **co najmniej miesiąc, najlepiej cztery do pięciu**. Aplikacja sprawdza minimum jednego miesiąca.

## Co widać w aplikacji

- **Wynik (0–100):** odsetek spełnionych reguł. Na stronach z rankingiem liczony z 8 reguł (opis np. „7/8 rules”), na stronie spółki z 7 („6/7 structural”). 100 oznacza, że spełnione są wszystkie.
- **Znaczek „wystąpił niedawno”:** układ uznaje się za zaistniały w dniu, w którym spełnione były **wszystkie siedem reguł cenowych**. Znaczek pokazuje, ile dni temu zdarzyło się to ostatnio (patrząc do 90 sesji wstecz). Reguła 8 nie wpływa na znaczek, tylko na wynik.
- **Znaczniki na wykresie:** bursztynowa kropka z zieloną etykietą „Trend Template” w każdym dniu, w którym pełny szablon siedmiu reguł **się włączył** (dzień wcześniej nie był spełniony). Dopóki szablon pozostaje spełniony, kolejnych znaczników nie ma, więc każdy znacznik to początek okresu spełniania reguł.
- **Kolumna Łącznie i Podsumowanie analiz:** wynik wchodzi do łącznej oceny wielu metod i do podsumowania na stronie spółki.

## Jak to działało w praktyce

- **Bramka testu wstecznego w aplikacji** (GPW, 288 spółek, pomiar z 2026-09-23): po włączeniu się szablonu akcja pobiła swój typowy ruch tylko w **43,4%** przypadków w ciągu 10 sesji i w **41,4%** w ciągu 30, przy **ujemnej** średniej przewadze (−0,38 i −0,57 punktu procentowego). Losowo wybrany dzień uzyskuje w tym samym teście +0,59 i +1,20. Na GPW to **najsłabsza** metoda w aplikacji.
- **Test kierunku** (2026-09-26, 1010 spółek z sześciu rynków, głównie lata 2025–2026): tu Minervini wypadł lepiej niż którakolwiek metoda VSA — akcja pobiła rynek w **51,8%** przypadków w ciągu 10 sesji i w **54,1%** w ciągu 30 (losowy wybór: ok. 49,5%). Znaczący statystycznie jest tylko wynik dla 30 sesji, a prawie wszystkie te dane pochodzą z jednego okresu (2025–2026).
- **Dlaczego wynik na GPW jest słaby:** szablon włącza się, gdy spółka jest **już głęboko w trendzie wzrostowym**. Na tych samych danych metoda Weinsteina — która kupuje w chwili, gdy trend wzrostowy się *zaczyna* — zamieniła tę samą ideę z ujemnej przewagi w dodatnią. Zobacz artykuł o Weinsteinie.

**Krótko mówiąc:** na warszawskiej giełdzie samo „już jest w silnym trendzie wzrostowym” nie było dobrym powodem do zakupu. Traktuj wysoki wynik jako „ta spółka jest w dobrym trendzie”, a nie „kupuj teraz”.

## Czego aplikacja nie robi

- Nie szuka punktów wejścia Minerviniego (formacji *Volatility Contraction Pattern*, zacieśniającej się bazy). Najbliższa temu w aplikacji jest metoda Volume Breakout.
- Nie prowadzi transakcji. Minervini ogranicza straty zleceniem stop ustalonym przed zakupem; aplikacja nie podaje stopu, celu ani sygnału wyjścia.
- Nie sprawdza wyników finansowych ani fundamentów, z których Minervini też korzysta.

## Źródła

- Mark Minervini, *Trade Like a Stock Market Wizard* (McGraw-Hill, 2013) — Trend Template.
- Mark Minervini, [minervini.com](https://www.minervini.com/).
- Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (1988) — model faz, na którym opiera się szablon.
