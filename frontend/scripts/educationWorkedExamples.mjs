// Additional bilingual examples. All chart values are synthetic teaching data.
export const extraDefinitions=[]
const add=(article,section,id,title,caption,scene)=>extraDefinitions.push({article,section,id:`example-${id}`,title,caption,scene,placement:'end'})
const lines=(series,extra={})=>({type:'lines',series,...extra})
const columns=(values,labels,extra={})=>({type:'columns',values,labels,...extra})
const chart=(bars,extra={})=>({type:'chart',bars,...extra})
const flow=(steps,note)=>({type:'flow',steps,note})
const green='#34d399',red='#fb7185',blue='#38bdf8',gold='#fbbf24'

add('minervini','The idea in plain language','trend-stack',
 ['Reading the trend layers together','Łączne odczytywanie warstw trendu'],
 ['Price above the three ordered averages illustrates the trend structure. The slope, yearly range and relative-strength checks remain separate.','Cena ponad trzema uporządkowanymi średnimi ilustruje strukturę trendu. Nachylenie, zakres roczny i siła względna pozostają osobnymi warunkami.'],
 lines([{label:['Price','Cena'],values:[112,118,115,124,121,130]},{label:'MA 50',values:[106,108,110,113,116,119]},{label:'MA 150',values:[101,103,105,107,109,111]},{label:'MA 200',values:[98,99,100,102,104,106]}]))
add('minervini','The eight rules StockPilot checks','ma-slope-cases',
 ['Same starting average, different slopes','Ta sama średnia początkowa, różne nachylenia'],
 ['The rising MA 200 passes the slope check; the falling example does not. Being above an average alone does not establish its slope.','Rosnąca MA 200 spełnia warunek nachylenia; malejąca nie. Sama cena ponad średnią nie określa kierunku tej średniej.'],
 lines([{label:['Rising MA 200','Rosnąca MA 200'],values:[100,101,102,103,104],color:green},{label:['Falling MA 200','Malejąca MA 200'],values:[100,99,98,97,96],color:red}],{points:true,axis:['t − 20','t']}))
add('minervini','The eight rules StockPilot checks','high-distance-cases',
 ['Distance from a high of 200','Odległość od maksimum 200'],
 ['A close of 160 is 20% below 200 and passes this one rule. A close of 140 is 30% below and fails. The boundary is 150.','Zamknięcie 160 leży 20% poniżej 200 i spełnia tę jedną regułę. Zamknięcie 140 leży 30% poniżej i jej nie spełnia. Granicą jest 150.'],
 columns([160,140],[['Pass: −20%','Spełnia: −20%'],['Fail: −30%','Nie spełnia: −30%']],{unit:['CLOSING PRICE','CENA ZAMKNIĘCIA'],ref:150,refLabel:['Minimum close = 150','Minimalne zamknięcie = 150'],colors:[green,red]}))
add('minervini','What you see in the app','structural-score',
 ['One unmet rule changes the score','Jedna niespełniona reguła zmienia wynik'],
 ['In the seven-rule structural view, six rules give approximately 86 and seven give 100. The market ranking adds relative strength as an eighth rule.','W widoku siedmiu reguł strukturalnych sześć daje około 86, a siedem 100. Ranking rynku dodaje siłę względną jako ósmą regułę.'],
 columns([86,100],[['6 of 7','6 z 7'],['7 of 7','7 z 7']],{unit:['STRUCTURAL SCORE','WYNIK STRUKTURALNY'],colors:[blue,green],note:['A score measures rule completion','Wynik mierzy kompletność reguł']}))

add('volumeBreakout','The conditions StockPilot checks','wick-without-breakout',
 ['A wick above the base is not enough','Knot ponad bazą nie wystarcza'],
 ['The last high reaches 109, but the close is 102, below resistance at 104. This example fails the closing-price breakout rule.','Ostatnie maksimum sięga 109, ale zamknięcie wynosi 102, poniżej oporu 104. Przykład nie spełnia warunku wybicia ceną zamknięcia.'],
 chart([[99,103,97,101,80],[101,104,98,100,70],[100,103,98,101,60],[101,109,100,102,170]],{levels:[[104,['Base high 104','Maksimum bazy 104'],blue]],note:['H = 109; C = 102 < 104','H = 109; C = 102 < 104']}))
