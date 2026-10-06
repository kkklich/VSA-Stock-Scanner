## Czym jest rating VSA

Rating VSA to liczba od 0 do 100 widoczna przy każdej spółce na Pulpicie, na liście Obserwowanych i na stronie spółki. To własny odczyt aplikacji StockPilot według metody **Volume Spread Analysis** (VSA) — sposobu czytania wykresu, który porównuje, ile obrócono akcjami (wolumen), z tym, jak daleko przesunęła się cena (spread) i gdzie zamknęła się sesja.

- **50** oznacza, że ostatnio nie wydarzyło się nic istotnego.
- **Powyżej 70** (zielony) oznacza, że ostatnie sesje pokazały oznaki siły.
- **Poniżej 30** (czerwony) oznacza, że ostatnie sesje pokazały oznaki słabości.

Rating opisuje **ostatnie 120 dni** notowań. Nie jest ceną docelową ani rekomendacją. To, jak dobrze rzeczywiście cokolwiek przewidywał, uczciwie opisuje rozdział „Jak to działało w praktyce” poniżej.

## Sześć formacji, których szuka silnik

Dla każdej sesji silnik porównuje bar z **poprzednimi 20 sesjami**: ich średnim spreadem, średnim wolumenem oraz najwyższym maksimum i najniższym minimum. Jedna sesja może mieć najwyżej jedną formację. Tabela pokazuje ustawienia domyślne; większość liczb można zmienić na stronie Skaner, a rating podąża wtedy za Twoimi ustawieniami.

| Formacja | Kierunek | Co sprawdza silnik (ustawienia domyślne) | Waga |
|---|---|---|---:|
| Spring | wzrostowy | Minimum przebija najniższe minimum z poprzednich 20 sesji, ale zamknięcie wraca powyżej niego, w górnych 40% bara. Albo szeroki bar (spread ponad 1,2× średniej) na wysokim wolumenie (ponad 1,2× średniej, ale nie więcej niż 4×), albo niski wolumen (poniżej 0,7× średniej) przy płytkim zejściu (najwyżej pół średniego spreadu niżej). | 0,9 |
| Sign of Strength (SOS) | wzrostowy | Szeroki bar wzrostowy (spread ponad 1,5× średniej) na wysokim wolumenie (ponad 1,5×, nie więcej niż 4×), zamknięty w górnych 35% bara, powyżej poprzedniego zamknięcia i powyżej najwyższego maksimum z poprzednich 20 sesji. | 1,0 |
| Successful Test | wzrostowy | Bar schodzi poniżej minimum poprzedniego bara, do najniższej ćwiartki zakresu z 20 sesji (najwyżej pół średniego spreadu poniżej niego), zamyka się w górnych 35% bara, na wolumenie poniżej 0,7× średniej i niższym niż na każdej z dwóch poprzednich sesji. | 0,75 |
| Upthrust | spadkowy | Maksimum sięga najwyższego maksimum z poprzednich 20 sesji, ale zamknięcie wraca poniżej niego, w dolnych 30% szerokiego bara (spread ponad 1,2× średniej). Wolumen wysoki (ponad 1,3×) albo niski (poniżej 0,7×). | 0,85 |
| Sign of Weakness (SOW) | spadkowy | Szeroki bar spadkowy (spread ponad 1,5× średniej) na wysokim wolumenie (ponad 1,5×), zamknięty w dolnych 35% bara, poniżej poprzedniego zamknięcia. | 1,0 |
| No Demand | spadkowy | Wąski bar wzrostowy (spread poniżej 0,7× średniej) na wolumenie poniżej 0,7× średniej i niższym niż na każdej z dwóch poprzednich sesji, niezamknięty w górnych 35%. | 0,6 |

„Bar wzrostowy” oznacza, że zamknięcie jest wyższe od **zamknięcia poprzedniej sesji** — a nie od otwarcia tej samej sesji. Tak definiuje to VSA i dlatego kolor świecy i kierunek bara w VSA mogą się różnić.

## Sprawdzenie tła

VSA podkreśla, że formacja znaczy tylko tyle, na ile pozwala jej tło. Silnik odczytuje tło ze **średniej zamknięć z poprzednich 30 sesji**:

- jeśli poprzednie zamknięcie jest co najmniej 3% powyżej tej średniej, tło jest **wzrostowe**;
- jeśli co najmniej 3% poniżej — **spadkowe**;
- w pozostałych przypadkach — **neutralne**.

Spring i Successful Test są pomijane w tle spadkowym (przebicie w dół w trendzie spadkowym to załamanie, a nie siła). Upthrust i No Demand są pomijane w tle wzrostowym (spokojna przerwa w silnym wzroście nie jest ostrzeżeniem).

Dwa przypadki są odczytywane jako **kulminacja**. Bar typu Sign of Strength na wolumenie ponad 4× średniej w tle wzrostowym jest traktowany jako **kulminacja kupna** i liczony jako spadkowy (widać go jako Upthrust). Bar typu Sign of Weakness na wolumenie ponad 4×, który robi nowe minimum w tle spadkowym, może oznaczać zakupy profesjonalistów w panice („stopping volume”), więc nie daje żadnego sygnału.

