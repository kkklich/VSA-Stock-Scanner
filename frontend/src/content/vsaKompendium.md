# VSA: kompendium metody analizy ceny i wolumenu

## Zakres i sposób czytania tego opracowania

To opracowanie porządkuje materiał kursu VSA z katalogu VSA-films: lekcje 1–30, cztery lekcje z kursu z 2018 r., odpowiadające im transkrypcje SRT oraz mapy wizualne. Kopie map z powielonych folderów potraktowano jako duplikaty, a opracowanie obecne w katalogu źródłowym jako materiał wtórny. Aktualne transkrypcje są dostępne również dla lekcji, które starszy dokument błędnie opisywał jako pozbawione transkrypcji. Nie oznacza to, że każdy z około 189 tys. wyrazów został tu przytoczony ani że obejrzano całe nagrania. Treść syntetyzuje definicje, przykłady, procesy i ograniczenia, które można sprawdzić w tekstach i mapach; dodatkowo wykonano punktową kontrolę klatek z lekcji 8, 25 i 26, a nie pełny przegląd filmów. Odnośniki czasowe prowadzą do zakresów znaczników z odpowiednich plików SRT.

Dla przejrzystości rozróżniam cztery statusy informacji:

- **[K] Kurs** — definicja lub reguła wypowiedziana w transkrypcji. To relacja z materiału edukacyjnego, nie niezależny dowód przewagi rynkowej.
- **[M] Mapa** — szczegół widoczny na schemacie lub mapie. Mapa bywa skrótem i czasem nie zgadza się z narracją.
- **[F] Formalizacja** — neutralny sposób zapisania lub operacyjnego sprawdzenia idei z kursu. Formalizacja pomaga powtarzać analizę, ale sama nie jest regułą obiecaną przez prowadzącego.
- **[L] Luka** — parametr, próg lub zasada, których źródło nie ustala. Implementacja wymaga jawnego wyboru i testu; nie wolno przedstawiać takiego wyboru jako kursowego faktu.

W kolejnych rozdziałach słowo „sygnał” oznacza wzorzec obserwacji, nie pewny zwrot ceny ani automatyczne polecenie kupna lub sprzedaży. Kurs wielokrotnie akcentuje kontekst, reakcję kolejnych barów, tło wyższego interwału i miejsce potencjalnego stop lossu. Pojedynczy wzorzec bez tych elementów jest niepełną informacją.

## 1. Czym jest VSA

VSA to skrót od Volume Spread Analysis, czyli analizy relacji między wolumenem, zakresem ceny i miejscem zamknięcia bara. W odróżnieniu od patrzenia wyłącznie na kształt świecy, VSA pyta, jaki ruch ceny towarzyszył danemu obrotowi i czy rynek osiągnął rezultat, którego można było oczekiwać po takim wysiłku. Dodatkowo pyta, gdzie dany bar pojawia się względem wcześniejszego ruchu: po spadku, po wzroście, przy lokalnym maksimum lub minimum, w korekcie, przy wsparciu albo oporze oraz względem wcześniejszych sygnałów. W kursie fundament ten pojawia się na początku serii i wraca w omówieniu sygnałów, sekwencji i procesu decyzyjnego [K: lekcja 1, SRT; kurs 2018, lekcja 1, SRT 01:18:01–01:21:38].

W języku kursu duży wolumen jest „wysiłkiem”, a ruch ceny i zamknięcie są „rezultatem”. Jeśli na wzroście widać większy obrót, ale cena nie potrafi utrzymać wysokiego zamknięcia, może to świadczyć o podaży absorbującej popyt. Jeśli na spadku obrót maleje i zakres się kurczy, może to świadczyć o słabnącej podaży. To są interpretacje obserwacji, a nie bezpośredni odczyt intencji konkretnego uczestnika. Z wykresu OHLCV nie da się ustalić, kto zawarł każdą transakcję, jaka była jego motywacja ani czy konkretny bank lub fundusz akumulował pozycję.

Kurs opisuje cykl rynku słowami akumulacja, wzrost, redystrybucja, dystrybucja i spadek. Użyteczne jest traktowanie tych pojęć jako hipotez o fazie rynku: po spadku duży obrót przy małym postępie w dół może być interpretowany jako zatrzymywanie podaży; po wzroście duży obrót przy braku postępu w górę może być interpretowany jako wchłanianie popytu. Dopiero późniejsze zachowanie ceny może taką hipotezę wesprzeć albo osłabić. Sam duży obrót nie dowodzi akumulacji, a sama konsolidacja nie dowodzi dystrybucji [K: lekcja 1; podział kategorii: lekcja 7, SRT 00:00:06–00:04:14].

## 2. Dane i budowa świecy

### Zakres (spread)

Spread w materiale oznacza zakres od maksimum do minimum bara: H − L. Nie jest to różnica otwarcia i zamknięcia. Szeroki spread oznacza dużą rozpiętość cen w danym przedziale czasu, wąski — małą. Określenia „szeroki”, „średni” i „wąski” są relatywne: bar porównuje się z innymi z tego samego instrumentu i interwału, zwłaszcza z najbliższymi barami oraz z obszarem, w którym pojawia się sygnał. Kurs nie definiuje uniwersalnej liczby ticków ani procentu, który zawsze odróżnia spread wąski od szerokiego [K; lekcja 1; rozbieżność szczegółowo niżej].

Wąski spread przy dużym wolumenie może oznaczać, że mimo znacznego obrotu cena nie przeszła daleko. VSA opisuje to jako wysiłek bez proporcjonalnego rezultatu. Szeroki spread przy niskim wolumenie może oznaczać, że cena przesunęła się łatwo, przy mniejszym oporze. Żadna z tych obserwacji nie ma znaczenia bez kierunku ruchu i tła.

### Położenie zamknięcia

Wykład i mapy omawiają zamknięcie wysoko, w środku lub nisko zakresu. Operacyjnie można wyrazić względne położenie jako pozycję zamknięcia pomiędzy low i high: (close − low) / (high − low), jeśli zakres jest dodatni [F]. Wtedy 0 oznacza zamknięcie przy minimum, a 1 — przy maksimum. To wyłącznie wygodny opis. W 2018 r. prowadzący mówi o przybliżonej górnej lub dolnej jednej trzeciej i wyraźnie odradza „aptekarskie” traktowanie granic [K: kurs 2018, lekcja 2, SRT 00:09:47–00:10:07]. Jedna z map podaje progi 30/70%; należy je czytać jako wizualny skrót, a nie uniwersalną stałą całego kursu [M]. W późniejszym użyciu przyjęcie granicy, np. 30% lub 70%, jest wyborem implementacyjnym [F/L], który trzeba opisać i zweryfikować.

Kurs czasem opisuje położenie zamknięcia w tercjach, a czasem używa słów „wysoko” i „nisko” jakościowo. Warto więc zachować dokładność: „zamknięcie w dolnej części zakresu” jest obserwacją; „podaż wygrała” jest jej interpretacją.

### Up Bar, Down Bar i kolor korpusu

Up Bar to bar, którego zamknięcie jest wyższe niż zamknięcie poprzedniego bara; Down Bar — niższe [K; lekcja 1]. Ta klasyfikacja porównuje close z poprzednim close. Kolor korpusu świecy porównuje zwykle close z open, więc nie jest tym samym. Bar może zamknąć się powyżej poprzedniego zamknięcia, a jednocześnie poniżej swojego otwarcia; wówczas może być Up Barem, choć świeca ma czerwony korpus. Analogicznie Down Bar może mieć korpus wzrostowy.

Różnica jest praktyczna: klasyfikacja Up/Down pomaga opisać relację do poprzedniego bara i jest używana w definicjach No Supply, No Demand i formacji dwubarowych; kolor korpusu opisuje relację w obrębie świecy. Kolory słupków wolumenu w platformie mogą z kolei zależeć od koloru świecy lub konfiguracji wskaźnika. Nie należy mylić trzech różnych rzeczy: kierunku close wobec poprzedniego close, koloru korpusu wobec open oraz koloru słupka wolumenu.

### Wolumen

Wolumen jest liczony dla konkretnego instrumentu i feedu. Dla kontraktów giełdowych może oznaczać liczbę zawartych kontraktów z danego okresu. W części rynków OTC i na platformach CFD wyświetlana miara może pochodzić od konkretnego dostawcy, np. być wolumenem tickowym albo wolumenem dostępnym dla instrumentu na danej platformie; nie musi reprezentować całego rynku. Lekcje kursu z 2018 r. krytykują tick volume i promują wolumen z rzeczywistych transakcji; wypowiedź o tym, jak platforma xStation wylicza własny wolumen, należy odczytywać jako opis używanego wówczas rozwiązania, nie jako uniwersalną gwarancję dla wszystkich instrumentów i aktualnych platform [K: 2018, lekcja 1, SRT 01:15:10; lekcja 4, SRT 00:34:29–00:37:43].