add('volumeBreakout','The conditions StockPilot checks','breakout-volume-cases',
 ['Two volume levels at the same threshold','Dwa wolumeny przy tym samym progu'],
 ['With reference volume 100, the minimum is 150. Volume 180 passes this check; 120 fails even if price has broken above the base.','Przy wolumenie odniesienia 100 minimum wynosi 150. Wolumen 180 spełnia ten warunek; 120 nie, nawet gdy cena wybiła ponad bazę.'],
 columns([180,120],[['Pass','Spełnia'],['Fail','Nie spełnia']],{ref:150,refLabel:'1.5 × 100 = 150',colors:[green,red]}))
add('volumeBreakout','The idea in plain language','quiet-base-breakout',
 ['Quiet consolidation, then expansion','Spokojna konsolidacja, potem ekspansja'],
 ['The example links a contracting price range and fading volume to a later wide bar above resistance. It illustrates the sequence, not a guaranteed outcome.','Przykład łączy zawężający się zakres ceny i malejący wolumen z późniejszym szerokim barem ponad oporem. Ilustruje kolejność, nie gwarantuje wyniku.'],
 chart([[100,106,95,102,110],[102,105,97,100,90],[100,104,98,102,70],[102,103,99,101,45],[101,113,100,112,190]],{levels:[[106,['Resistance','Opór'],blue]]}))
add('volumeBreakout','What the app does not do','breakout-next-paths',
 ['A breakout can continue or fail','Wybicie może trwać lub zawieść'],
 ['Both hypothetical paths start at the same breakout close. A scanner signal alone does not determine the following price path or manage the exit.','Obie hipotetyczne ścieżki zaczynają się na tym samym zamknięciu wybicia. Sam sygnał skanera nie określa dalszej ścieżki ceny ani wyjścia.'],
 lines([{label:['Continuation','Kontynuacja'],values:[105,108,107,112,116],color:green},{label:['Return to base','Powrót do bazy'],values:[105,103,101,98,96],color:red}],{axis:[['Signal close','Zamknięcie sygnału'],['Later sessions','Kolejne sesje']],points:true}))

add('weinstein','Why weekly bars','week-volume-sum',
 ['Five daily volumes make one weekly total','Pięć wolumenów dziennych tworzy sumę tygodnia'],
 ['In this example, daily volumes 20, 30, 25, 35 and 40 sum to 150. A partial week would omit some of that activity.','W tym przykładzie wolumeny dzienne 20, 30, 25, 35 i 40 sumują się do 150. Niepełny tydzień pomija część tej aktywności.'],
 columns([20,30,25,35,40],[['Mon','Pon'],['Tue','Wt'],['Wed','Śr'],['Thu','Czw'],['Fri','Pt']],{note:['Completed weekly volume = 150','Wolumen zamkniętego tygodnia = 150']}))
add('weinstein','The six conditions StockPilot checks','weekly-slope-limit',
 ['The average must rise slowly enough','Średnia musi rosnąć dostatecznie powoli'],
 ['Starting at 100 ten weeks ago, an average ending at 105 satisfies the 0–10% change rule. An average ending at 115 is too steep for this check.','Przy wartości 100 dziesięć tygodni temu średnia kończąca na 105 spełnia regułę zmiany 0–10%. Wartość 115 oznacza zbyt stromy wzrost dla tego warunku.'],
 lines([{label:['+5%: passes','+5%: spełnia'],values:[100,101,102,103,104,105],color:green},{label:['+15%: too steep','+15%: zbyt stromo'],values:[100,103,106,109,112,115],color:red}],{axis:['t − 10w','t'],points:true}))
