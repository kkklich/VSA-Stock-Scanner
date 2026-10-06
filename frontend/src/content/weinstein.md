## Idea w prostych słowach

Stan Weinstein patrzy na każdą spółkę na wykresie **tygodniowym** i widzi jej życie jako cykl czterech faz, odczytywanych względem **30-tygodniowej średniej kroczącej** (średniego tygodniowego zamknięcia z ostatnich 30 tygodni):

| Faza | Nazwa | Jak wygląda wykres | Co robi Weinstein |
|---|---|---|---|
| 1 | Budowanie bazy | po spadku spółka miesiącami porusza się w bok; 30-tygodniowa średnia przestaje spadać i się wypłaszcza | czeka |
| 2 | Wzrost | spółka wybija się z bazy i rośnie; średnia skręca w górę | **kupuje na początku** |
| 3 | Szczyt | spółka znów porusza się w bok, tym razem na górze | sprzedaje / trzyma się z daleka |
| 4 | Spadek | spółka spada poniżej opadającej średniej | trzyma się z daleka |

Cała metoda polega na kupnie **w chwili, gdy Faza 1 przechodzi w Fazę 2**: w tygodniu, w którym spółka wybija się z długiej, nudnej bazy na dużym wolumenie. Właśnie tego szuka StockPilot. Metoda jest **tylko na wzrosty** i **średnioterminowa** — wzrost w Fazie 2 trwa zwykle miesiącami.

## Skąd pochodzi

Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (1988). Najlepszym niezależnym potwierdzeniem jest praca **Thomasa Bulkowskiego**, który posortował 440 własnych, prawdziwych transakcji (1987–2010, po kosztach) według fazy, w której kupował:

- zakup przy **wybiciu z Fazy 1 do Fazy 2**: średnio **+13,2%**, **69%** zyskownych (127 transakcji);
- zakup **głęboko w Fazie 2**: średnio **+4,1%**, **57%** zyskownych (116 transakcji);
- zakup w Fazie 3 lub 4: strata.

To decyzje jednego inwestora, a nie test mechaniczny — dlatego aplikacja mierzy metodę ponownie na własnych danych (niżej).

## Dlaczego świece tygodniowe

Fazy Weinsteina, jego 30-tygodniowa średnia i test wolumenu są zdefiniowane na świecach **tygodniowych**. Uruchomienie ich na dziennych byłoby inną regułą pod jego nazwiskiem. StockPilot buduje świece tygodniowe z cen dziennych, które już przechowuje, więc nic dodatkowego nie jest pobierane.

**Trwający tydzień jest pomijany.** Weinstein kupuje na tygodniowym *zamknięciu*, a niedokończony tydzień ma tylko część tygodniowego wolumenu, co odebrałoby sens testowi wolumenu. Dlatego od poniedziałku do czwartku metoda pokazuje wynik ostatniego zakończonego tygodnia. Tydzień wybicia jest widoczny jako „wystąpiło” w swój piątek i przez weekend, a od poniedziałku jako „Broke out 3d ago”, „Broke out 4d ago” itd. (wybicie sprzed 3, 4 dni), licząc od ostatniej sesji. Jeśli następny tydzień znów wybija, to ten sam ruch: nie dostaje nowego znacznika na wykresie i nie jest też pokazywany jako „wystąpiło”.

## Sześć warunków, które sprawdza StockPilot

Aby wybicie **wystąpiło**, wszystkie sześć warunków musi być spełnionych w tym samym zakończonym tygodniu:

| # | Warunek | Jak mierzy to StockPilot |
|---:|---|---|
| 1 | Była prawdziwa baza | 20 tygodni przed tym tygodniem mieściło się w zakresie najwyżej 30% od najwyższego maksimum do najniższego minimum |
| 2 | Tydzień wybija się z niej | tygodniowe zamknięcie powyżej najwyższego maksimum tych 20 tygodni |
| 3 | Jest po stronie Fazy 2 | tygodniowe zamknięcie powyżej 30-tygodniowej średniej kroczącej |
| 4 | Spadek się skończył | 30-tygodniowa średnia nie jest niżej niż 10 tygodni temu |
| 5 | Wzrost dopiero się zaczyna | 30-tygodniowa średnia wzrosła w tych 10 tygodniach najwyżej o 10% |
| 6 | Kupujący naprawdę są | wolumen tygodnia co najmniej 2× średniej z poprzednich 10 tygodni |

**Warunek 5 to serce metody.** Bez niego te same reguły włączałyby się także na spółce, która już mocno urosła i tylko zrobiła przerwę: płaski 20-tygodniowy odcinek na szczycie stromego wzrostu wciąż ma stromo *rosnącą* 30-tygodniową średnią. To słabszy zakup Bulkowskiego „głęboko w Fazie 2”. Ten limit trzyma metodę przy **przejściu**, które naprawdę kupuje Weinstein. W historii GPW sam ten warunek odrzucił 4467 tygodni-kandydatów.

Faza 1 u Weinsteina następuje po spadku w Fazie 4, ale spadek **nie** jest sprawdzany osobno: spółka mogła budować bazę rok lub dłużej, a wtedy spadek wypadłby poza historię, którą ma aplikacja. Warunki 4 i 5 i tak wymagają płaskiej średniej, która definiuje Fazę 1.

