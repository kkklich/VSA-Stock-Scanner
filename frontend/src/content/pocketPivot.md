## Idea w prostych słowach

Zanim spółka wybije się na nowe maksima, zwykle przez kilka tygodni porusza się w bok, w **bazie**. Klasyczny sposób zakupu — [Volume Breakout](/education/volume-breakout) — czeka na dzień, w którym cena opuszcza tę bazę przy dużym wolumenie. Do tego czasu cena często zdążyła już urosnąć, a nieudane wybicie potrafi od razu spaść z powrotem.

**Pocket pivot** próbuje wejść wcześniej, **wewnątrz bazy**. Szuka jednego dnia, w którym kupujący wyraźnie przeważają nad sprzedającymi: kurs rośnie, a wolumen jest **co najmniej tak duży jak największy dzień sprzedaży z poprzednich dwóch tygodni**. Jeśli dzieje się to wtedy, gdy spółka spokojnie trzyma się swojej średniej kroczącej, może to oznaczać, że duży kupujący — fundusz — skupuje akcje jeszcze przed wybiciem.

Metoda jest **tylko na wzrosty** i **średnioterminowa**: tak jak wybicie, które próbuje wyprzedzić, ma złapać ruch trwający od tygodni do miesięcy.

## Skąd pochodzi

Gil Morales i Chris Kacher, *Trade Like an O'Neil Disciple: How We Made 18,000% in the Stock Market* (Wiley, 2010), oraz jej kontynuacja *In the Trading Cockpit with the O'Neil Disciples* (2012). Obaj zarządzali pieniędzmi w William O'Neil + Co., firmie założyciela Investor's Business Daily; Morales przez osiem lat prowadził tam część własnego kapitału firmy. Książka nazywa pocket pivot „an early base breakout indicator” — wczesnym wskaźnikiem wybicia z bazy.

Co dowody pokazują, a czego nie:

- Kacher podaje, że jego prywatny rachunek zarobił **18 241% w latach 1996–2002**, co według niego zweryfikowała firma audytorska KPMG. Ale sam pocket pivot powstał **później**, w połowie lat 2000., więc ten wynik **nie** jest dowodem na tę regułę.
- Sam Kacher mówi, że **mniej więcej połowa** pocket pivotów, nawet w dobrych spółkach, nie działa — mniej więcej tyle samo, co zwykłych wybić.
- **Nie znaleziono niezależnego testu** tej reguły.

To więc jasno opisana metoda doświadczonych inwestorów, a nie udowodniona przewaga. Aplikacja mierzy ją na własnych danych (niżej).

## Czym różni się od wybicia na wolumenie

| | Volume Breakout | Pocket Pivot |
|---|---|---|
| Gdzie kupuje | w dniu, w którym cena **opuszcza** bazę, na nowym maksimum | **wewnątrz** bazy, przed wybiciem |
| Z czym porównuje wolumen | ze średnią z poprzednich 50 sesji | z **największym dniem sprzedaży** z poprzednich 10 sesji |
| Gdzie musi być cena | powyżej najwyższego maksimum bazy | blisko 10- lub 50-sesyjnej średniej kroczącej, nie daleko nad nią |

Porównanie wolumenu to najciekawszy pomysł tej metody: zestawia **popyt z podażą** — dzień kupujących z największym dniem sprzedających — dokładnie tak, jak analiza VSA czyta pojedynczy bar.

## Sześć warunków, które sprawdza StockPilot

Aby pocket pivot **wystąpił**, wszystkie sześć warunków musi być spełnionych tego samego dnia:

| # | Warunek | Jak mierzy to StockPilot |
|---:|---|---|
| 1 | Dzień wygrali kupujący | zamknięcie powyżej poprzedniego zamknięcia |
| 2 | Popyt przeważa nad podażą | wolumen dnia co najmniej równy wolumenowi **największego dnia spadkowego** z poprzednich 10 sesji |
| 3 | Trend jest zdrowy | zamknięcie powyżej średniej kroczącej z 50 i z 200 sesji |
| 4 | Startuje od linii, nie z powietrza | dzienne minimum na, pod albo najwyżej **2%** nad średnią z 10 lub 50 sesji, a zamknięcie powyżej tej średniej |
| 5 | Wcześniej było spokojnie | 5 sesji przed nim miało średnio mniejszy wolumen niż 50 sesji przed nimi |
| 6 | Bez klina | w 5 sesjach przed nim **nie** było wyższego minimum w co najmniej 4 dniach przy rosnącym zamknięciu |