add('weinstein','The six conditions StockPilot checks','weekly-wick',
 ['Judge the completed weekly close','Oceń zamknięcie pełnego tygodnia'],
 ['An intraweek high above 104 is not sufficient: the last weekly close at 101 returns below the base high.','Maksimum wewnątrz tygodnia ponad 104 nie wystarcza: ostatnie zamknięcie tygodnia na 101 wraca poniżej maksimum bazy.'],
 chart([[99,103,96,101,80],[101,104,97,100,75],[100,103,98,101,65],[101,110,99,101,220]],{levels:[[104,['Base high','Maksimum bazy'],blue]],note:['Each candle represents one completed week','Każda świeca oznacza jeden zamknięty tydzień']}))
add('weinstein','What the app does not do','stage-context-exit',
 ['Recognising stages and planning an exit','Rozpoznawanie faz i planowanie wyjścia'],
 ['A Stage 2 entry screen does not automatically provide a Stage 3 or Stage 4 exit. The illustration separates the entry context from later trade management.','Skaner wejścia w Fazę 2 nie dostarcza automatycznie wyjścia w Fazie 3 lub 4. Ilustracja rozdziela kontekst wejścia od późniejszego zarządzania transakcją.'],
 flow([['Stage 1: base','Faza 1: baza'],['Stage 2: advance','Faza 2: wzrost'],['Stage 3: topping','Faza 3: szczyt'],['Stage 4: decline','Faza 4: spadek']],['The scanner describes an entry setup; plan exits separately','Skaner opisuje układ wejścia; wyjścia zaplanuj osobno']))

add('pocketPivot','How it differs from a volume breakout','largest-selling-day',
 ['A large buying day is not the reference','Duży dzień wzrostowy nie jest odniesieniem'],
 ['Among these reference-day examples, the largest down-day volume is 100. The up-day volume of 180 is excluded from that maximum; signal-day volume 120 passes this one comparison.','Wśród tych przykładowych dni odniesienia największy wolumen dnia spadkowego wynosi 100. Wzrostowy dzień z wolumenem 180 nie należy do tego maksimum; wolumen sygnału 120 spełnia to jedno porównanie.'],
 columns([80,180,100,120],[['Down day','Dzień spadkowy'],['Up day','Dzień wzrostowy'],['Down day','Dzień spadkowy'],['Signal day','Dzień sygnału']],{colors:[red,green,red,gold],ref:100,refLabel:'V = 100',note:['Selected days from the 10-session reference window','Wybrane dni z okna odniesienia 10 sesji']}))
add('pocketPivot','The six conditions StockPilot checks','insufficient-pivot-volume',
 ['A rising close with insufficient volume','Rosnące zamknięcie przy zbyt małym wolumenie'],
 ['A signal-day volume of 90 is below the largest down-day volume of 100. A rising close cannot compensate for this failed volume check.','Wolumen dnia sygnału 90 jest niższy od największego wolumenu dnia spadkowego 100. Rosnące zamknięcie nie zastępuje niespełnionego warunku wolumenu.'],
 columns([100,90],[['Down-day max','Maks. spadkowy'],['Candidate day','Dzień kandydata']],{colors:[blue,red],ref:100,refLabel:['Required minimum = 100','Wymagane minimum = 100']}))
add('pocketPivot','The six conditions StockPilot checks','pivot-too-far',
 ['A low too far above the moving average','Minimum zbyt daleko nad średnią'],
 ['With the average at 100, the allowed low is at most 102. This bar has a low of 107, so it fails the proximity check for that average.','Przy średniej 100 dopuszczalne minimum wynosi najwyżej 102. Ten bar ma minimum 107, więc nie spełnia warunku bliskości tej średniej.'],
 chart([[108,112,107,111,160],[111,115,109,114,180]],{levels:[[100,'MA = 100',blue],[102,['Limit = 102','Limit = 102'],red]],note:['First bar: L = 107 > 102','Pierwszy bar: L = 107 > 102']}))