## Od formacji do jednej liczby

Każda formacja ma swoją wagę (ostatnia kolumna pierwszej tabeli), a ta waga **spada o połowę co 30 dni**, więc stary sygnał stopniowo wygasa. Wagi wzrostowe się dodaje, spadkowe odejmuje — powstaje *wynik netto*. Rating to:

> rating = 50 + 50 × tanh(wynik netto ÷ 2), zaokrąglone

`tanh` to łagodna krzywa, która utrzymuje wynik między 0 a 100, więc pojedynczy sygnał nigdy nie wypycha ratingu do skrajności. Plakietka werdyktu (Strong Buy … Strong Sell) jest odczytywana z **tego samego** wyniku netto, dlatego zielony rating nigdy nie ma plakietki „Sell”.

| Wynik netto | Rating (ok.) | Werdykt | Typowa przyczyna |
|---|---:|---|---|
| +3 lub więcej | 95+ | Strong Buy | kilka świeżych sygnałów wzrostowych |
| od +1,2 do +3 | 77–95 | Strong Buy | świeży mocny sygnał plus wsparcie |
| od +0,45 do +1,2 | 61–77 | Buy | jeden świeży Sign of Strength (≈ 73) |
| od −0,45 do +0,45 | 39–61 | Hold | nic świeżego albo sygnały się znoszą |
| od −1,2 do −0,45 | 23–39 | Sell | jeden świeży No Demand (≈ 35) |
| −1,2 lub mniej | 23 lub mniej | Strong Sell | świeże mocne sygnały spadkowe |

## Gdzie widać go w aplikacji

- **Pulpit, Obserwowane, Filtry:** kolumna *Rating*, plakietka werdyktu i „dni temu” (ile minęło od ostatniego sygnału dowolnego rodzaju).
- **Znaczek „1W”:** ten sam silnik uruchomiony na świecach **tygodniowych** zbudowanych z tych samych notowań dziennych. Zielony „1W ✓” oznacza, że wykres tygodniowy wskazuje ten sam kierunek co dzienny; czerwony „1W ✗” — kierunek przeciwny. Gdy któraś strona jest neutralna, znaczka nie ma.
- **Wykres spółki:** zielone strzałki dla formacji wzrostowych, czerwone dla spadkowych.
- **Strona Skaner:** włączanie i wyłączanie poszczególnych formacji, zmiana ich progów i statystyki testu wstecznego dla każdej formacji.

## Jak to działało w praktyce

StockPilot mierzy własne metody, a wyniki ratingu VSA **nie są dobre**. Podajemy je tutaj, żeby nikt nie wziął ratingu za prognozę.

- **Bramka testu wstecznego w aplikacji** (GPW, 288 spółek, pomiar z 2026-09-23): po wzrostowym sygnale VSA akcja pobiła swój typowy ruch tylko w **44,6%** przypadków w ciągu 10 kolejnych sesji i w **44,0%** w ciągu 30 sesji. Bramka wymaga ponad 50%, więc metoda **jej nie przechodzi**. Jej średnia przewaga (+0,03 i +1,06 punktu procentowego) nie jest lepsza od tego, co w tym samym teście uzyskuje **losowo wybrany dzień** (+0,59 i +1,20).
- **Test kierunku** (2026-09-26, 1010 spółek z sześciu rynków): po wzrostowym znaczniku akcja pobiła rynek w ciągu 10 sesji w **50,1%** przypadków, a po spadkowym wypadła gorzej od rynku w **49,3%**. Losowy wybór daje 49,7%. Werdykt Buy/Sell daje ten sam obraz: **nie lepiej niż los**.
- **Spring na GPW działa odwrotnie:** po Springu akcja pobiła rynek tylko w **42%** przypadków w ciągu 10 sesji i w **37%** w ciągu 20. To jeden z niewielu wyników wyraźnych statystycznie — i wskazuje zły kierunek.
- **W czterech latach historii GPW przedziały ratingu działają na odwrót:** spółki z ratingiem 0–29 pobiły potem swój typowy ruch z 60 sesji w 53,6% przypadków, a spółki z ratingiem 70–100 tylko w 45,1%.

**Krótko mówiąc:** traktuj rating jako zwięzły opis tego, co ostatnio robiły wolumen i cena, a nie jako prognozę tego, co zrobią dalej.

## Dalsza lektura

- [Kompendium VSA](/education/vsa-kompendium) — pełne kompendium, na którym opierają się metody VSA w aplikacji: budowa bara, katalog sygnałów, testy, sekwencje i ryzyko.
- Tom Williams, *Master the Markets* — klasyczny tekst o VSA, z którego pochodzi sześć formacji silnika.
- Prace Richarda Wyckoffa o akumulacji i dystrybucji, na których opiera się VSA.