Warunki 1–3 to słowa samych autorów: książka wymaga wolumenu dnia wzrostowego „equal to or greater than the largest down-volume day over the prior 10 days” (równego największemu wolumenowi dnia spadkowego z poprzednich 10 dni albo od niego większego) i mówi, że pocket pivoty kupuje się powyżej średniej z 50 dni; reguły Kachera dodają średnią z 200 dni. **Trzy liczby to odczytanie aplikacji**, bo autorzy opisują te warunki tylko słowami albo na wykresach: „tuż przy” linii (2%), wolumen „spokojny przez kilka poprzednich dni” (5 sesji) i „klin” (4 z 5 rosnących minimów). Ustalono je przed jakimkolwiek pomiarem i nie dopasowywano później.

Warunki 5 i 6 razem to obraz pocket pivota z książki: spokojne cofnięcie albo pauza na średniej kroczącej, a potem jeden dzień popytu cięższego niż jakakolwiek niedawna podaż. Pokrywają też dwa ostrzeżenia autorów: spółka, która „mocno spada” przez swoje średnie i od razu wraca w górę w kształcie litery V, nie robi tego na spokojnym wolumenie, a spółka powyżej średniej z 200 sesji rzadko jest w wielomiesięcznym trendzie spadkowym, przed którym ostrzega Kacher.

Jeśli w poprzednich 10 sesjach nie było żadnego dnia spadkowego z wolumenem, nie ma z czym porównać i pocket pivot **nie** występuje. Spółka potrzebuje **co najmniej 200 sesji** historii (dla średniej z 200 sesji).

## Co widać w aplikacji

- **Wynik (0–100):** na ile obraz pocket pivota jest teraz kompletny. Sześć sprawdzeń, po ok. 17 punktów: zamknięcie powyżej średniej z 50 sesji; powyżej średniej z 200 sesji; spółka jest przy linii zakupu (ten sam test co warunek 4); wolumen był spokojny; brak klina; oraz pocket pivot w ciągu ostatnich 10 dni. Poniżej średniej z 200 sesji wynik jest ograniczony do 50, bo autorzy nie kupują tam żadnego pocket pivota, więc przy takiej spółce metoda nigdy nie liczy się jako pozytywna w podsumowaniu analityki.
- **Opis:** „Pocket pivot x1.4 down-vol” w dniu sygnału (wolumen 1,4× największego dnia spadkowego), „Pocket pivot 3d ago, 6/6” w kolejnych dniach, a w pozostałych przypadkach „4/6 setup” albo „2/6 below 200d MA”.
- **Znaczniki na wykresie:** turkusowa kropka z zieloną etykietą w dniu sygnału — „Pocket Pivot 10d”, gdy dzień wyszedł od średniej z 10 sesji (zwykły przypadek u autorów), albo „Pocket Pivot 50d”, gdy od średniej z 50 sesji. Dwa dni sygnału z rzędu dostają jeden znacznik.

## Prawdziwy przykład: XTB, lipiec 2026

Pod koniec czerwca 2026 kurs XTB (XTB, GPW) przez tydzień spokojnie się cofał: dzienne minima zeszły z 106,84 do ok. 103,50 zł, a pięć sesji przed 1 lipca miało średnio **246 074 akcji** dziennie, niewiele ponad połowę z 448 527 w pięćdziesięciu sesjach przed nimi. **1 lipca 2026** kurs zszedł do 105,94 zł, poniżej 10-sesyjnej średniej 107,98, i zamknął się na **110,00 zł** przy **424 306 akcjach — 1,41× największego dnia spadkowego z poprzednich dziesięciu sesji** (300 361 akcji 24 czerwca). Był wyraźnie powyżej średniej z 50 sesji (103,42) i z 200 sesji (83,23). Wszystkie sześć warunków było spełnionych, a opis brzmi „Pocket pivot x1.4 down-vol”. Dziesięć sesji później, 15 lipca, kurs zamknął się na 135,20 zł: **+22,9%**.