add('pocketPivot','The six conditions StockPilot checks','no-selling-reference',
 ['No down day means no comparison','Brak dnia spadkowego oznacza brak porównania'],
 ['When the prior ten sessions contain no down day with volume, the engine has no selling-day benchmark and does not fire a pocket pivot.','Gdy poprzednie dziesięć sesji nie zawiera dnia spadkowego z wolumenem, silnik nie ma odniesienia do podaży i nie generuje pocket pivot.'],
 flow([['Inspect prior 10 sessions','Sprawdź poprzednie 10 sesji'],['No down day with volume','Brak dnia spadkowego z wolumenem'],['No valid benchmark','Brak poprawnego odniesienia'],['No pocket pivot','Brak pocket pivot']]))

add('vsaRating','The six patterns the engine looks for','reference-window',
 ['The candidate is outside its reference window','Kandydat leży poza oknem odniesienia'],
 ['The average spread, average volume and range extrema come from the previous twenty sessions. The candidate bar is evaluated against them.','Średni zakres, średni wolumen i ekstrema pochodzą z poprzednich dwudziestu sesji. Bar kandydata jest oceniany na ich tle.'],
 flow([['t − 20 through t − 1','Od t − 20 do t − 1'],['Compute reference values','Oblicz wartości odniesienia'],['Evaluate bar t','Oceń bar t']],['Keep the candidate outside the reference averages','Nie włączaj kandydata do średnich odniesienia']))
add('vsaRating','From patterns to one number','offsetting-signals',
 ['Opposing signals can cancel out','Przeciwne sygnały mogą się równoważyć'],
 ['A bullish contribution of +1 and a bearish contribution of −1, with equal decay, sum to zero. The formula then returns a rating of 50.','Wkład wzrostowy +1 i spadkowy −1, przy takim samym zaniku, sumują się do zera. Wzór zwraca wtedy rating 50.'],
 flow([['Bullish: +1','Wzrostowy: +1'],['Bearish: −1','Spadkowy: −1'],['Net score: 0','Wynik netto: 0'],['Rating: 50','Rating: 50']]))
add('vsaRating','From patterns to one number','rating-decay-example',
 ['One signal fades toward neutral','Jeden sygnał zanika ku neutralności'],
 ['With no new signals, an initial bullish weight of 1 becomes 0.5 after 30 days and 0.25 after 60. The corresponding rounded ratings are 73, 62 and 56.','Bez nowych sygnałów początkowa waga wzrostowa 1 spada do 0,5 po 30 dniach i 0,25 po 60. Odpowiednie zaokrąglone ratingi to 73, 62 i 56.'],
 lines([{label:['Rating','Rating'],values:[73,62,56]}],{points:true,min:50,max:80,axis:[['Day 0','Dzień 0'],['Day 60','Dzień 60']],levels:[[50,['Neutral = 50','Neutralnie = 50']]],note:['Day 0 → 30 → 60; no new signals','Dzień 0 → 30 → 60; brak nowych sygnałów']}))
add('vsaRating','Where you see it in the app','timeframe-conflict',
 ['Daily strength and weekly weakness','Siła dzienna i słabość tygodniowa'],
 ['Opposite non-neutral daily and weekly verdicts indicate a conflict. They describe different timeframes; agreement is not a forecast of the next move.','Przeciwne, nieneutralne oceny dzienna i tygodniowa oznaczają konflikt. Opisują różne interwały; zgodność nie jest prognozą następnego ruchu.'],
 flow([['Daily: bullish','Dziennie: wzrostowo'],['Weekly: bearish','Tygodniowo: spadkowo'],['1W: conflict','1W: konflikt']],['Assess both timeframes before interpreting the badge','Oceń oba interwały przed interpretacją oznaczenia']))

add('vsaKompendium','Exercise A — describing a bar without interpretation','exercise-observation',
 ['Exercise A: describe before interpreting','Ćwiczenie A: opisz przed interpretacją'],
 ['For this bar, the range is 16 and the close position is (108 − 96) / 16 = 0.75. Record those observations before assigning an interpretation.','Dla tego bara zakres wynosi 16, a pozycja zamknięcia (108 − 96) / 16 = 0,75. Zapisz te obserwacje przed nadaniem interpretacji.'],
 {type:'anatomy',items:[[100,112,96,108]],labels:[['Range = 16; close position = 0.75','Zakres = 16; pozycja close = 0,75']],note:['Next: compare volume and the previous close','Dalej: porównaj wolumen i poprzednie zamknięcie']} )