Spółka potrzebuje **co najmniej 40 zakończonych tygodni** historii (30-tygodniowa średnia plus 10 tygodni, w których jest porównywana).

## Co widać w aplikacji

- **Wynik (0–100):** na ile obraz przejścia z Fazy 1 do Fazy 2 jest kompletny. Sześć sprawdzeń, po ok. 17 punktów: ciasna baza; 30-tygodniowa średnia przestała spadać; nie wzrosła już o ponad 10%; cena jest teraz powyżej 30-tygodniowej średniej; cena jest najwyżej 20% powyżej szczytu bazy (wciąż w strefie zakupu); oraz wybicie w ciągu ostatnich czterech tygodni. Gdy wybicie było niedawno, bazę ocenia się tak, jak wyglądała w tygodniu wybicia — inaczej wzrost po wybiciu sprawiłby, że baza wyglądałaby na „nieciasną” akurat wtedy, gdy układ właśnie się włączył.
- **Opis:** „Stage 2 breakout x6.9 vol” w tygodniu wybicia, „Broke out 12d ago, 5/6” później, a w pozostałych przypadkach „3/6 below 30w MA” albo „3/6 setup”.
- **Znaczniki na wykresie:** niebieska kropka z zieloną etykietą „Stage 2 breakout”, umieszczona w **ostatnim dniu sesyjnym tygodnia wybicia**.

## Prawdziwy przykład: Dom Development, grudzień 2022

W grudniu 2022 Dom Development (DOM, GPW) od około pięciu miesięcy poruszał się w bok, w bazie. W **tygodniu od 19 grudnia 2022** (zamkniętym w piątek 23 grudnia) zamknął się powyżej szczytu tej bazy na **122 201 akcjach — 6,9× średniego tygodniowego wolumenu z poprzednich dziesięciu tygodni** — przy płaskiej 30-tygodniowej średniej. Metoda włącza się w tym tygodniu, a opis brzmi „Stage 2 breakout x6.9 vol”. W kolejnych czterech miesiącach kurs wzrósł o około **44%**.

Ta sama spółka wybiła się ponownie w **lipcu 2023**, ale wtedy 30-tygodniowa średnia rosła już stromo od miesięcy — była to przerwa w dojrzałej Fazie 2. To wybicie dało najwyżej ok. +12%, a na koniec roku ok. −1%. Metoda je **odrzuca** z powodu warunku 5.

Oba przypadki są automatycznie sprawdzane w testach aplikacji na prawdziwych cenach tygodniowych. Jeden dobry przykład sam niczego nie dowodzi — liczą się pomiary poniżej.

## Jak to działało w praktyce

- **Jak często się włącza:** rzadko. W całej zapisanej historii GPW włączył się **0,32 razy na spółkę na rok** — 174 razy, na 69 z 292 spółek.
- **Bramka testu wstecznego w aplikacji** (GPW, 288 spółek, pomiar z 2026-09-23): po wybiciu akcja pobiła swój typowy ruch w **51,0%** przypadków w ciągu 10 sesji, ze średnią przewagą **+0,64** punktu procentowego i zyskami 1,27× większymi od strat: tu metoda **przechodzi** bramkę. W ciągu 30 sesji przewaga rośnie do **+2,07** punktu, a zyski są **1,96×** większe od strat, ale odsetek trafień spada do 45,9%, więc formalnie metoda odpada (bramka wymaga ponad 50% zyskownych).
- **W porównaniu z losowym dniem:** losowo wybrany dzień na GPW uzyskuje w tym samym teście +0,59 i +1,20 punktu. Przy 10 sesjach Weinstein jest ledwie powyżej tego poziomu; przy 30 sesjach wyraźnie powyżej.
- **W porównaniu z Minervinim**, mierzonym tak samo: Minervini −0,38 / −0,57, Weinstein +0,64 / +2,07. Kupowanie tam, gdzie trend się *zaczyna*, zamiast tam, gdzie jest już ugruntowany, zamieniło ujemną przewagę w dodatnią.
- **Test kierunku** (2026-09-26, sześć rynków) miał przy 10 sesjach tylko **85** sygnałów Weinsteina — zdecydowanie za mało, by cokolwiek stwierdzić w którąkolwiek stronę.

**Krótko mówiąc:** najbardziej obiecująca z klasycznych metod w aplikacji, ale na skąpych dowodach. Z założenia włącza się rzadko, więc każdy pomiar opiera się na niewielkiej liczbie transakcji.

## Czego aplikacja nie robi

- Nie sprawdza **siły względnej** wobec rynku, z której Weinstein też korzysta.
- Nie prowadzi transakcji. Wyjścia Weinsteina opierają się na zleceniach stop poniżej wsparcia i na 30-tygodniowej średniej; aplikacja nie podaje stopu, celu ani sygnału wyjścia.
- Nie odczytuje fazy całego rynku (Weinstein woli kupować, gdy cały rynek też jest w Fazie 2).

## Źródła

- Stan Weinstein, *Secrets for Profiting in Bull and Bear Markets* (McGraw-Hill, 1988).
- Thomas Bulkowski, [wyniki analizy faz](https://thepatternsite.com/Stages.html) — 440 transakcji posortowanych według fazy zakupu.