Te same miesiące pokazują też, jak metoda odmawia. **2 marca 2026** wolumen XTB wyniósł **2,0×** największego niedawnego dnia spadkowego, ale kurs doszedł do tego dnia z wyższym minimum w czterech z pięciu poprzednich sesji — to klin (warunek 6). **9 lipca 2026** wolumen wyniósł **2,7×**, ale po niemal pionowym ruchu ze 110 do 124 zł minimum dnia było 7% nad średnią z 10 sesji — cena była za daleko od linii (warunek 4).

Kontrprzykład: **PZU** spełniło wszystkie sześć warunków **23 lutego 2026**, a dziesięć sesji później jego kurs był **8,3% niżej**. Trzy dni XTB są automatycznie sprawdzane w testach aplikacji na prawdziwych cenach. Jeden dobry przykład sam niczego nie dowodzi — liczą się pomiary poniżej.

## Jak to działało w praktyce

- **Jak często się włącza:** często. W zapisanej historii GPW włączył się około **5 razy na spółkę na rok** — 2765 razy, na 198 z 288 spółek. Nieco ponad połowa tych dni (56%) przypadła na spółki wystarczająco płynne dla rankingu; reszta to dni słabego obrotu, które ranking pomija.
- **Bramka testu wstecznego w aplikacji** (GPW, ok. czterech lat, pomiar z 2026-09-26): po pocket pivocie akcja pobiła swój typowy ruch w **46,3%** przypadków w ciągu 10 sesji i w **44,5%** w ciągu 30. Średnia przewaga (+0,26 i +0,39 punktu procentowego) jest **mniejsza niż ta, którą w tym samym teście uzyskuje losowo wybrany dzień** (+0,59 i +1,20). Metoda **nie przechodzi** bramki.
- **Na tle rynku** (2026-09-26, sześć rynków, spółki powyżej progu płynności, ta sama metoda co w teście kierunku): po pocket pivocie akcja pobiła medianową spółkę rynku w **49,7%** przypadków w ciągu 10 sesji i w **50,4%** w ciągu 20; losowy wybór w te same dni daje ok. **49,6%**. To **nie lepiej niż los**. Na samym GPW wynik sięgnął 52,6% w ciągu 30 sesji, ale na rynkach zagranicznych tylko 46,1% — dwa wyniki w przeciwne strony, czyli dokładnie to, jak wygląda przypadek.
- **Od średniej z 10 czy z 50 sesji:** sygnały od średniej z 50 sesji wypadły w ciągu 10 sesji nieco lepiej (53,5% wobec 49,1%), ale tylko na 254 przypadkach — to za mało, by cokolwiek znaczyło.

**Krótko mówiąc:** jasno opisana reguła doświadczonych inwestorów, ale na danych, które ma aplikacja, nie dała przewagi. Progi celowo pozostawiono na wartościach autorów zamiast dopasowywać je do historii, bo dopasowanie do przeszłości poprawiłoby tylko wygląd historii.

## Czego aplikacja nie robi

- Nie sprawdza fundamentów spółki. Autorzy chcą też silnego wzrostu zysków i sprzedaży oraz lidera w swojej branży.
- Nie stosuje rzadkiego wyjątku autorów: spółki wyraźnie poniżej średniej z 50 dni, która znajduje wsparcie na średniej z 200 dni.
- Nie prowadzi transakcji. Autorzy używają średnich kroczących jako wskazówek do sprzedaży; aplikacja nie podaje stopu, celu ani sygnału wyjścia.
- Nie patrzy na kierunek całego rynku, który szkoła O'Neila uważa za rozstrzygający.

## Źródła

- Gil Morales, Chris Kacher, *Trade Like an O'Neil Disciple: How We Made 18,000% in the Stock Market* (Wiley, 2010) — rozdział 4, pocket pivoty.
- Gil Morales, Chris Kacher, *In the Trading Cockpit with the O'Neil Disciples* (Wiley, 2012).
- Chris Kacher, „Ten Rules for Trading Pocket Pivots” — [przedruk na NewTraderU](https://www.newtraderu.com/2012/08/21/ten-rules-for-trading-pocket-pivots-2/).
- [The Virtue of Selfish Investing](https://www.virtueofselfishinvesting.com/) — strona autorów.