add('vsaKompendium','Exercise B — signal and context','exercise-hidden-future',
 ['Exercise B: hide the future first','Ćwiczenie B: najpierw zasłoń przyszłość'],
 ['Write the hypothesis and invalidation using only information available at the signal. Reveal later bars afterwards and include failed examples.','Zapisz hipotezę i unieważnienie wyłącznie na podstawie danych dostępnych przy sygnale. Dopiero potem odsłoń kolejne bary; uwzględnij też niepowodzenia.'],
 flow([['Hide later bars','Zasłoń późniejsze bary'],['Describe background','Opisz tło'],['Write invalidation','Zapisz unieważnienie'],['Reveal and compare','Odsłoń i porównaj']]))
add('vsaKompendium','Exercise C — a test of supply as a sequence','exercise-test-sequence',
 ['Exercise C: mark the whole sequence','Ćwiczenie C: zaznacz całą sekwencję'],
 ['The schematic shows a rebound, a lower-volume return to the test area and a later response. Label attempts separately from confirmed and negated tests.','Schemat pokazuje odbicie, powrót do obszaru testu przy mniejszym wolumenie i późniejszą reakcję. Oddziel próby od testów potwierdzonych i zanegowanych.'],
 chart([[103,104,94,99,240],[99,108,98,107,150],[107,108,100,102,80],[102,103,98,102,40],[102,110,101,109,130]],{highlight:[3],levels:[[98,['Test area','Obszar testu'],blue]],note:['Attempt → later response → assessment','Próba → późniejsza reakcja → ocena']}))
add('vsaKompendium','Exercise D — auditing VSA in code','exercise-zero-range',
 ['Exercise D: handle a zero-range bar','Ćwiczenie D: obsłuż bar o zerowym zakresie'],
 ['When O = H = L = C, the range is zero. The close-position fraction would divide by zero, so the implementation must handle this case explicitly.','Gdy O = H = L = C, zakres wynosi zero. Wzór pozycji zamknięcia dzieliłby przez zero, dlatego implementacja musi jawnie obsłużyć ten przypadek.'],
 flow([['O = H = L = C = 100','O = H = L = C = 100'],['H − L = 0','H − L = 0'],['Do not divide by zero','Nie dziel przez zero'],['Verify documented handling','Sprawdź opisaną obsługę']]))
add('vsaKompendium','Exercise E — out of sample and costs','exercise-validation-split',
 ['Exercise E: keep validation later in time','Ćwiczenie E: walidacja później w czasie'],
 ['Use the earlier period to define the rules and the later period to assess them against a baseline after costs. Reusing validation to tune the rules compromises the separation.','Wcześniejszy okres służy ustaleniu reguł, a późniejszy ich ocenie względem punktu odniesienia po kosztach. Dostrajanie reguł na walidacji narusza ten podział.'],
 flow([['Earlier: design','Wcześniej: projekt'],['Freeze rules','Zamroź reguły'],['Later: evaluate','Później: oceń'],['Compare after costs','Porównaj po kosztach']]))
add('vsaKompendium','Exercise F — a decision journal','exercise-journal',
 ['Exercise F: record skipped entries too','Ćwiczenie F: zapisuj także pominięte wejścia'],
 ['A useful journal retains the original plan and records both entries and decisions to abstain. Review the process separately from the eventual profit or loss.','Przydatny dziennik zachowuje pierwotny plan oraz zapisuje wejścia i decyzje o rezygnacji. Oceniaj proces oddzielnie od późniejszego zysku lub straty.'],
 flow([['Chart + timestamp','Wykres + czas'],['Hypothesis + invalidation','Hipoteza + unieważnienie'],['Enter or abstain','Wejdź lub zrezygnuj'],['Review process + result','Oceń proces + wynik']]))