Należy porównywać podobne rzeczy: ten sam instrument, źródło danych, interwał i — o ile ma to znaczenie — podobną porę sesji. Wolumen kontraktów, wolumen obrotu akcjami, tick count i otwarte pozycje nie są wymienne. Wolumen mierzy kontrakty, które zmieniły właściciela w okresie; open interest to liczba kontraktów futures nadal otwartych. Te dwie wielkości odpowiadają na różne pytania [CME Group, Open Interest](https://www.cmegroup.com/education/lessons/open-interest).

W mapach No Supply i No Demand kolor różowy oznacza wolumen niższy od dwóch poprzednich słupków w użytej konfiguracji platformy. Lekcje mówią wprost o takim ustawieniu [K: lekcja 12, SRT 00:00:06–00:01:19; lekcja 19, SRT 00:00:06–00:01:08]. Kolor różowy nie jest naturalną cechą wolumenu ani samodzielnym sygnałem rynkowym. Algorytm powinien wprost określić, czy chodzi o mniejszą wartość niż na poprzednich dwóch barach, czy też jedynie o kolor wskaźnika. Jeżeli platforma koloruje wolumen odmiennie, trzeba przełożyć znaczenie na liczby.

## 3. Główna logika: effort-result, background i interwał

### Effort-result

Wysiłek–rezultat porównuje relatywny obrót z tym, co zrobiła cena. Duży wolumen to duży wysiłek, ale nie narzuca on kierunku. Rezultat ocenia się poprzez spread, kierunek, zamknięcie i kolejny ruch.

- **Duży obrót i wyraźny postęp w górę, zamknięcie wysoko:** zgodny rezultat dla popytu, o ile tło nie mówi czegoś przeciwnego.
- **Duży obrót na wzroście, ale mały postęp, górny knot lub zamknięcie nisko:** możliwy brak rezultatu z wysiłku, wejście podaży lub absorpcja popytu; do potwierdzenia potrzebne jest zachowanie dalszych barów.
- **Duży obrót na spadku z zamknięciem nisko:** może oznaczać aktywną podaż, ale przy końcu ruchu może też być kulminacją sprzedaży; lokalizacja i późniejsza reakcja są decydujące.
- **Mały obrót i wąski spadkowy bar po wzroście:** możliwa korekta z malejącą podażą; w tle byczym może być neutralny lub sprzyjający wznowieniu trendu.
- **Mały obrót przy próbie wzrostu po dystrybucji:** może oznaczać brak popytu; to słabość dopiero w kontekście, nie dlatego, że jeden słupek jest mały.

No Result From Effort (brak rezultatu z wysiłku) to nazwana w kursie postać tej zasady. Przykład kursowy dotyczy wzrostu na dużym wolumenie, po którym cena nie utrzymuje wysokiego zamknięcia. Gdyby popyt dominował, oczekiwanym rezultatem powinien być bar zamknięty wysoko; niskie zamknięcie interpretuje się jako możliwą przewagę podaży [K: lekcja 17, SRT 00:00:06–00:01:04]. Nie wolno jednak utożsamiać samego wolumenu z „wysiłkiem kupujących”: każda zawarta transakcja ma stronę kupującą i sprzedającą. VSA czyta skutek transakcji na cenie, a nie sumuje niezależnych kupujących i sprzedających.

### Background — tło rynku

Background to kontekst poprzedzający lokalny sygnał. Obejmuje co najmniej:

1. kierunek i strukturę ruchu w analizowanym interwale;
2. to, czy rynek wykonuje impuls, czy korektę;
3. charakter wolumenu na falach wzrostowych i spadkowych;
4. wcześniejsze sygnały siły i słabości oraz ich testy;
5. obszary wsparcia/oporu i relację do wcześniejszych ekstremów;
6. zachowanie w wyższej skali czasowej.

Lokalny No Supply po silnej dystrybucji nie ma automatycznie tej samej wymowy co No Supply po akumulacji. Upthrust po długim wzroście może ostrzegać przed podażą, ale w środku silnego trendu wzrostowego może być tylko nieudaną próbą wybicia, po której trend nadal trwa. Test ma znaczenie tylko wtedy, gdy istnieje obszar podaży lub wcześniejsza siła do sprawdzenia [K: lekcja 13, SRT 00:00:06–00:01:13]. Kurs 2018 zachęca do szukania ostatniej akumulacji lub dystrybucji w tle, a nie izolowania pojedynczej świecy [K: lekcja 2, SRT 00:28:02 i dalej].

Tło nie jest wymówką do zmieniania definicji sygnału po fakcie. Warto rozdzielić dwie notatki: „wzorzec spełnia definicję X” oraz „w tym miejscu interpretuję go jako potwierdzenie/ostrzeżenie, bo wcześniejszy kontekst Y”. Pozwala to uniknąć dopasowywania narracji do wyniku.

### Charakter wolumenu na falach

Lekcja o wolumenie byczym i niedźwiedzim mówi o sekwencji fal, a nie o jednym słupku. Wolumen byczy: ruch wzrostowy ma tendencję do zwiększania obrotu, a cofnięcie do jego zmniejszania. Wolumen niedźwiedzi: spadkowe fale mają większy lub narastający wolumen, a odbicia — malejący. Taka obserwacja pomaga ocenić, czy korekta jest spokojniejsza niż ruch zgodny z trendem [K: lekcja 6, SRT 00:00:06–00:02:39].

Nie oznacza to, że każdy słupek wzrostowy musi być wyższy od poprzedniego albo że każdy pullback w trendzie spadkowym musi mieć malejący wolumen. Wykład opisuje względny charakter fal. [F] Można to badać na odcinkach, porównując typowe obroty impulsu i cofnięcia w tym samym instrumencie i okresie, ale źródło nie podaje okna, uśrednienia ani wartości progowych [L]. Jeśli fal nie da się wiarygodnie wyznaczyć, ocena jest niepewna.

### Skala czasowa

Kurs zaleca najpierw określić kierunek na wyższej skali, a potem szukać miejsca przyłączenia się na niższej. Przykładowo dla decyzji na wykresie 5-minutowym wykres godzinowy może być wyższy; dla decyzji godzinowej — czterogodzinowy [K: lekcja 6, SRT 00:01:49–00:02:39]. Nie jest to nakaz używania wyłącznie tych par. Interwały powinny odpowiadać płynności instrumentu, horyzontowi pozycji i możliwościom obserwacji.

Wyższa skala pomaga ocenić trend i kontekst, ale nie rozwiązuje automatycznie konfliktu. Jeśli wykres dzienny jest wzrostowy, a godzinowy pokazuje dystrybucję, krótkoterminowa decyzja zależy od tego, czy celem jest transakcja przeciw korekcie, czy poszukiwanie wejścia z głównym trendem. Warto zapisać, która skala odpowiada za bias, a która za trigger. Przeglądanie kolejnych interwałów aż do znalezienia pasującego sygnału grozi wyborem po fakcie.

## 4. Klasy sygnałów oraz ich katalog

Lekcja 7 dzieli sygnały siły na akumulacyjne, zbierające podaż oraz testujące podaż, a sygnały słabości na dystrybucyjne, zalewające popyt i testujące popyt [K: lekcja 7, SRT 00:01:25–00:04:14]. Sygnałów siły poszukuje się po spadku lub przy końcu korekty spadkowej w trendzie wzrostowym; sygnałów słabości — po wzroście lub przy końcu korekty wzrostowej w trendzie spadkowym [K: lekcja 7, SRT 00:00:06–00:01:25]. Kurs nie przypisuje bezwyjątkowo każdego wzorca do jednej klasy: Two Bar Reversal może w zależności od wolumenu być sygnałem zbierania albo testowania podaży/popytu. Dlatego poniższy katalog podaje klasę jako interpretację, gdzie zależy ona od wolumenu i kontekstu.

W opisach „potwierdzenie” oznacza późniejszą obserwację, która wspiera hipotezę; nie jest potwierdzeniem statystycznym ani gwarancją wyniku. „Unieważnienie” oznacza zachowanie, które osłabia pierwotną interpretację lub wymaga ponownej oceny. Kurs nie zawsze podaje formalną cenę unieważnienia; jeśli tak jest, zaznaczam to jako lukę.

### Sygnały siły

#### 1. Bag Holding

**Wzorzec [K].** Po spadku pojawia się bar o wąskim spreadzie i bardzo wysokim lub ultra wysokim wolumenie, niewidzianym w porównywalnym fragmencie po lewej stronie wykresu. Przy takim obrocie cena nie schodzi już swobodnie niżej. Kursowy wariant klasyczny opisuje Down Bar zamknięty mniej więcej pośrodku zakresu. Prowadzący dopuszcza jednak także Up Bar, jeśli wąski spread i wolumen wskazują na zatrzymywanie rynku. Różnica ma znaczenie: kolor lub kierunek bara nie powinien przeważyć nad relacją zakres–wolumen–reakcja [K: lekcja 8, SRT 01:58–04:35].

**Interpretacja.** W języku kursu to akumulacja/absorpcja podaży: duży obrót w obszarze niskich cen, ale niewielki dalszy postęp w dół. Wzorzec powinien skłonić do obserwacji, czy rynek potrafi odbić i czy późniejszy test odbywa się na mniejszym wolumenie.

**Wsparcie i porażka.** Odbicie, udany test albo kolejne wysokie zamknięcia wspierają hipotezę. Nowe minima, szerokie Down Bary i rosnący obrót po sygnale osłabiają ją. Sam Bag Holding nie wskazuje punktu wejścia ani konkretnego SL.

#### 2. Selling Climax

**Wzorzec [K].** Po wyraźnym spadku rynek robi szeroki ruch w dół przy wysokim lub ultra wysokim wolumenie, ale nie zamyka się przy samym minimum; zamknięcie w środkowej części zakresu wskazuje na reakcję popytu. Ważne jest porównanie obrotu z niedawnym fragmentem po lewej. Wysoki wolumen, który nie jest wyjątkowy w lokalnym kontekście, nie spełnia automatycznie warunku kulminacji [K: lekcja 8, SRT ok. 08:45–10:06; przykład kontrastowy ok. 14:08].

**Interpretacja.** Kurs interpretuje to jako kulminację sprzedaży, gdzie popyt przejmuje część podaży. Kulminacja nie oznacza „ostatecznego dna” z definicji. Po niej cena może jeszcze ponowić minimum, a rynek powinien pokazać, czy podaż została skutecznie przetestowana.

**Potwierdzenie/unieważnienie.** Odbicie i późniejszy test z mniejszym obrotem wspierają hipotezę. Kolejne szerokie spadki z wysokim wolumenem i zamknięciem nisko sugerują, że podaż nadal dominuje. Kurs nie ustala wymaganego procentowego progu wolumenu [L].

#### 3. Stopping Volume

**Wzorzec [K].** Dwubarowa obserwacja po spadku: pierwszy bar jest Down Bar z narastającym lub wyraźnym wolumenem; po nim pojawia się Up Bar zamknięty wysoko, niekiedy w obszarze korpusu poprzedniego czerwonego bara. Nie należy dodawać warunku, że zamknięcie drugiego bara ma wypaść w górnej części zakresu pierwszego. Wykład mówi o zwiększonym wolumenie pierwszego bara i odpowiedzi popytu w drugim [K: lekcja 9, SRT 00:00:06–01:29].

**Interpretacja.** Podaż napływa, ale nie potrafi utrzymać ceny nisko; popyt absorbuje część wyprzedaży. Nie należy mylić go z dowolnym czerwonym barem o dużym wolumenie: elementem wzorca jest późniejsza odpowiedź.

**Warianty i ocena.** Kurs omawia różne relacje między dwoma słupkami wolumenu; ważniejsza jest reakcja ceny niż mechaniczne żądanie, by wolumen drugiego bara zawsze przewyższał pierwszy. Kolejny test podaży na mniejszym wolumenie jest dodatkowym wsparciem. Nowe dołki na nasilającym się Down Barze osłabiają interpretację.

#### 4. Shakeout

**Wzorzec [K].** Cena gwałtownie schodzi, często narusza wcześniejsze minimum lub dolną granicę zakresu, a następnie zamyka się w górnej jednej trzeciej szerokiego bara. Istotny jest dolny cień, reakcja z dołka i wolumen, który może być znaczny. Kurs wprost mówi, że kolor korpusu nie jest warunkiem: może być zielony lub czerwony [K: lekcja 10, SRT 00:00:06–01:55]. Mapa pokazuje jeden wariant z zielonym korpusem [M]; nie powinno się z tego robić dodatkowego kryterium.

**Interpretacja.** „Wytrząśnięcie” ma testować podaż i wyeliminować uczestników reagujących na wybicie w dół; w tle akumulacyjnym może być mocnym sygnałem, że podaż została odebrana. Podobnie wyglądający bar w środku trendu może mieć inną wymowę.

**Potwierdzenie/unieważnienie.** Odbicie, test z niższym wolumenem lub kolejne Up Bary wspierają hipotezę. Zamknięcie nisko, brak odbicia i nowe minima sugerują, że sprzedający nadal kontrolują ruch. Kurs wspomina też o Shakeout jako teście po wcześniejszej akumulacji — to sekwencja, a nie osobna gwarancja [K: lekcja 10, SRT 01:27–01:55].

#### 5. Two Bar Reversal — strona siły

**Wzorzec [K].** Pierwszy bar: Down Bar, zamknięty nisko. Drugi: Up Bar, którego zamknięcie dochodzi co najmniej do otwarcia pierwszego bara lub wyżej. Kurs pokazuje wariant, w którym wolumen drugiego, wzrostowego bara jest większy od pierwszego; równa wartość również zostaje dopuszczona w dalszym omówieniu [K: lekcja 11, SRT 00:36–01:33 oraz ok. 04:18]. Przy bardzo małym wolumenie całej pary interpretacja może przejść z „zbierania podaży” w stronę testu [K: lekcja 11, SRT 00:06–00:30].

**Interpretacja.** Powrót ceny po spadku pokazuje popyt odbierający podaż. Przy dużym wolumenie może być odczytywany jako zbieranie podaży, przy małym — raczej jako test. Miejsce po spadku, przy wsparciu lub w końcu korekty jest ważniejsze od samego podobieństwa dwóch świec.

**Potwierdzenie/unieważnienie.** Dalszy wzrost i udane testy wspierają wariant siły; kolejne niskie zamknięcia i nowe minima osłabiają go. Jeżeli rzeczywisty close drugiego bara nie spełnia poziomu wskazanego przez kurs, nie należy dopasowywać go po wyglądzie korpusu.

#### 6. No Supply

**Wzorzec [K].** Down Bar z wolumenem niskim, niższym niż na dwóch poprzednich słupkach, przez co w przykładowej konfiguracji platformy jest różowy. Mapa dodaje wąski spread jako typowy obraz [M]; transkrypcja określa przede wszystkim Down Bar oraz różowy/niewielki wolumen [K: lekcja 12, SRT 00:00:06–01:19]. Wąski zakres jest częsty i użyteczny jako cecha kontekstu, ale nie należy bez sprawdzenia podnosić go do warunku koniecznego wypowiedzianego w narracji.

**Interpretacja.** Jest to sygnał testujący podaż, nie akumulacyjny ani samodzielnie zbierający podaż. Spadek na malejącym obrocie może sugerować, że presja podaży słabnie. Najwięcej znaczy po wcześniejszej sile, przy korekcie albo w pobliżu obszaru popytu.

**Potwierdzenie/unieważnienie.** Kolejny Up Bar lub dalsza reakcja wzrostowa potwierdza skuteczność testu [K: lekcja 12, przykłady po 11:04 i 12:25]. Brak reakcji wzrostowej pozostawia sygnał niepotwierdzony. Jeśli po nim pojawia się szeroki Down Bar na rosnącym wolumenie i wybija wsparcie, hipoteza słabnącej podaży traci podstawę. „Różowy” jest ustawieniem porównania wolumenu do dwóch poprzednich, a nie własnością rynku.

#### 7. Test podaży

**Wzorzec [K].** Po wcześniejszej sile cena wraca w obszar, gdzie podaż już była zbierana lub gdzie występowały silne sygnały popytu. Pojawia się bar o średnim lub wąskim spreadzie, niewielkim wolumenie i dolnym cieniu. Korpus nie ma rozstrzygającego znaczenia; kurs pokazuje zamknięcie wysoko jako korzystny wariant [K: lekcja 13, SRT 00:00:06–02:07]. Test może, ale nie musi być jednocześnie klasyfikowany jako No Supply; przykłady pokazują oba przypadki [K: lekcja 13, SRT 00:04:07–00:04:35].

**Interpretacja.** To test w sensie pytania: „czy w tej strefie nadal pojawia się podaż?”. Sam mały wolumen nie odpowiada na to pytanie, dopóki cena nie sprawdzi wcześniejszego obszaru popytu. Wykład podkreśla, że test bez wcześniejszej akumulacji/siły ma małą wartość.

**Potwierdzenie/unieważnienie.** Następujący po nim Up Bar jest potwierdzeniem w rozumieniu kursu. Pojedynczy test bez takiej odpowiedzi pozostaje próbą, nie skutecznym testem. Nowe minima na rosnącym wolumenie przeczą interpretacji. Lekcja 21 rozwija test jako cały proces: po spadku pojawia się siła, rynek odbija, wraca do obszaru i na malejącej podaży sprawdza, czy może kontynuować wzrost [K: lekcja 21, SRT 00:01:07–04:40].

### Sygnały słabości

#### 8. End of the Rising Market

**Wzorzec [K].** Klasyczny End of the Rising Market pojawia się po wzroście jako Up Bar zamknięty mniej więcej w środku zakresu, o wąskim spreadzie i największym wolumenie widocznym w tym ruchu [K: lekcja 14, SRT 01:07–03:16]. Kurs określa formację jako rzadką. Ruch nie postępuje proporcjonalnie do wysiłku.

**Interpretacja.** Możliwa dystrybucja: obrót jest duży, lecz cena przestaje iść w górę. Kurs sugeruje czujność, nie automatyczne otwarcie krótkiej pozycji. Powtarzalne wysokie zamknięcia po sygnale lub kontynuacja wzrostu mogą obalić interpretację końca trendu. Wąski spread sam w sobie nie przewiduje kierunku.

**Potwierdzenie/unieważnienie.** Kolejne słabe reakcje, Upthrust, No Demand albo test popytu wspierają scenariusz słabości. Jeśli rynek utrzymuje wysokie ceny i późniejsze wzrosty uzyskują dobry rezultat przy mocnym wolumenie, teza słabości słabnie.

#### 9. Buying Climax

**Wzorzec [K].** Po rozciągniętym wzroście pojawia się szeroki bar, wyjątkowo wysoki wolumen i brak zamknięcia przy maksimum — często zamknięcie środkowe, z górną częścią zakresu odrzuconą przez podaż [K: lekcja 14, SRT 06:48–09:02]. Istotna jest relacja do wcześniejszego wzrostu i porównanie wolumenu z lokalną historią; nie każdy słupek rekordowy na ekranie jest kulminacją.

**Interpretacja.** Popyt, który dołącza do już rozwiniętego wzrostu, może spotkać podaż. „Kulminacja kupna” nie dowodzi, że cena natychmiast się odwróci. Rynek może zbudować zakres, wykonać test albo kontynuować wzrost.

**Potwierdzenie/unieważnienie.** Kolejne słabe reakcje i nieudane próby wzrostu wspierają dystrybucyjną interpretację. Nowe wysokie zamknięcia i szerokie wzrosty na wolumenie osłabiają ją. Kurs podkreśla znaczenie położenia zamknięcia i kontekstu poprzedzającego ruch.

#### 10. Supply Coming In

**Wzorzec [K].** W ruchu wzrostowym pojawia się Up Bar z górnym cieniem i zwiększonym wolumenem, ale wolumen nie jest największy w obserwowanym wzroście [K: lekcja 15, SRT 00:00:06–01:53]. Jest to ważna cecha odróżniająca kursową definicję od uproszczenia „duży wolumen na wzroście”.

**Interpretacja.** Górny cień oraz wzmożony obrót przy wzroście mogą oznaczać podaż wchodzącą na wyższych poziomach. To ostrzeżenie o możliwym osłabieniu, nie bezpośredni sygnał do sprzedaży. Prowadzący wprost zaznacza, że nie jest to samo w sobie wejście i warto czekać na dalszy układ [K: lekcja 15, ok. 03:13–04:06].

**Potwierdzenie/unieważnienie.** Późniejszy Trap Upmove, No Demand, Upthrust lub słabe zamknięcia wspierają scenariusz. Jeśli rynek robi postęp w górę i utrzymuje wysokie zamknięcia, sam Supply Coming In mógł być jedynie odpoczynkiem w trendzie.

#### 11. Trap Upmove

**Wzorzec [K].** Po wzroście lub wzrostowej korekcie cena wykonuje fałszywą próbę pójścia wyżej, czasem przebija lokalne maksimum, po czym kończy bar nisko przy zwiększonym wolumenie podażowym. Kursowy opis podkreśla zamknięcie nisko jako pułapkę dla późnych kupujących [K: lekcja 16, SRT 00:06–02:14]. Wzorzec może pojawić się przy końcu wzrostowego fragmentu korekty w większym trendzie spadkowym.

**Interpretacja.** Uczestnicy, którzy kupili wybicie, zostają po niewłaściwej stronie, jeśli cena nie utrzymuje ruchu. Nie należy utożsamiać każdego górnego cienia z pułapką.

**Potwierdzenie/unieważnienie.** Następny Down Bar, niższa reakcja i nieudany test popytu wspierają dalszą słabość. Utrzymanie wysokiego zamknięcia, powrót nad szczyt i brak podaży podważają ją. Rozmiar cienia nie zastępuje warunku niskiego zamknięcia na wolumenie.

#### 12. No Result From Effort

**Wzorzec [K].** Po wzrostowym wysiłku — dużym wolumenie — cena nie osiąga oczekiwanego rezultatu: zamiast utrzymać się wysoko, zamyka się nisko lub zostawia odrzucenie od góry. W tej lekcji przykładem jest napływ jeszcze większego wolumenu, lecz słabsze zamknięcie niż na poprzednim barze [K: lekcja 17, SRT 00:00:06–01:04; przykłady od 01:46].

**Interpretacja.** Możliwy sygnał podaży w tle wzrostu, zgodnie z regułą effort-result. Ważne, aby „wysoki wolumen” był wysoki względem porównywanego ruchu, a rezultat faktycznie słaby. Kurs nie nadaje mu uniwersalnego progu.

**Potwierdzenie/unieważnienie.** Dalsze niskie zamknięcia i brak powrotu do wysokich poziomów wspierają słabość. Jeśli cena szybko odzyska zakres i kontynuuje wzrost, początkowe niepowodzenie nie potwierdziło trwałej przewagi podaży.

#### 13. Two Bar Reversal — strona słabości

**Wzorzec [K].** Pierwszy bar jest Up Barem. Drugi to Down Bar i zamyka się na wysokości otwarcia pierwszego lub niżej; wolumen drugiego ma być zbliżony do pierwszego lub wyższy. Wariantem testującym popyt jest sytuacja, gdy wolumen całej pary jest mały w relacji do wcześniejszego ruchu, a drugi bar nadal ma wolumen zbliżony do lub większy niż pierwszy; samo V2<V1 nie oznacza testu [K: lekcja 18, SRT 00:06–01:17, 02:05 i dalszy opis].

**Interpretacja.** Po próbie wzrostu cena wraca poniżej ważnego poziomu pierwszego bara, co wskazuje na potencjalne przejęcie kontroli przez podaż. Miejsce po wzroście i wcześniejszy background słabości są istotne. Jest to lustrzany odpowiednik wariantu siły z lekcji 11.

**Potwierdzenie/unieważnienie.** Dalsze spadkowe zamknięcia wspierają słabość. Gdy cena wraca do sprawdzenia popytu, malejący lub niski wolumen podczas podejścia i następująca reakcja spadkowa są zgodne z nieudanym testem popytu. Nowe wysokie zamknięcia i brak kontynuacji unieważniają ją jako przewagę sprzedających.

#### 14. No Demand

**Wzorzec [K].** Up Bar z wolumenem niższym od dwóch poprzednich słupków — na wskazanej konfiguracji różowy — jest testem popytu [K: lekcja 19, SRT 00:00:06–01:08]. Kurs wyjaśnia go jako próbę wzrostu przy niskim obrocie, która nie pokazuje aktywnego popytu.

**Interpretacja.** Wzorzec jest najbardziej znaczący podczas słabego tła, po wzroście zakończonym dystrybucją albo po wcześniejszym sygnale podaży. W tle akumulacyjnym taki sam Up Bar może być zwykłą niskowolumenową przerwą przed dalszym wzrostem.

**Potwierdzenie/unieważnienie.** Następujący Down Bar lub kolejne niższe zamknięcia wspierają brak popytu. Silny wzrost i poprawiające się wolumeny oznaczają, że domniemany test nie wykazał przewagi podaży. Powtarzające się No Demand to nie automatyczny łańcuch shortów; trzeba oceniać, czy po każdej próbie rynek rzeczywiście odrzuca wyższe ceny.

#### 15. Upthrust

**Wzorzec [K].** Cena narusza lub testuje niedawne wysokie poziomy, lecz wraca z górnym cieniem i zamyka się w dolnej jednej trzeciej zakresu. Kurs rozdziela dwa warianty według obrotu: przy średnim lub większym wolumenie Upthrust może być sygnałem zalewania popytu; przy niskim wolumenie — testującym popyt [K: lekcja 20, SRT 00:00:06–00:01:21]. „Ukryty” Upthrust w niektórych przykładach ma czerwony korpus/Down Bar i górne odrzucenie; nazwa nie zmienia znaczenia zamknięcia i wolumenu.

**Interpretacja.** Cena chwilowo zachęca do kupna nad szczytem, ale nie utrzymuje wyższych poziomów. Pojedynczy Upthrust nie dowodzi zmiany trendu. Lekcja pokazuje przykład, w którym pierwszy Upthrust nie usuwa całego popytu, a dalsza reakcja i testy dopiero wyjaśniają tło [K: lekcja 20, przykłady ok. 09:04–09:49 i podsumowanie ok. 21:38].

**Potwierdzenie/unieważnienie.** Niższe zamknięcia, kolejne nieudane próby wzrostu i No Demand wzmacniają słabość. Wybicie szczytu z utrzymaniem ceny i dobrym rezultatem wzrostowym osłabia ją. Poziom, który formalnie unieważnia interpretację, trzeba określić w danym scenariuszu [L].

## 5. Test jako proces, a nie pojedyncza świeca

Lekcja 21 nadaje testowaniu szczególne znaczenie. Test podaży w pełnej sekwencji zaczyna się po spadku, kiedy na rynku pojawiają się sygnały akumulacji lub siły. Cena odbija; następnie wraca w obszar, w którym wcześniej pojawiła się podaż albo popyt. Jeżeli zejście następuje przy niewielkim lub malejącym wolumenie, a potem rynek odpowiada wzrostem, jest to argument za tym, że podaż została sprawdzona i może być słabsza. Jeżeli wolumen rośnie i spadek nie zatrzymuje się, test nie jest udany [K: lekcja 21, SRT 00:01:07–04:40].

Praktyczny rozkład procesu:

1. **Zidentyfikuj hipotezę.** Co zostało wcześniej odebrane: podaż po spadku czy popyt po wzroście? Wskaż konkretne wcześniejsze sygnały.
2. **Zaznacz obszar testu.** Użyj wcześniejszego zakresu, ekstremum lub strefy, w której pojawiła się reakcja. Nie wybieraj jej dopiero po tym, jak zobaczysz pomyślny wynik.
3. **Obserwuj wysiłek.** Czy powrót do obszaru odbywa się przy spadającym wolumenie, czy przy wzroście wolumenu? Czy spread się rozszerza, czy kurczy?
4. **Poczekaj na odpowiedź.** Dla testu podaży kurs wskazuje późniejszy Up Bar jako potwierdzenie; dla testu popytu potrzebna jest odpowiedź w dół.
5. **Zapisz, co nie zadziałało.** Jeśli cena przechodzi przez obszar na rosnącym wolumenie, pierwotna interpretacja wymaga rewizji.

Kursowe wyjaśnienie historii o dużym uczestniku kontrolującym ilość uwalnianej podaży należy czytać jako model dydaktyczny, a nie dowód tego, kto rzeczywiście zawiera transakcje na oglądanym instrumencie. Z perspektywy analizy wykresu sprawdzalna jest relacja ceny i wolumenu, a nie opowieść o tożsamości uczestnika.

## 6. Sekwencje VSA, WFO i korekty

### Sekwencje wzrostowe i spadkowe

Lekcje 23 i 24 opisują sekwencje jako uporządkowane ciągi trzech sygnałów. Dla wzrostów kurs zestawia sygnał akumulacyjny, sygnał zbierający podaż i test podaży; dla spadków — dystrybucję, zalewanie popytu i test popytu. Odpowiedź testu ma pokazać, czy rynek jest gotowy do ruchu w oczekiwanym kierunku [K: lekcja 23, SRT 00:00:05–03:37; lekcja 24, SRT ok. 00:01:25–02:40]. Sekwencje są sposobem na uporządkowanie sygnałów i zwiększenie spójności procesu, nie automatycznym wejściem.

Źródła nie ustanawiają jednej bezwyjątkowej permutacji dla wszystkich instrumentów. Mapy pokazują kilka kombinacji, a skróty w rodzaju „SZP” nie są wszędzie jednoznaczne: w jednych miejscach oznaczają „zbierające podaż”, a w innych w mapie spadkowej są opisane jako „zalewające popyt”. W tekście używam pełnych nazw, a nie skrótu. Nie należy wnioskować, że każdy z 15 omawianych sygnałów ma przypisane miejsce w sekwencji. Jeśli trzy istotne obserwacje nie wystąpią, ich brak nie może być uzupełniany przez dowolne podobne świece.

Przy ćwiczeniu sekwencji warto zapisywać: sygnał 1 i jego tło; obszar reakcji; sygnał 2; czy rynek dotarł do testu; jak wyglądał wolumen podczas testu; oraz jaka była odpowiedź ceny. To pozwala oddzielić poprawną identyfikację wzorca od wyniku transakcji. Kurs zachęca do sprawdzenia wcześniejszych transakcji pod kątem sekwencji [K: lekcja 23, SRT 01:42–02:20], ale sam postulat, że sekwencje „dramatycznie zwiększą skuteczność”, jest twierdzeniem prowadzącego, nie niezależną statystyką.

### WFO — wolumenowa formacja odwrócenia

WFO z lekcji 25 i 26 porównuje dwa kolejne ekstrema rozdzielone korektą. WFO na spadki ma dwa wierzchołki, z których drugi cenowo jest wyżej; WFO na wzrosty — dwa dołki, z których drugi cenowo jest niżej. W obu opisach pierwsze ekstremum ma większy wolumen, drugi wolumen jest mniejszy niż pierwszy, ale większy niż wszystkie wolumeny na odcinku pomiędzy ekstremami: V1 > V2 > każdy wolumen pomiędzy nimi [K: lekcja 25, SRT ok. 14:37; lekcja 26, SRT 00:46–01:15 oraz 09:20–09:34]. To rozróżnia drugie ekstremum od zwykłej korekty na malejącym obrocie.

WFO nie polega wyłącznie na znalezieniu dwóch szczytów lub dwóch dołków. Kurs podaje minimalną różnicę cenową jednego ticka między ekstremami [K: lekcja 25, SRT ok. 03:06; lekcja 26, SRT ok. 00:38]. Trzeba określić punkty ekstremalne, przedział korekty i porównywalność wolumenów; źródło nie ustala jednak pełnych reguł wykrywania swingów ani minimalnej głębokości korekty [L]. Dla kodu wybór algorytmu wykrywania ekstremów będzie więc formalizacją [F], a nie „oryginalną formułą” VSA.

WFO jest obszarem zainteresowania i może wspierać scenariusz, ale nie przesądza, czy cena natychmiast odwróci cały trend. Materiał omawia różne późniejsze drogi: kontynuację wcześniejszego kierunku po korekcie oraz zmianę kierunku po odbiciu i skutecznym teście [K: lekcja 26, SRT 01:15–02:07]. WFO może zatem dostarczyć hipotezy, a dalszy test i struktura ceny są potrzebne do rozróżnienia wariantów. Kurs wspomina łączenie WFO z inną techniką i geometrią [K: lekcja 25, SRT 05:47–06:12].

### Korekty

Lekcja 27 rozróżnia korektę na wygasającym wolumenie od korekty zakończonej wyraźnym „wybraniem” lub „wylaniem”. W klasycznej korekcie trendowej wolumen cofnięcia jest słabszy niż na impulsie zgodnym z trendem. W drugiej odmianie sam koniec korekty sygnalizuje ponowne wejście popytu lub podaży, czasem przez gwałtowny bar o zwiększonym wolumenie [K: lekcja 27, SRT 00:00:54–01:15 i 06:31–08:17]. Te słowa są opisowe; źródło nie daje liczbowej definicji „wygasającego” wolumenu ani progu, od którego korekta ma być uznana za zakończoną.

Korekta może wyglądać jak ruch przeciwny do trendu, ale też jak konsolidacja lub gwałtowny ruch testujący. Rozróżnia się ją przez strukturę, kierunek dominujących fal i charakter wolumenu; nie wystarczy nazwać każdego przeciwnego ruchu „korektą”. Jeżeli wolumen na spadku w trendzie wzrostowym rośnie, a cena robi szerokie spadkowe bary, hipoteza łagodnej korekty słabnie. Po stronie trendu spadkowego analogicznie należy obserwować odbicia.

## 7. Geometria jako poziom obserwacji

Lekcja 22 nie uczy geometrii jako samodzielnego systemu VSA; pokazuje VSA jako potwierdzenie geometrii. Przykładowe poziomy zniesień wymienione w wykładzie to 38,2%, 41,4%, 50% i 61,8%. Mierzy się od dołka do szczytu lub odwrotnie, lecz sam kontakt z linią nie jest sygnałem do transakcji. Prowadzący podkreśla, że cena może zawrócić na którymś poziomie, nie zatrzymać się na żadnym albo przebić wszystkie [K: lekcja 22, SRT 00:00:06–03:57; mapa i transkrypcja].

Praktyczny proces: najpierw określić, jaki impuls mierzymy i dlaczego; następnie zapisać wcześniejszą siłę lub słabość; potem ocenić, czy dojście do poziomu odbywało się na wolumenie impulsowym czy korekcyjnym; na końcu czekać na reakcję ceny i sygnał VSA. W kursowym scenariuszu nr 5 geometria 0,5 i 0,618 pojawia się również jako strefa planowania, a nie pewne miejsce zwrotu [K: kurs 2018, lekcja 3, SRT 01:00:40–01:03:40]. Jedna mapa odczytuje ręcznie zapisany poziom jako 0,878; narracja mówi wyraźnie 0,5 i 0,618, więc odczyt z mapy nie jest tu wiarygodny.

Opracowanie nie narzuca szerokości strefy wokół fibonacciego, reguły wyboru kotwic, sposobu łączenia wielu poziomów ani sposobu filtrowania fałszywych reakcji. Te elementy trzeba zapisać jawnie przed testem [L]. VSA może opisać zachowanie przy poziomie; nie usuwa niepewności co do tego, czy wybrana geometria jest istotna.

## Świece i bary jako uzupełnienie VSA

Lekcje 3 i 4 przedstawiają formacje świecowe jako dodatkowy filtr miejsca i zachowania ceny. Kurs nie zaleca handlu wyłącznie z kształtu świecy: formacja ma pojawić się w odpowiednim backgroundzie i otrzymać potwierdzenie wolumenowe. Dla młota prowadzący opisuje długi dolny cień, zamknięcie blisko maksimum, korpus nie większy niż około jedna trzecia zakresu, położenie po spadku i brak znaczenia koloru korpusu. Wysoki górny cień dyskwalifikuje klasyczny kształt. Narracja wiąże wejście z zamknięciem potwierdzonego młota, a poziom poniżej jego minimum z invalidacją [K: lekcja 3, SRT 00:00:06–02:50].

Lustrzana spadająca gwiazda pojawia się po wzroście, ma długi górny cień, zamknięcie blisko minimum i mały korpus; duży dolny cień osłabia kwalifikację. Kurs opisuje SL nad maksimum formacji oraz wymóg tła VSA [K: lekcja 4, SRT 00:00:06–02:04]. Pozostałe przykłady w tych lekcjach obejmują przenikanie i gwiazdę poranną po spadku, a także gwiazdę wieczorną, zasłonę ciemnej chmury i objęcie bessy po wzroście. Dla gwiazdy wieczornej mapa nie zawiera osobnego slajdu strategii, więc reguł z sąsiednich formacji nie należy mechanicznie przenosić na nią.

Lekcja 5 odróżnia wejście po zamknięciu świecowego wzorca od wejścia na wybicie. W Inside Bar drugi bar w całości mieści się między high i low pierwszego; dopiero trzeci bar, gdy wybije maksimum lub minimum pierwszego bara, uruchamia kierunkowy wariant [K: lekcja 5, SRT 00:01:01–03:53]. Kolor korpusów nie definiuje tej formacji. Mapa strategii pokazuje krótką konfigurację, ale narracja wyraźnie omawia Inside Bar zarówno na wzrosty, jak i na spadki. Formacje te mogą pomóc wyznaczyć trigger i poziom invalidacji, ale nie zastępują VSA ani oceny kosztu wejścia po wybiciu.
## 8. Proces decyzyjny od obserwacji do transakcji

Lekcja 29 odróżnia ocenę kierunku od scenariusza. Ocena kierunku mówi, czy aktualne tło wydaje się wzrostowe, spadkowe czy niejednoznaczne. Scenariusz ma ponadto określone warunki wejścia, stop lossu i prowadzenia pozycji [K: lekcja 29, SRT 03:33–05:09]. Kierunek bez miejsca wejścia nie jest jeszcze gotowym planem. Można mieć czytelne tło, ale nie mieć sensownego miejsca z bliskim stopem; wówczas „brak pozycji” jest pełnoprawnym wynikiem procesu [K: lekcja 29, SRT 11:03–11:28].

Poniższa kolejność jest formalizacją [F] kursowego procesu, nie cytatem z jednej checklisty:

1. **Sprawdź gotowość i stan decyzji.** Czy jesteś w stanie wykonać wcześniej ustalony plan, czy próbujesz odrobić poprzednią stratę, gonisz rynek albo ignorujesz sygnały? Kurs zaczyna scenariusz od samooceny [K: lekcja 29, SRT 01:05–01:34].
2. **Wybierz instrumenty i ramy czasowe.** Lepiej rozumieć jeden rynek niż gubić się równocześnie w wielu pozycjach [K: lekcja 28, SRT 08:26–09:15]. Zaznacz, który interwał określa trend, a który ma dostarczyć wejścia.
3. **Zdefiniuj tło.** Oznacz trend, fale impulsu i korekty, poprzednie sygnały, strefy oraz jakość danych wolumenowych. Nie nazywaj tła akumulacją tylko dlatego, że jest to konsolidacja.
4. **Zapisz hipotezę.** Np. „spadek do obszaru poprzedniej siły ma charakter korekcyjny; chcę zobaczyć test podaży i odpowiedź popytu”. Określ też, jaka obserwacja obali hipotezę.
5. **Wyznacz trigger.** Może nim być potwierdzony test, sygnał w sekwencji albo inny jawny element scenariusza. Nie otwieraj pozycji wyłącznie dlatego, że dotknięto fibonacciego albo wystąpił jeden słupek różowego wolumenu.
6. **Ustal poziom invalidacji i stop.** SL ma być powiązany z punktem, po którego naruszeniu pierwotny powód wejścia nie jest już aktualny, a nie dobrany po to, by uzyskać dogodną wielkość pozycji.
7. **Policz wielkość pozycji i koszt.** Uwzględnij wartość punktu/ticka, walutę kwotowania, spread, prowizję, ewentualne finansowanie, minimalny lot i przewidywany poślizg.
8. **Oceń relację zysku do ryzyka.** Kurs używa 3:1 jako docelowej minimalnej proporcji lub ilustracji scenariusza, nie jako prawa rynku. Zapisz, czy potencjalny cel ma podstawę w wykresie i czy koszty nie pochłaniają przewagi.
9. **Zarządzaj według zasad zapisanych przed wejściem.** Kursowe przykłady obejmują przesunięcie stopu na zero i wyjście przy silnym sygnale przeciwnym; dokładna reguła, kiedy to zrobić, powinna być sprecyzowana w testowanej strategii.
10. **Zapisz wynik i klasyfikację.** Oddziel poprawne wykonanie planu od wyniku pojedynczej transakcji. Błąd planu, błąd danych, błąd wykonania i normalna strata to różne kategorie.

### Scenariusz nr 5 jako przykład procesu, nie wzorzec uniwersalny

W lekcji 29 warunkiem wyboru „ważnego miejsca” jest jeden z wariantów: zakończenie ABC, WFO albo poziom geometrii [K: lekcja 29, SRT 12:38–14:22]. Nie są one trzema warunkami, które muszą wystąpić naraz. Dalsze etapy konkretnego scenariusza są bardziej szczegółowe: brak silnej podaży przy wcześniejszym szczycie, korekcyjne zejście wolumenu, formacja świecowa potwierdzona sygnałem VSA oraz potencjał co najmniej 3R [K: lekcja 29, SRT 16:04–18:04; szczegóły m.in. 16:24, 16:46, 17:12 i 17:41–18:04]. Scenariusz ilustruje zależność między kierunkiem, strefą i wejściem; nie należy automatycznie przenosić go na każdą pozycję.

### Plan transakcji jako karta przed wejściem

Minimalny zapis, który pozwala później sprawdzić proces, może zawierać:

| Pole | Co zapisać |
|---|---|
| Instrument i feed | Symbol, typ instrumentu, dostawca wolumenu, sesja i interwał |
| Tło | Trend/zakres, impulsy i korekty, istotne sygnały z wyższej skali |
| Hipoteza | Co rynek może robić i jakie dane ją wspierają |
| Wzorzec | Nazwa sygnału/sekcji, bary i dokładne kryteria, które spełnia |
| Trigger | Obserwowalny warunek, który uprawnia do wejścia |
| Invalidacja/SL | Poziom i uzasadnienie; jaki ruch unieważnia hipotezę |
| Wielkość | Kapitał ryzyka, odległość stopu, wartość punktu, koszty, ilość |
| Cel i zarządzanie | Poziom celu lub reguła wyjścia; warunki przesunięcia stopu |
| Niepewność | Brakujący sygnał, rozjazd interwałów, ograniczenia danych, bliskie makro |
| Rezultat | R, koszty, poślizg, wykonanie planu, zrzut wykresu z chwili decyzji |

## 9. Ryzyko, stop loss, wielkość pozycji i koszty

### Stop loss i wielkość pozycji

Kurs słusznie oddziela ocenę kierunku od miejsca stop lossu i zarządzania ryzykiem. Lekcja 28 opisuje procent kapitału narażany na pojedynczą transakcję: jako punkt odniesienia dla początkujących pada 0,5%, a dalsze wartości zależą od doświadczenia; w różnych miejscach pojawiają się 1%, do 1,5% oraz 2,5% jako pułap dla doświadczonych. To nie jest spójna, uniwersalna rekomendacja. Należy czytać te wartości jako wypowiedzi kursowe i przykłady, nie zalecenie dla odbiorcy [K: lekcja 28, SRT 13:30–14:20, 15:55–16:58, 22:03–23:02]. Ważniejsze jest ograniczenie z góry kwoty straty, a nie dopasowanie wykresu do arbitralnego procentu.

Ogólna arytmetyka planowania [F]:

- kapitał przeznaczony na stratę = kapitał rachunku × zadany procent ryzyka;
- strata na jednostkę przed kosztami = abs(wejście − SL) × wartość pełnego punktu albo abs(wejście − SL) / rozmiar ticka × wartość jednego ticka;
- ilość = zaokrąglenie w dół do kroku ilości: kwota ryzyka / strata na jednostkę z kosztami wejścia i wyjścia.

Przykład wyłącznie arytmetyczny, nie rekomendacja instrumentu: kapitał 10 000 jednostek waluty rachunku, ryzyko 1% daje 100; wejście 100, SL 95, wartość punktu na jednostkę 1, koszt pełnego obrotu 0,20 na jednostkę. Ryzyko jednostkowe wynosi 5 + 0,20 = 5,20, więc 100 / 5,20 = 19,2307; przy kroku ilości 0,01 można zaokrąglić w dół do 19,23. Luka i poślizg mogą sprawić, że faktyczna strata przekroczy tę wartość. To nie jest kompletny algorytm dla każdego brokera. Trzeba uwzględnić mnożnik kontraktu, minimalny krok wolumenu, walutę rozliczeniową, prowizję, spread, przewalutowanie i możliwość luki. Jeżeli po uwzględnieniu minimum wielkości pozycji ryzyko przekracza limit, poprawną decyzją może być pominięcie transakcji. Nie należy zawężać stopu wyłącznie po to, aby „zmieścić” za dużą pozycję.

SL powinien odpowiadać technicznej invalidacji scenariusza. Zbyt ciasny stop może zostać trafiony przez normalny szum; zbyt szeroki wymaga mniejszej pozycji. Stop zleceniowy nie gwarantuje wykonania po stop price: po aktywacji zlecenie rynkowe może zostać zrealizowane gorzej przy szybkim ruchu lub luce [FINRA, Stop Orders](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets). Mechanika i dostępne typy zleceń zależą od rynku, brokera i produktu.

### Relacja zysku do ryzyka

3:1 pojawia się w kursie jako minimalny potencjał zysku względem ryzyka w omawianym scenariuszu i przykładach prowadzenia transakcji [K: lekcja 28, SRT ok. 35:48–37:34; kurs 2018, lekcja 3, SRT 01:09:35]. Sama relacja celu do stopu nie mówi, czy strategia jest zyskowna. Przy prostym założeniu jednej wielkości zysku 3R i straty 1R próg rentowności bez kosztów wynosi 25% wygranych, jeżeli nie ma pozycji zamkniętych na zero. Prowizje, poślizg, różne wyjścia, luki i niepełne wykonania zmieniają tę arytmetykę.

Przykład z lekcji 28 o serii 20 transakcji i ilustracyjnej kombinacji zysków/strat ma pokazać rolę rozkładu ryzyka, nie dowodzić przewagi metody. Każde takie wyliczenie powinno jawnie określać założenia: czy procent ryzyka jest liczony od zmiennego kapitału, czy stałego; czy uwzględnia koszty; jak traktuje breakeven; ile było obsunięcia; jakiej próbki użyto. Mała próbka i wybrane przykłady z wykresu nie pozwalają ocenić przyszłej skuteczności.

### Koszty i makro

Transakcja ma koszt spreadu, prowizji, finansowania overnight, ewentualnego rolowania kontraktu, poślizgu oraz wykonania przy niskiej płynności. Jeżeli sygnał i stop są blisko siebie, koszt może istotnie pogorszyć rzeczywisty stosunek zysku do ryzyka. W backteście należy stosować koszty zgodne z instrumentem i okresem; nie wolno wnioskować z danych CFD o całym rynku, jeśli źródło wolumenu jest wyłącznie brokerskie.

Lekcja 30 omawia cztery ogólne rodzaje reakcji na dane: ruch zgodny z oczekiwaniem, początkowy ruch zgodny z danymi, po którym cena odwraca; początkowa reakcja przeciwna do oczekiwania i silna kontynuacja; oraz opóźniona lub niejednoznaczna reakcja [K: lekcja 30, SRT 00:00:14–01:39]. Zamiast zakładać, że „dobre dane muszą podnieść cenę”, kurs zachęca do obserwacji reakcji ceny i wolumenu. Żadnego stałego czasu oczekiwania po publikacji źródło nie określa [L]. Przed publikacją trzeba uwzględnić możliwy spread, lukę, szybkie zmiany ceny i ryzyko poślizgu.

## 10. Formalizacja metody w kodzie i jej granice

Kod może powtarzalnie obliczać cechy baru i oznaczać potencjalne wzorce. Nie może sam ustalić, że rynek „akumuluje”, jeśli nie zdefiniowano i nie przetestowano reguł dla tła, swingów, progów spreadu, porównywania wolumenu, potwierdzenia i unieważnienia. Każdy parametr musi mieć status: kursowy, jawnie przyjęty przez implementację lub nieobsługiwany.

Minimalna, audytowalna warstwa danych powinna zawierać OHLCV, timestamp, symbol, interwał, jednostkę ceny, źródło wolumenu i zasady sesji. Sprawdź brakujące świece, duplikaty, zmianę strefy czasowej, okresy bez transakcji i ewentualne zmiany kontraktu. Świeca ze spreadem zero wymaga ostrożnej obsługi, bo względne położenie zamknięcia dzieliłoby przez zero. Przyszłe dane nie mogą przeciekać do obliczenia sygnału ani do etykiety wstecznej.

Praktyczne rozdzielenie implementacji:

| Warstwa | Przykłady | Status |
|---|---|---|
| Cechy bazowe | H − L, close vs previous close, pozycja close, wolumen | [F], bez progu |
| Klasyfikacja relatywna | Wąski/szeroki spread; niski/wyjątkowy wolumen | [L], trzeba ustalić okno/metodę |
| Wzorce | No Supply, Upthrust, Two Bar Reversal, WFO | Kryteria kursowe plus formalizacja |
| Kontekst | trend, korekta, obszar testu, wsparcie | Częściowo [K], swing extraction [L] |
| Potwierdzenie | kolejny bar, retest lub sekwencja | [K] kierunkowo, timing [L] |
| Ryzyko | poziom SL, kwota ryzyka, ilość, koszty | [F], zależne od kontraktu |
| Ocena wyniku | forward test, koszty, drawdown, stabilność | Wymaga danych, nie wynika z definicji VSA |

Przykładowe decyzje wymagające jawnego opisu:

- Jaka liczba barów lub jaka lokalna charakterystyka definiuje „wąski” spread?
- Jak wyznaczasz „bardzo wysoki” wolumen: lokalne maksimum, percentyl, medianę, z-score, czy tylko porównanie wzrokowe? Kurs nie narzuca jednej metody [L].
- Czy „różowy” wolumen jest dokładnie niższy niż dwa poprzednie słupki? Tak jest opisany w kursie, ale rzeczywisty wskaźnik trzeba sprawdzić.
- Jak wykrywasz dwa ekstrema WFO i zakres korekty bez użycia przyszłych barów?
- Jak długo czekasz na potwierdzenie i co robisz, gdy go nie ma?
- Czy backtest uwzględnia prowizję, spread, poślizg, lukę, zmianę kontraktu i brak płynności?
- Czy sygnały są liczone po zamknięciu bara? Jeżeli tak, wejście może nastąpić dopiero później niż cena zamknięcia sygnału.

Dopiero po zapisaniu tych wyborów warto badać wyniki. Należy oddzielić okres projektowania od walidacji, sprawdzić różne fazy rynku i unikać strojenia progów na pojedynczych przykładach z kursu. Rozsądna analiza obejmuje liczbę transakcji, wynik po kosztach, średnie R, obsunięcie, rozkład strat, zależność od instrumentu i interwału, a także zachowanie poza próbką. To są zasady oceny algorytmu [F], nie deklaracja, że VSA z góry daje dodatnią wartość oczekiwaną.

## 11. Co źródła mówią, a czego nie dowodzą

Kurs mówi o „smart money”, profesjonalnych uczestnikach, akumulowaniu akcji, wchłanianiu podaży i zamykaniu uczestników po przeciwnej stronie. To użyteczne metafory do wyobrażenia sobie możliwej dynamiki rynku, ale z pojedynczego słupka wolumenu nie można zidentyfikować, kim były strony transakcji ani czy działała jedna skoordynowana grupa. Każda transakcja ma kupującego i sprzedającego. Wysoki wolumen przy małym spreadzie pokazuje aktywność i ograniczony postęp, nie nazwy lub intencje uczestników.

Wszystkie przykłady na wykresach są ilustracjami. Nie stanowią testu z kompletnym zbiorem decyzji, zleceń, kosztów i strat. Kategoryczne twierdzenia o wzroście skuteczności, powtarzalności WFO albo zachowaniu profesjonalistów należy odróżniać od definicji, którą można sprawdzić w danych. To opracowanie nie zakłada rentowności VSA i nie obiecuje wyników. Wykresy historyczne nie mówią, ile podobnych konfiguracji zawiodło ani czy reguła działa po kosztach w nowych okresach.

Szczególną ostrożność zachowaj wobec:

- wyboru wyłącznie udanych przykładów, które widać na slajdach;
- zmiany definicji sygnału po zobaczeniu kolejnych świec;
- mylenia korelacji z przyczynowością i interpretacji z pomiarem;
- przenoszenia wolumenu z jednego instrumentu lub feedu na inny;
- częstego przeglądania wielu interwałów i wielu progów aż do uzyskania korzystnego obrazu;
- liczenia skuteczności wyłącznie z transakcji zakończonych zyskiem;
- przypisywania każdej formacji „smart money” bez danych o uczestnikach.

Kurs ma wartość przede wszystkim jako katalog pytań do wykresu: jaki był wysiłek, jaki był rezultat, jak cena się zamknęła, co wydarzyło się wcześniej i co rynek zrobił potem? Te pytania można przekształcić w spójną i kontrolowalną procedurę. Odpowiedź musi jednak pozostać hipotezą do czasu, aż zostanie sprawdzona na danych i wykonaniu.

## 12. Ćwiczenia do nauki i walidacji

### Ćwiczenie A — opis baru bez interpretacji

Wybierz 50 losowych barów z jednego instrumentu. Zapisz dla każdego: spread względem 10 poprzednich barów, Up/Down według close wobec poprzedniego close, położenie close w zakresie, wolumen względem dwóch poprzednich i względem ostatniego lokalnego fragmentu. Nie wpisuj jeszcze „akumulacja”, „dystrybucja” ani „smart money”. Celem jest nauczyć się odróżniać obserwację od narracji. Porównaj własne określenie spreadu wąski/średni/szeroki z regułą liczbową, którą zdecydujesz się formalnie przetestować.

### Ćwiczenie B — sygnał i kontekst

Dla każdego sygnału z katalogu znajdź na wykresie kilka przykładów, w tym te, które zakończyły się przeciwnie do oczekiwania. Zasłoń przyszłe bary. Zapisz definicję, tło, hipotezę, warunek dalszego potwierdzenia i unieważnienie. Dopiero potem odsłoń przyszłe dane. Dzięki temu zobaczysz, czy nazwa wzorca rzeczywiście pomaga podejmować decyzje przed wynikiem, czy tylko łatwo opisuje historię po fakcie.

### Ćwiczenie C — test podaży jako sekwencja

Zaznacz wcześniejszą siłę po spadku, odbicie, obszar retestu, wolumen podczas zejścia i następującą odpowiedź. Oznacz test jako skuteczny tylko wtedy, gdy spełnia przyjętą wcześniej definicję i pojawia się reakcja. Policz osobno: wszystkie próby, próby potwierdzone i próby zanegowane. Nie pomijaj sytuacji, w których test nie przyniósł wzrostu.

### Ćwiczenie D — audyt VSA w kodzie

Przygotuj syntetyczne bary ręcznie: narrow spread + high volume; wide spread + low volume; Up Bar z czerwonym korpusem; Down Bar z zielonym korpusem; wolumen niższy od dwóch poprzednich; świeca z H=L. Sprawdź, czy kod klasyfikuje cechy niezależnie od koloru korpusu, prawidłowo oblicza położenie close i obsługuje zakres zerowy. Każdy wygenerowany sygnał powinien mieć powód w postaci cech źródłowych, aby dało się go audytować.

### Ćwiczenie E — poza próbą i koszty

Zdefiniuj reguły przed badaniem. Podziel dane chronologicznie na próbę do projektowania i późniejszy okres walidacji. Zmierz bazowy wariant bez sygnału, potem sprawdź, czy filtr VSA poprawia wynik po kosztach, w różnych fazach i na nieużytych wcześniej instrumentach. Raportuj rozkład wyników, a nie tylko odsetek zyskownych transakcji. Jeśli wynik zależy od jednego progu, jednego rynku albo kilku najlepszych przykładów, jego stabilność jest słaba.

### Ćwiczenie F — dziennik decyzji

Przez co najmniej jeden pełny cykl ćwiczeń zapisuj także decyzje o braku wejścia. Dołącz zrzut wykresu z chwili planowania, feed, interwał, hipotezę, poziom unieważnienia i koszt. Po fakcie oceniaj oddzielnie: jakość hipotezy, jakość wykonania oraz rezultat. Jedna zyskowna transakcja może być błędna proceduralnie; jedna strata może być zgodna z planem.

## 13. Najważniejsze rozbieżności map, narracji i dokumentów wtórnych

| Temat | Co wynika z narracji / aktualnego materiału | Co upraszcza lub błędnie podaje mapa albo starszy dokument | Jak traktuje to kompendium |
|---|---|---|---|
| Dostępność transkrypcji | Są aktualne TXT i SRT dla lekcji 1–30 oraz 4 pozycji kursu 2018 | Starsze opracowanie twierdzi, że transkrypcja istnieje tylko dla lekcji 1; mapy 2–30 powtarzają informację „bez audio/transkrypcji” | Za aktualne przyjęto dostępne transkrypcje; starszą informację uznano za nieaktualną |
| Spread w lekcji 1 | Definicja z mapy/slajdu i powtarzanych wypowiedzi: high–low | Pojedynczy fragment transkrypcji myli spread z open–close | Przyjęto H−L, a pojedyncze O−C potraktowano jako lapsus/ASR |
| Granica close high/low | Kurs 2018 mówi o przybliżonej tercji i ostrzega przed aptekarską precyzją | Mapa rysuje 30/70% | 30/70 można użyć jako jawnej formalizacji, a nie ponadczasowego progu kursu |
| Bag Holding | Klasyczny Down Bar; prowadzący dopuszcza także Up Bar w odpowiednim obrazie zakresu i wolumenu | Stary algorytm/mapa mogą sugerować wyłącznie jeden typ bara | Uwzględniono oba warianty; istotne są wąski spread, wyjątkowy wolumen i reakcja |
| Bag Holding — który bar ma najwyższy wolumen | Punktowa kontrola klatki lekcji 8 przy 02:30 pokazała wzrost wolumenu w trzech barach, z maksimum pod ostatnim małym barem | Mapa pozostawiała niepewność, a stary opis wskazywał możliwość maksimum pod środkowym barem | Wskazano rozstrzygnięcie z kontroli jednej klatki; nie deklarowano obejrzenia całego filmu |
| Shakeout | Narracja mówi, że korpus może być zielony lub czerwony; ważne jest zamknięcie wysoko | Mapa rysuje korpus zielony | Kolor nie jest warunkiem |
| Inside Bar | Narracja definiuje zakres pierwszego bara, drugi bar w całości wewnątrz i wybicie przez trzeci; pokazuje ruchy w obie strony | Jedna mapa/strategia ilustruje tylko wejście w dół, podczas gdy mapa definicji pokazuje wybicie w górę | Kierunku nie uogólniono z pojedynczej ilustracji; lekcja 5 wymaga wybicia zakresu pierwszego bara |
| Mapa kursu 2018, lekcja 2 | Narracja mówi o przybliżonej tercji | Mapa sugeruje dokładne 30/70 i może implikować automatyczne wejście po T | Sygnał testu wymaga reakcji; sama strzałka nie potwierdza zlecenia |
| Mapa kursu 2018, lekcja 3 | SRT wymienia poziomy 0,5 i 0,618 oraz odróżnia scenariusz nr 5 od piątej fali | Mapa odczytuje ręczny zapis jako 0,878, a „5” interpretuje niepewnie | Pierwszeństwo narracji; zapis 0,878 nie został użyty |
| Zarządzanie kapitałem 2018 | SRT omawia SL, potencjał 3:1 i dopasowanie stopu do kapitału | Mapa sugeruje, że brak reguł kapitałowych | Wzięto pod uwagę narrację; podano jej liczby jako przykłady z kursu |
| Sekwencje spadkowe | Narracja opisuje dystrybucję, zalewanie popytu i test popytu pełnymi kategoriami | Skrót „SZP” w mapach bywa niejednoznaczny | Użyto pełnych nazw; nie wymyślono mapowania każdego sygnału do klasy |
| WFO | Lekcje 25 i 26 opisują relację wolumenów dwóch ekstremów i korekty | Mapy pokazują geometrię, lecz implementacja ekstremów nie jest liczbowo zdefiniowana | Warunek relacji wolumenów zachowano; sposób wykrywania swingów oznaczono jako formalizację |

W lekcji 2018, mapa nr 4 twierdzi, że zagadnienie źródła wolumenu pojawia się tylko w jednym miejscu całego materiału. SRT lekcji 1 ma jednak wypowiedź o wolumenie tickowym i rzeczywistym już przy 01:15:10. Lekcja 4 dodatkowo odróżnia tick, wolumen giełdowy rzeczywistych kontraktów futures oraz określony w wykładzie „realny” wolumen XTB, opisany jako oparty na rzeczywistym wolumenie danego waloru [K: 2018, lekcja 4, SRT 00:34:30–00:39:12, w tym odrzucenie tick volume 00:35:53–00:36:29]. To historyczne wyjaśnienie używanej platformy, nie obietnica, że podobne źródło jest obecnie dostępne dla każdego instrumentu. Mapa pomija także wyraźną uwagę, że wolumen kupna i sprzedaży w transakcji jest równy; kolor słupka nie jest miarą netto kupujących [K: 2018, lekcja 4, SRT ok. 00:25:58].

Wszystkie cztery mapy kursu 2018 powstały na podstawie obrazu; w razie konfliktu szczegółów rozstrzygających narracyjnie pierwszeństwo ma odpowiedni SRT.

## 14. Mapa materiału źródłowego: lekcje 1–30 oraz kurs 2018

Tabela pomaga wrócić do źródła. Czas wskazuje weryfikowany punkt lub fragment SRT, a nie czas całej lekcji. Przy zakresach opisanych jako „w dalszej części” należy korzystać z nagłówka SRT i wyszukać wymieniony temat.

| Materiał | Temat i użycie w kompendium | Orientacyjny znacznik SRT |
|---|---|---|
| Lekcja 1 | VSA, spread, wolumen, close, tło i sposób czytania wykresu | Odpowiednie pojęcia w pierwszej części; spread H−L omawiany na początku |
| Lekcja 2 | Typy wykresów, tło decyzyjne, HLC/OHLC i konfiguracja słupków | Tematy początku wykładu |
| Lekcja 3 | Wzrostowe formacje świecowe: m.in. młot, przenikanie, gwiazda poranna i objęcie hossy; nacisk na VSA jako potwierdzenie | Młot 00:06–02:50; pozostałe formacje w dalszej części |
| Lekcja 4 | Spadkowe formacje: spadająca gwiazda, gwiazda wieczorna, zasłona ciemnej chmury, objęcie bessy; wolumen jako potwierdzenie | Spadająca gwiazda 00:06–02:04; pozostałe formacje od ok. 11:35 |
| Lekcja 5 | Formacje barowe i wejście na wybicie, m.in. Inside Bar | Definicja wybicia przez trzeci bar ok. 01:46–03:53 |
| Lekcja 6 | Byczy/niedźwiedzi wolumen na falach i ocena kierunku | 00:06–02:39 |
| Lekcja 7 | Kategorie i miejsca oczekiwania sygnałów VSA | 00:06–04:14 |
| Lekcja 8 | Bag Holding i Selling Climax | Bag Holding 01:58–04:35; Selling Climax ok. 08:45–10:06 |
| Lekcja 9 | Stopping Volume | 00:06–01:29 |
| Lekcja 10 | Shakeout | 00:06–01:55 |
| Lekcja 11 | Two Bar Reversal po spadku | 00:06–01:33 |
| Lekcja 12 | No Supply | 00:06–01:19; przykłady testowania w dalszej części |
| Lekcja 13 | Test podaży i warunek wcześniejszej siły | 00:06–02:07 |
| Lekcja 14 | End of the Rising Market i Buying Climax | End of Rising Market 00:20–03:16; BC ok. 06:48–09:02 |
| Lekcja 15 | Supply Coming In | 00:06–01:53; zastrzeżenie o niewchodzeniu bez dalszego sygnału ok. 03:13–04:06 |
| Lekcja 16 | Trap Upmove | 00:06–02:14 |
| Lekcja 17 | No Result From Effort | 00:06–01:04; przykłady od ok. 01:46 |
| Lekcja 18 | Two Bar Reversal po wzroście | 00:06–01:17 |
| Lekcja 19 | No Demand | 00:06–01:08 |
| Lekcja 20 | Upthrust i wariant wolumenowy | 00:06–00:47 |
| Lekcja 21 | Testowanie podaży jako proces | 00:35–04:40 |
| Lekcja 22 | VSA jako potwierdzenie geometrii | 00:06–03:57 |
| Lekcja 23 | Sekwencje wzrostowe | 00:05–03:37 |
| Lekcja 24 | Sekwencje spadkowe | Wprowadzenie ok. 00:05; przykładowe układy ok. 01:25–02:40 |
| Lekcja 25 | WFO na spadki | Warunek relacji wolumenów ok. 14:37; rola w scenariuszu 05:47–06:12 |
| Lekcja 26 | WFO na wzrosty | Drugi dołek i wolumen 00:46–01:15; rola formacji 01:15–02:07; warunek 09:20–09:34 |
| Lekcja 27 | Rodzaje korekt | Korekta na wygasającym wolumenie 00:54–01:15; wybranie/wylanie 06:31–08:17 |
| Lekcja 28 | Ryzyko, kapitał, stop loss i prowadzenie | Początkujący/zaangażowanie 13:30–14:20; kwota ryzyka 15:55–16:58; prowadzenie 35:48–37:34 |
| Lekcja 29 | Scenariusz nr 5 i decyzja od kierunku do pozycji | Samoocena 01:05–01:34; rozdział biasu/scenariusza 03:33–05:09; ważne miejsce 12:38–14:22; warunki 16:04–18:04 |
| Lekcja 30 | Reakcje rynku na dane makro | 00:14–01:39; przykład reakcji wolumenowej od ok. 03:17 |
| Kurs 2018, lekcja 1 | Podstawy VSA, spread, wolumen rzeczywisty i byczy/niedźwiedzi | 01:15:10; 01:18:01–01:21:38; przykład 01:25:35 |
| Kurs 2018, lekcja 2 | Prawa rynku, akumulacja/dystrybucja, background | 00:09:47–00:10:07; 00:12:58–00:19:03; 00:28:02 |
| Kurs 2018, lekcja 3 | Kompletny scenariusz, geometria i ryzyko | 01:00:40–01:03:40; 01:09:35–01:10:19 |
| Kurs 2018, lekcja 4 | Sygnał jako punkt koncentracji w procesie | 00:07:52; 00:34:29–00:39:12; 00:43:05–00:45:32 |

W mapie lekcji 8 część tytułu sygnału jest transkrybowana jako „Back Holding”; w kompendium ujednolicono zapis do Bag Holding. W kilku SRT automatyczne rozpoznawanie mowy błędnie zapisuje angielskie terminy, np. Up Bar jako „abbar”, Down Bar jako „dąbar”, Two Bar Reversal fonetycznie, lub No Result jako „No Resort”. Nazwy w tekście ujednolicono, nie zmieniając opisu merytorycznego.

## 15. Słownik skrótów i rozróżnień

| Termin | Znaczenie w tym opracowaniu |
|---|---|
| Bar | Jednostka danych z jednego interwału; świeca lub słupek zależnie od wykresu |
| Spread | High minus low bara, czyli pełen zakres ceny |
| Close high / close low | Położenie zamknięcia w relacji do zakresu bara |
| Up Bar / Down Bar | Close wyżej/niżej niż close poprzedniego bara |
| Effort-result | Porównanie relatywnego wolumenu z ruchem i zamknięciem ceny |
| Background | Kierunek, struktura fal, wcześniejsze sygnały i położenie w wyższej skali |
| Test podaży / popytu | Powrót ceny do obszaru sprawdzającego, czy dana strona nadal wywiera presję |
| Akumulacja / dystrybucja | Kursowa interpretacja możliwego przejmowania podaży/popytu; nie bezpośredni odczyt intencji |
| WFO | Wolumenowa formacja odwrócenia z dwoma ekstremami, korektą i relacją wolumenów |
| SL / stop loss | Poziom planowanego wyjścia ograniczający stratę; cena wykonania może się różnić |
| R | Jednostka początkowego ryzyka pozycji, używana do porównania wyników |

## Zakończenie

Najbardziej wiernym streszczeniem VSA w tych materiałach jest dyscyplina zadawania pytań o cenę i obrót: jak daleko rynek przeszedł, przy jakim wolumenie, gdzie zamknął się bar, co wydarzyło się przed nim i jaka odpowiedź nastąpiła potem. Kontekst oraz kolejne reakcje są równie ważne jak sama nazwa sygnału. Jeśli proces jest formalizowany w Pythonie, każde nieokreślone w kursie ustawienie należy ujawnić jako wybór projektowy; to pozwala porównać wynik programu z rzeczywistą treścią metody i uczciwie ocenić jej ograniczenia.




## Dodatek A. Od opisu rynku do programu Python

### A.1. Co właściwie jest obliczane

VSA nie ma jednej funkcji, której wynik jednoznacznie określa decyzję „kup” lub „sprzedaj”. Dostarczony program jest **jawną, eksperymentalną formalizacją** wybranych obserwacji z kursu. Przetwarza zamknięte świece jednego instrumentu i jednego interwału. Oblicza cechy ceny i wolumenu, oznacza kandydatów na nazwane sygnały, zapisuje późniejsze potwierdzenia oraz testuje uproszczoną sekwencję wejścia.

Słowo `candidate` w wynikach oznacza spełnienie warunków programu. Nie dowodzi udziału konkretnych uczestników rynku ani przyszłego kierunku ceny. Kilka nazw może pasować do tej samej świecy; nie są to niezależne „głosy” zwiększające prawdopodobieństwo sukcesu.

| Element metody | Zakres dostarczonego programu |
|---|---|
| Spread, korpus, cienie, położenie zamknięcia, Up Bar/Down Bar | Obliczenia bezpośrednio z OHLC. Kierunek bara zależy od poprzedniego zamknięcia. |
| Względny wolumen i względny spread | Odniesienie do wcześniejszego okna; bieżąca świeca nie wchodzi do własnego poziomu odniesienia. |
| Nazwane sygnały siły i słabości | Kandydaci według jawnych reguł opisanych w instrukcji programu. Progi i długości okien są założeniami. |
| WFO w obu kierunkach | Uproszczenie oparte na lokalnych ekstremach, relacji wolumenów i opóźnionym potwierdzaniu ekstremum. |
| Tło rynku | Przybliżenie na jednym interwale, bez pełnej oceny struktury wyższego interwału. |
| Sekwencja transakcyjna | Wcześniejsza siła → No Supply/Test → potwierdzenie albo wcześniejsza słabość → No Demand → potwierdzenie. |
| Scenariusz nr 5, pełne ABC i geometria Fibonacciego | Opisane w kompendium; nie są w całości realizowane przez backtest. |
| Zarządzanie transakcją | Jedna pozycja naraz, stały stop i cel, prowizja i poślizg, limit ryzyka i nominału. |
| Dane makro, kalendarz sesji, rolowanie kontraktów, finansowanie i automatyczne zlecenia | Nie są zintegrowane. |

Szczegółowe, obowiązujące warunki każdego detektora znajdują się w `python/README.md` i `python/engine.py`. Jeżeli zmienisz konfigurację, zmienisz również badany wariant strategii. Nie nazywaj wyników różnych konfiguracji wynikami jednej niezmiennej metody.

### A.2. Uruchomienie

Potrzebny jest Python 3.10 lub nowszy. Sam silnik nie wymaga instalowania pakietów przez `pip`. Otwórz terminal w podfolderze `python` rozpakowanego pakietu i wykonaj:

```text
python vsa.py --input sample_ohlcv.csv --output results
```

Na Windows można zastąpić `python` poleceniem `py -3`. Przykład zawiera **dane syntetyczne**, przygotowane do demonstracji działania. Jego wynik finansowy nie jest pomiarem skuteczności na rynku.

Własne dane przygotuj jako CSV z nagłówkiem:

```text
timestamp,open,high,low,close,volume
2026-01-01T10:00:00Z,100,102,99,101,1500
2026-01-01T10:05:00Z,101,103,100,102,1300
```

To tylko ilustracja formatu; dwie świece nie wystarczają do rozgrzania modelu. Używaj kropki dziesiętnej, przecinka jako separatora, jednej strefy czasowej i rosnących, niepowtarzających się znaczników czasu. Wybierz jedną konwencję oznaczania świec: ich początek lub koniec; konsekwentnie stosuj ją w całym zbiorze. Obliczenia zakładają, że wszystkie wartości danej świecy są znane dopiero po jej zamknięciu. Naiwne znaczniki bez strefy są przez loader traktowane jako UTC, dlatego najlepiej przekazywać jawne `Z` albo przesunięcie strefy.

W zbiorze powinien być jeden instrument i jeden interwał. Nie sklejaj wolumenu kontraktu futures z ceną innego instrumentu ani danych różnych dostawców bez jawnej synchronizacji i uzasadnienia. Plik nie może zawierać niezamkniętej ostatniej świecy. Ceny muszą być dodatnie, wolumen nieujemny, a High i Low obejmować Open i Close. Model nie obsługuje instrumentów z cenami zerowymi lub ujemnymi.

### A.3. Jak czytać wyniki

`signals.csv` służy do audytu świeca po świecy: zawiera dane wejściowe, cechy, kandydatów i zdarzenia potwierdzenia. `trades.csv` opisuje symulowane transakcje. `equity.csv` pokazuje przebieg kapitału z wyceną otwartej pozycji. `summary.json` jest skrótem wyników. Dokładny wykaz plików i kolumn podaje instrukcja programu.

Rozróżniaj trzy czasy:

1. **Świeca kandydata:** dopiero jej zamknięcie ujawnia pełny High, Low, Close i Volume.
2. **Świeca potwierdzenia:** późniejsza reakcja, której wcześniej nie można było znać. WFO ma dodatkowe opóźnienie wynikające z rozpoznawania lokalnych ekstremów.
3. **Realizacja:** w backteście następuje najwcześniej na otwarciu kolejnej świecy po potwierdzeniu.

Potwierdzenie w implementacji jest bardziej mechaniczne niż obserwacja prowadzącego: pełne reguły podaje README. Dotknięcie poziomu i zamknięcie poza nim nie są tym samym. Model nie udaje, że z samego OHLC zna kolejność wszystkich ruchów w obrębie świecy. Gdy po wejściu stop i cel mieszczą się w zakresie tej samej świecy, przyjmuje wykonanie stopu jako pierwsze. To założenie konserwatywne, a nie odtworzenie rzeczywistej ścieżki ceny.

### A.4. Ryzyko i jednostki

Kwota planowanego ryzyka jest ułamkiem kapitału. Wielkość pozycji zależy od odległości wejścia od stopu, kosztów oraz limitu nominału. Cel wyznaczony jako wielokrotność odległości do stopu nie oznacza, że rynek rzeczywiście ma taki potencjał: program nie bada wszystkich oporów, wsparć ani płynności na drodze do celu. To szczególnie ważna różnica wobec oceny potencjału w kursowym scenariuszu nr 5.

Podstawowy model używa jednostek instrumentu, dla których ruch ceny o 1 daje zmianę wartości o 1 na jednostkę, w walucie kapitału. Nie podstawiaj bez przeliczenia liczby kontraktów futures, lotów FX ani instrumentów z innym mnożnikiem. Ułamkowa liczba jednostek w symulacji może być niedozwolona u konkretnego brokera. W takim zastosowaniu trzeba uwzględnić wartość punktu, walutę kwotowania, minimalny krok pozycji i depozyt.

Stop jest poziomem aktywacji wyjścia, a nie gwarancją kwoty straty. Luka przez stop może zwiększyć stratę ponad planowany budżet. Wyjaśnienie tej różnicy znajduje się również w materiale [FINRA o ryzyku zleceń stop](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets). W modelu prowizja jest naliczana po obu stronach transakcji; szczegóły wykonania celu i poślizgu podaje README.

Obsunięcie kapitału jest mierzone na kolejnych zamknięciach świec, po uwzględnieniu modelowanych wyjść. Nie jest to dokładne maksimum obsunięcia wewnątrz świecy. W przypadku otwartej pozycji wycena uwzględnia szacowany koszt zamknięcia; nie jest jeszcze zrealizowaną transakcją. Stała prowizja i poślizg nie modelują całej zmienności spreadu bid-ask, finansowania pozycji, kolejek zleceń ani wpływu własnego zlecenia na cenę.

### A.5. Czego dowodzą testy programu

Testy jednostkowe sprawdzają logikę i obliczenia na kontrolowanych przykładach. Test przyczynowości porównuje wyniki na prefiksie szeregu z tą samą częścią wyniku dla całej historii: dodanie późniejszych świec nie może zmienić dawnych cech ani dawnych zdarzeń analitycznych. Metadane wykonania transakcji i statystyki końcowe należy oceniać osobno, ponieważ pojawiają się później.

Przejście testów nie jest dowodem przewagi inwestycyjnej. Do jej oceny potrzebny jest oddzielony czasowo zbiór testowy z rzeczywistymi danymi, realistycznymi kosztami i kontrolą liczby sprawdzonych wariantów. W pakiecie nie ma rzeczywistych danych rynkowych ani deklaracji, że strategia zarabia.

Rozsądny eksperyment polega na zamrożeniu konfiguracji po okresie treningowym, sprawdzeniu kolejnego okresu bez zmian, powtórzeniu tego procesu w kolejnych oknach oraz zestawieniu wyników z prostym punktem odniesienia. Raportuj liczbę transakcji, wynik netto, obsunięcie, rozkład zysków i strat oraz wrażliwość na koszty. Wykres kilku trafnych przykładów sam w sobie nie wystarcza.

### A.6. Pochodzenie i powtarzalność

Pakiet zawiera inwentarz `zrodla_manifest.json` z nazwami, rozmiarami i skrótami SHA-256 materiałów tekstowych. Inwentarz obejmuje także kopie; jego obecność nie oznacza, że kopie są niezależnymi źródłami. Nagrania pozostają w oryginalnym folderze. Podczas pracy sprawdzono punktowo klatki: lekcja 8 o 02:30, lekcja 25 o 03:30 i lekcja 26 o 01:00. Nie przeprowadzono ponownego oglądania wszystkich filmów od początku do końca.

Przechowuj wraz z każdym własnym backtestem plik wejściowy, konfigurację, wersję kodu i datę uruchomienia. Wynik bez tych elementów nie wystarcza do powtórzenia eksperymentu.
