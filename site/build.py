"""Build the Triki reference page (en, pl, ru) for GitHub Pages.

python3 site/build.py [output directory, site/_site by default]

A plain reference page about the Żabka Triki cap, organised by what people
search for (what it is, the battery, connecting, using it without the app),
with the Home Assistant integration as one section. One template, one text
table per language, so every page has the same sections.
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "_site"
BASE = "https://elenium3.github.io/ha-triki/"
GH = "https://github.com/elenium3/ha-triki"
DOCS = f"{GH}/blob/main/docs/"
HACS = ("https://my.home-assistant.io/redirect/hacs_repository/?owner=elenium3&repository=ha-triki"
        "&category=integration")
BP = ("https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com"
      "%2Felenium3%2Fha-triki%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ftriki%2F")
LANGS = {"en": "", "pl": "pl/", "ru": "ru/"}

# Links used in every language
L = {
    "flops": "https://github.com/Flopsstuff/triki",
    "scope": "https://github.com/Maku-hub/TrikiScope",
    "pylib": "https://github.com/woofter-wolf/triki-library-python",
    "pyapi": "https://github.com/Wojtekb30/unofficial-triki-api-py",
    "hw": "https://github.com/Piwencjusz/zabka-triki-hardware",
    "pcb": "https://github.com/DISKIMG/Triki-PCB",
    "ctrl": "https://github.com/koksny/TRIKI-Control",
    "tray": "https://github.com/egortar-pi/TrikiControl",
    "reader": "https://github.com/AND-Y0/TrikiReader",
    "mouse": "https://github.com/kawaczek/triki",
    "vr": "https://github.com/CreoleVR/TrikiVR",
    "esp": "https://github.com/Diego7120/esp_triki",
    "find": "https://github.com/alex-so-3/find-my-triki",
    "unoff": "https://github.com/orionas97/triki_unofficial",
    "elektroda": "https://www.elektroda.pl/news/news4175986.html",
    "reddit": "https://www.reddit.com/r/Polska/comments/1txi9uz/kontroler_triki_z_%C5%BCabki_czy_kto%C5%9B_pr%C3%B3bowa%C5%82/",
    "faq": "https://triki.zabka.pl/#faq",
    "gsm": "https://gsmonline.pl/artykuly/sprawdzilismy-nowy-kontroler-triki-z-zabki",
    "press": "https://www.zabka.pl/triki-nowy-wymiar-rozrywki-w-zappce/",
    "ha": "https://www.home-assistant.io/",
    "proxy": DOCS + "bluetooth-proxy.md",
}


def a(key: str, text: str) -> str:
    return f'<a href="{L[key]}">{text}</a>'


def projects(t: dict) -> str:
    """The community projects list; the descriptions are per language."""
    groups = [
        (t["pg_docs"], [("flops", "Flopsstuff/triki", t["p_flops"]), ("scope", "TrikiScope", t["p_scope"]),
                        ("pylib", "triki-library-python", t["p_pylib"]), ("pyapi", "unofficial-triki-api-py", t["p_pyapi"])]),
        (t["pg_pc"], [("ctrl", "TRIKI-Control", t["p_ctrl"]), ("tray", "TrikiControl", t["p_tray"]),
                      ("reader", "TrikiReader", t["p_reader"])]),
        (t["pg_other"], [("mouse", "kawaczek/triki", t["p_mouse"]), ("vr", "TrikiVR", t["p_vr"]),
                         ("esp", "esp_triki", t["p_esp"]), ("find", "find-my-triki", t["p_find"])]),
        (t["pg_hw"], [("hw", "zabka-triki-hardware", t["p_hw"]), ("pcb", "Triki-PCB", t["p_pcb"])]),
    ]
    out = ""
    for title, items in groups:
        out += f"<h3>{title}</h3><ul>" + "".join(f"<li>{a(k, n)}: {d}</li>" for k, n, d in items) + "</ul>"
    return out


T: dict[str, dict] = {}

T["en"] = {
    "title": "Żabka Triki: what it is, the battery, connecting, using it without the app",
    "desc": "The Triki controller from Żabka (the bottle cap for the Żappka games): what is inside, "
            "which battery it takes and how to change it, why it does not connect, and how to use it "
            "without the app, on a PC or with Home Assistant.",
    "h1": "Żabka Triki: what it is and how it works",
    "lead": "Notes on the Triki cap from the Żappka games, collected while writing a Home Assistant "
            "integration for it. What is inside, the battery, connecting, and using it outside the app.",
    "toc": "On this page",
    "s": {"what": "What it is", "inside": "What is inside", "battery": "Battery", "connect": "Connecting",
          "noapp": "Without the Żappka app", "ha": "Home Assistant", "faq": "Questions"},
    "what": f"""<p>Triki is a small Bluetooth motion controller in the shape of a bottle cap. Żabka
announced it on 29 April 2026 as a controller for the <i>Strefa Gier</i> (game zone) in the Żappka
app, where it plays short games (Snake, Ninja Frog, boxing, a toss game, football) for points and
discounts. It went on general sale in Żabka stores on 8 June 2026
({a("press", "Żabka press release")}).</p>
<p>The cap is made by Caps Apps (brand HOPX), model CAP001. It has one button, a green LED and a
motion sensor. There is no vibration, speaker or compass.</p>""",
    "inside": """<table>
<tr><th>Part</th><th>What</th></tr>
<tr><td>Chip</td><td>Nordic nRF52810, Bluetooth Low Energy 5</td></tr>
<tr><td>Motion sensor</td><td>ST LSM6DSL: accelerometer and gyroscope, 3 axes each</td></tr>
<tr><td>Memory</td><td>Macronix MX25R8035F, 8 Mbit, holds firmware updates</td></tr>
<tr><td>Button</td><td>the whole cap: the green underside flexes when pressed</td></tr>
<tr><td>LED</td><td>green</td></tr>
<tr><td>Battery</td><td>CR2032 coin cell</td></tr>
<tr><td>Firmware</td><td>3.2.1-A on the unit we tested; updates come signed through the app</td></tr>
</table>""",
    "inside_src": f"Sources: {a('flops', 'Flopsstuff/triki')}, {a('hw', 'Piwencjusz/zabka-triki-hardware')}, "
                  f"{a('gsm', 'gsmonline.pl')}.",
    "photo_front": "The Triki: a silver bottle cap with a black T",
    "photo_back": "The underside: a green board with the Ż logo",
    "photo_credit": "Photos: Flopsstuff, MIT",
    "battery": f"""<p><b>Triki does not charge.</b> It runs on a CR2032 coin cell, the same as in
kitchen scales and car keys, and the cell is replaceable.</p>
<p>A weak cell shows as an irregularly blinking LED or frequent disconnects (Żabka's
{a("faq", "FAQ")}). We also saw caps with a weak cell stop answering the button until the cell
was taken out and put back.</p>
<p><b>Changing it.</b> There are no screws or clips: the green underside just sits inside the crimped
metal rim. Pry it up with something thin and lift it out. Note which way the cell faces before
taking it out.</p>
<p><b>How long it lasts</b> depends on use. Kept connected all the time, a fresh cell is empty in
about a week. A cap that is left alone sleeps and uses very little.</p>""",
    "connect": """<p>There is no pairing in the usual sense. The cap advertises itself as
<code>Triki</code> followed by a ten-digit number (the app shows the same number), and anything
that connects can talk to it.</p>
<ul>
<li><b>It sleeps</b> when it lies still and nothing is connected. Only a press wakes it: picking it
up or shaking it does not. After a press it is visible for a few seconds.</li>
<li><b>One connection at a time.</b> While a phone, a computer or Home Assistant is connected, nobody
else sees it.</li>
<li>After a connection drops, it stays visible for about three minutes and then sleeps.</li>
</ul>
<h3>When it does not connect</h3>
<ol>
<li>Press the cap once to wake it, then connect within a few seconds.</li>
<li>Check that nothing else holds it: another phone, a computer or Home Assistant. Turning Bluetooth
off on that device frees the cap.</li>
<li>Change the battery if the LED blinks irregularly or the link keeps dropping.</li>
<li>Take the battery out for a few seconds. This is the only reset the cap has; nothing is lost.</li>
</ol>""",
    "noapp": f"""<p>The cap uses plain Bluetooth Low Energy without encryption or an account. People
in the community worked out its protocol ({a("elektroda", "elektroda.pl")},
{a("reddit", "r/Polska")}), and there are open-source programs for it. All of them are unofficial.
A computer needs Bluetooth Low Energy (Bluetooth 4.0 or newer).</p>""",
    "pg_docs": "Protocol and libraries", "pg_pc": "On a computer", "pg_other": "Other uses",
    "pg_hw": "Hardware",
    "p_flops": "the fullest protocol and hardware description, a TypeScript library",
    "p_scope": "a terminal viewer of the motion data",
    "p_pylib": "a Python library", "p_pyapi": "another Python API",
    "p_ctrl": "a desktop program and a clear write-up of how it works",
    "p_tray": "a Windows tray remote", "p_reader": "a 3D view of the cap's position (C#)",
    "p_mouse": "the cap as an Android mouse", "p_vr": "the cap as a SlimeVR body tracker",
    "p_esp": "an ESP32 client", "p_find": "finding a lost cap by its signal",
    "p_hw": "board photos, pinout, memory and update analysis", "p_pcb": "the board in KiCad",
    "ha": f"""<p><a href="{GH}">ha-triki</a> is an open-source integration that turns the cap into a
remote for {a("ha", "Home Assistant")}. A press, a long press, double and triple presses, turning
the cap on the table like a knob, tilting it and shaking it arrive as events. Automations use them,
for example to switch or dim a light or run a scene. It works locally, without the Żappka app or
the cloud.</p>
<p>The integration comes with a card that shows the cap in 3D. Below it replays a recording of a
real cap.</p>""",
    "replay": "Recorded on a real Triki",
    "captions": ["Turned on the table: knob steps", "Turned on the table: knob steps",
                 "Tilted in the hand, right and left", "Pressed once, twice, held",
                 "Flipped onto the green side", "Shaken"],
    "ha_need": f"""<h3>What you need</h3>
<ul>
<li>Home Assistant 2025.8 or newer.</li>
<li>A Bluetooth receiver near the cap. An ESP32 board with ESPHome Bluetooth proxy near the cap
connects in under a second; the built-in Bluetooth of a Raspberry Pi across the room often connects slowly or not at all
(<a href="{L["proxy"]}">Bluetooth proxy for beginners</a>).</li>
</ul>
<h3>Installing</h3>
<ol>
<li>Find <b>Żabka Triki</b> in <a href="{HACS}">HACS</a>, download it and restart Home Assistant.</li>
<li>Press the cap. It appears under <i>Discovered</i> in Settings → Devices &amp; services; confirm it
and tick the gestures you want.</li>
<li>Add the <b>Triki live 3D</b> card to a dashboard and press <b>Check</b>: it goes through the
button, the knob and the gestures.</li>
</ol>
<p>Ready automations: a <a href="{BP}triki_light.yaml">light remote</a> and
<a href="{BP}triki_actions.yaml">an action per gesture</a>.
Documentation: <a href="{DOCS}installation.md">installation</a>,
<a href="{DOCS}configuration.md">options</a>,
<a href="{DOCS}events-and-automations.md">events and automations</a>,
<a href="{DOCS}troubleshooting.md">troubleshooting</a>.
Another Home Assistant integration that shows the raw sensors: {a("unoff", "triki_unofficial")}.</p>""",
    "faq": [
        ("How do I charge the Triki?",
         "You don't: it has no charging. It runs on a CR2032 coin cell, which you replace."),
        ("Which battery does the Triki take?", "A CR2032 coin cell."),
        ("Why does my Triki not connect?",
         "It sleeps and only a press wakes it, and it accepts one connection at a time. Press it once, "
         "make sure no other phone, computer or Home Assistant is connected to it, and if that does not "
         "help, change the battery or take it out for a few seconds."),
        ("How do I reset the Triki?",
         "Take the battery out for a few seconds. There is no reset button, and nothing is lost."),
        ("Does the Triki work without the Żappka app?",
         "Yes. It is a plain Bluetooth Low Energy device; community programs and the Home Assistant "
         "integration talk to it directly. They are unofficial."),
        ("Does the Triki work on a PC?",
         "Yes, on a computer with Bluetooth Low Energy, using a community program such as TRIKI-Control "
         "or TrikiControl."),
        ("Can the Triki control lights?",
         "Yes, through Home Assistant and the ha-triki integration: presses, turning, tilting and "
         "shaking become events for automations."),
    ],
    "foot": "This page is made by the ha-triki project, not by Żabka. Triki, Żappka and Żabka are "
            "trademarks of their owners; the project is not affiliated with Żabka Polska or Caps Apps. "
            "Using the cap outside the app is at your own risk.",
    "foot_src": "Source on GitHub",
    "hint": "This page is also in English",
    "not_found": "This page does not exist.",
    "home": "Back to the main page",
}

T["pl"] = {
    "title": "Triki z Żabki: co to jest, bateria, połączenie, użycie bez aplikacji",
    "desc": "Kontroler Triki z Żabki (kapsel do gier w Żappce): co jest w środku, jaka bateria i jak "
            "ją wymienić, dlaczego się nie łączy i jak używać go bez aplikacji, na komputerze albo w "
            "Home Assistancie.",
    "h1": "Triki z Żabki: co to jest i jak działa",
    "lead": "Notatki o kapslu Triki do gier w Żappce, zebrane przy pisaniu integracji dla Home "
            "Assistanta. Co jest w środku, bateria, połączenie i używanie go poza aplikacją.",
    "toc": "Na tej stronie",
    "s": {"what": "Co to jest", "inside": "Co jest w środku", "battery": "Bateria", "connect": "Połączenie",
          "noapp": "Bez aplikacji Żappka", "ha": "Home Assistant", "faq": "Pytania"},
    "what": f"""<p>Triki to mały kontroler ruchu Bluetooth w kształcie kapsla. Żabka zapowiedziała go
29 kwietnia 2026 roku jako kontroler do <i>Strefy Gier</i> w aplikacji Żappka, gdzie służy do
krótkich gier (Snake, Ninja Frog, boks, rzut, piłka nożna) o punkty i zniżki. Do sprzedaży we
wszystkich sklepach Żabka trafił 8 czerwca 2026 roku ({a("press", "informacja prasowa Żabki")}).</p>
<p>Producentem kapsla jest Caps Apps (marka HOPX), model CAP001. Triki ma jeden przycisk, zieloną diodę i
czujnik ruchu. Nie ma wibracji, głośnika ani kompasu.</p>""",
    "inside": """<table>
<tr><th>Element</th><th>Co to jest</th></tr>
<tr><td>Mikrokontroler</td><td>Nordic nRF52810, Bluetooth Low Energy 5</td></tr>
<tr><td>Czujnik ruchu</td><td>ST LSM6DSL: akcelerometr i żyroskop, po 3 osie</td></tr>
<tr><td>Pamięć</td><td>Macronix MX25R8035F, 8 Mbit, na aktualizacje oprogramowania</td></tr>
<tr><td>Przycisk</td><td>cały kapsel: zielony spód ugina się przy naciśnięciu</td></tr>
<tr><td>Dioda</td><td>zielona</td></tr>
<tr><td>Bateria</td><td>CR2032 (pastylkowa)</td></tr>
<tr><td>Oprogramowanie</td><td>3.2.1-A w sprawdzanym egzemplarzu; podpisane aktualizacje przychodzą przez aplikację</td></tr>
</table>""",
    "inside_src": f"Źródła: {a('flops', 'Flopsstuff/triki')}, {a('hw', 'Piwencjusz/zabka-triki-hardware')}, "
                  f"{a('gsm', 'gsmonline.pl')}.",
    "photo_front": "Triki: srebrny kapsel z czarnym T",
    "photo_back": "Spód: zielona płytka z logo Ż",
    "photo_credit": "Zdjęcia: Flopsstuff, MIT",
    "battery": f"""<p><b>Triki nie da się ładować.</b> Działa na baterii pastylkowej CR2032, takiej jak w
wadze kuchennej czy kluczyku do samochodu, i tę baterię można wymienić.</p>
<p>Słabą baterię zdradza nieregularnie migająca dioda albo częste rozłączanie się (według
{a("faq", "FAQ Żabki")}). Widzieliśmy też kapsle ze słabą baterią, które nie reagowały na przycisk,
dopóki nie wyjęło się baterii i nie włożyło jej z powrotem.</p>
<p><b>Wymiana.</b> Nie ma śrubek ani zatrzasków: zielony spód jest po prostu włożony w zagięty metalowy
brzeg. Wystarczy podważyć go czymś cienkim i wyjąć. Przed wyjęciem baterii zapamiętaj, którą stroną
jest włożona.</p>
<p><b>Czas pracy</b> zależy od sposobu używania. Przy stałym połączeniu nowa bateria
wyczerpuje się po mniej więcej tygodniu. Nieużywany kapsel śpi i zużywa bardzo mało energii.</p>""",
    "connect": """<p>Nie ma parowania w zwykłym sensie. Kapsel przedstawia się jako <code>Triki</code> z
dziesięciocyfrowym numerem (ten sam numer pokazuje aplikacja) i każde urządzenie, które się z nim
połączy, może z nim rozmawiać.</p>
<ul>
<li><b>Śpi</b>, gdy leży nieruchomo i nic nie jest z nim połączone. Budzi go tylko naciśnięcie:
podniesienie ani potrząśnięcie go nie budzi. Po naciśnięciu jest widoczny przez kilka sekund.</li>
<li><b>Jedno połączenie naraz.</b> Gdy połączony jest telefon, komputer albo Home Assistant, nikt inny
go nie widzi.</li>
<li>Po zerwaniu połączenia jest widoczny jeszcze przez około trzy minuty, potem zasypia.</li>
</ul>
<h3>Gdy nie chce się połączyć</h3>
<ol>
<li>Naciśnij kapsel raz, żeby go obudzić, i połącz się w ciągu kilku sekund.</li>
<li>Sprawdź, czy nie jest z nim połączone inne urządzenie: drugi telefon, komputer albo Home Assistant.
Wyłączenie na nim Bluetooth zwalnia kapsel.</li>
<li>Wymień baterię, jeśli dioda miga nieregularnie albo połączenie się zrywa.</li>
<li>Wyjmij baterię na kilka sekund. To jedyny reset, jaki ma kapsel; niczego się przy tym nie traci.</li>
</ol>""",
    "noapp": f"""<p>Kapsel używa zwykłego Bluetooth Low Energy, bez szyfrowania i bez konta. Społeczność
rozpracowała jego protokół ({a("elektroda", "elektroda.pl")}, {a("reddit", "r/Polska")}) i powstały
do niego programy open source. Wszystkie są nieoficjalne. Komputer musi mieć Bluetooth Low Energy
(Bluetooth 4.0 lub nowszy).</p>""",
    "pg_docs": "Protokół i biblioteki", "pg_pc": "Na komputerze", "pg_other": "Inne zastosowania",
    "pg_hw": "Sprzęt",
    "p_flops": "najpełniejszy opis protokołu i sprzętu, biblioteka TypeScript",
    "p_scope": "podgląd danych z czujnika w terminalu",
    "p_pylib": "biblioteka w Pythonie", "p_pyapi": "inne API w Pythonie",
    "p_ctrl": "program na komputer i przystępny opis działania",
    "p_tray": "pilot w zasobniku systemowym Windows", "p_reader": "podgląd położenia kapsla w 3D (C#)",
    "p_mouse": "kapsel jako mysz w Androidzie", "p_vr": "kapsel jako tracker SlimeVR",
    "p_esp": "klient na ESP32", "p_find": "szukanie zgubionego kapsla po sygnale",
    "p_hw": "zdjęcia płytki, wyprowadzenia, analiza pamięci i aktualizacji", "p_pcb": "płytka w KiCadzie",
    "ha": f"""<p><a href="{GH}">ha-triki</a> to integracja open source, która robi z kapsla pilot do
{a("ha", "Home Assistanta")}. Naciśnięcie krótkie, długie, podwójne i potrójne, obracanie
kapsla na stole jak pokrętła, przechylanie i potrząsanie trafiają do Home Assistanta jako zdarzenia.
Automatyzacje mogą na ich podstawie na przykład zapalać lub ściemniać światło albo uruchamiać sceny.
Integracja działa lokalnie, bez aplikacji Żappka i bez chmury.</p>
<p>Integracja ma kartę, która pokazuje kapsel w 3D. Poniżej karta odtwarza nagranie z
prawdziwego kapsla.</p>""",
    "replay": "Nagranie z prawdziwego Triki",
    "captions": ["Obrót na stole: kroki pokrętła", "Obrót na stole: kroki pokrętła",
                 "Przechylanie w dłoni w prawo i w lewo", "Naciśnięcie: raz, dwa razy, przytrzymanie",
                 "Odwrócenie na zieloną stronę", "Potrząśnięcie"],
    "ha_need": f"""<h3>Czego potrzebujesz</h3>
<ul>
<li>Home Assistanta w wersji 2025.8 lub nowszej.</li>
<li>Odbiornika Bluetooth blisko kapsla. Płytka ESP32 z ESPHome Bluetooth Proxy obok kapsla łączy się
w niecałą sekundę; wbudowany Bluetooth Raspberry Pi na drugim końcu pokoju często łączy się wolno albo wcale
(<a href="{L["proxy"]}">Bluetooth Proxy dla początkujących</a>, po angielsku).</li>
</ul>
<h3>Instalacja</h3>
<ol>
<li>Znajdź <b>Żabka Triki</b> w <a href="{HACS}">HACS</a>, pobierz i uruchom ponownie Home
Assistanta.</li>
<li>Naciśnij kapsel. Pojawi się w sekcji <i>Wykryte</i> w menu Ustawienia → Urządzenia oraz usługi.
Potwierdź go i zaznacz gesty, których chcesz używać.</li>
<li>Dodaj kartę <b>Triki live 3D</b> do dashboardu i kliknij <b>Test</b>, który sprawdza po
kolei przycisk, pokrętło i gesty.</li>
</ol>
<p>Gotowe schematy (blueprinty): <a href="{BP}triki_light.yaml">pilot do światła</a> i
<a href="{BP}triki_actions.yaml">osobna akcja dla każdego gestu</a>.
Dokumentacja (po angielsku): <a href="{DOCS}installation.md">instalacja</a>,
<a href="{DOCS}configuration.md">opcje</a>,
<a href="{DOCS}events-and-automations.md">zdarzenia i automatyzacje</a>,
<a href="{DOCS}troubleshooting.md">rozwiązywanie problemów</a>.
Inna integracja dla Home Assistanta, pokazująca surowe dane z czujników: {a("unoff", "triki_unofficial")}.</p>""",
    "faq": [
        ("Jak naładować Triki?",
         "Nie trzeba i nie da się: Triki nie ma ładowania. Działa na baterii pastylkowej CR2032, którą "
         "się wymienia."),
        ("Jaka bateria jest w Triki?", "Bateria pastylkowa CR2032."),
        ("Dlaczego Triki nie chce się połączyć?",
         "Kapsel śpi i budzi go tylko naciśnięcie, a do tego przyjmuje tylko jedno połączenie naraz. Naciśnij go raz, "
         "sprawdź, czy nie jest połączony z innym telefonem, komputerem albo Home Assistantem, a jeśli "
         "to nie pomoże, wymień baterię albo wyjmij ją na kilka sekund."),
        ("Jak zresetować Triki?",
         "Wyjmij baterię na kilka sekund. Kapsel nie ma przycisku resetu, a przy wyjęciu baterii niczego się nie traci."),
        ("Czy Triki działa bez aplikacji Żappka?",
         "Tak. To zwykłe urządzenie Bluetooth Low Energy; programy tworzone przez społeczność i integracja dla Home "
         "Assistanta łączą się z nim bezpośrednio. Są nieoficjalne."),
        ("Czy Triki działa na komputerze?",
         "Tak, na komputerze z Bluetooth Low Energy, za pomocą programu stworzonego przez społeczność, na przykład "
         "TRIKI-Control albo TrikiControl."),
        ("Czy Triki może sterować światłem?",
         "Tak, przez Home Assistanta i integrację ha-triki: naciśnięcia, obracanie, przechylanie i "
         "potrząsanie stają się zdarzeniami dla automatyzacji."),
    ],
    "foot": "Tę stronę prowadzi projekt ha-triki, nie Żabka. Triki, Żappka i Żabka są znakami "
            "towarowymi należącymi do ich właścicieli; projekt nie jest powiązany ze spółką Żabka Polska ani "
            "z Caps Apps. Używasz kapsla poza aplikacją na własną odpowiedzialność.",
    "foot_src": "Kod na GitHubie",
    "hint": "Ta strona jest dostępna także po polsku",
    "not_found": "Takiej strony nie ma.",
    "home": "Wróć na stronę główną",
}

T["ru"] = {
    "title": "Triki из Żabka: что это, батарейка, подключение, использование без приложения",
    "desc": "Контроллер Triki из Żabka (крышка для игр в Żappka): что внутри, какая батарейка и как её "
            "поменять, почему не подключается и как использовать без приложения, на компьютере или в "
            "Home Assistant.",
    "h1": "Triki из Żabka: что это и как работает",
    "lead": "Заметки о крышке Triki для игр в Żappka, собранные при написании интеграции для Home "
            "Assistant. Что внутри, батарейка, подключение и использование вне приложения.",
    "toc": "На странице",
    "s": {"what": "Что это", "inside": "Что внутри", "battery": "Батарейка", "connect": "Подключение",
          "noapp": "Без приложения Żappka", "ha": "Home Assistant", "faq": "Вопросы"},
    "what": f"""<p>Triki — маленький Bluetooth-контроллер движения в форме крышки от бутылки. Żabka
анонсировала его 29 апреля 2026 года как контроллер для <i>Strefa Gier</i> (игровой зоны) в
приложении Żappka: им играют в короткие игры (Snake, Ninja Frog, бокс, бросок, футбол) за баллы и
скидки. В свободную продажу во всех магазинах Żabka он поступил 8 июня 2026 года
({a("press", "пресс-релиз Żabka")}).</p>
<p>Производитель — Caps Apps (бренд HOPX), модель CAP001. У Triki одна кнопка, зелёный светодиод и
датчик движения. Вибрации, динамика и компаса нет.</p>""",
    "inside": """<table>
<tr><th>Деталь</th><th>Что это</th></tr>
<tr><td>Чип</td><td>Nordic nRF52810, Bluetooth Low Energy 5</td></tr>
<tr><td>Датчик движения</td><td>ST LSM6DSL: акселерометр и гироскоп, по 3 оси</td></tr>
<tr><td>Память</td><td>Macronix MX25R8035F, 8 Мбит, для обновлений прошивки</td></tr>
<tr><td>Кнопка</td><td>вся крышка: зелёное дно прогибается при нажатии</td></tr>
<tr><td>Светодиод</td><td>зелёный</td></tr>
<tr><td>Батарейка</td><td>CR2032 (таблетка)</td></tr>
<tr><td>Прошивка</td><td>3.2.1-A на проверенном экземпляре; обновления приходят подписанными через приложение</td></tr>
</table>""",
    "inside_src": f"Источники: {a('flops', 'Flopsstuff/triki')}, {a('hw', 'Piwencjusz/zabka-triki-hardware')}, "
                  f"{a('gsm', 'gsmonline.pl')}.",
    "photo_front": "Triki: серебристая крышка с чёрной T",
    "photo_back": "Обратная сторона: зелёная плата с логотипом Ż",
    "photo_credit": "Фото: Flopsstuff, MIT",
    "battery": f"""<p><b>Triki не заряжается.</b> Она работает от батарейки-таблетки CR2032, как в
кухонных весах и автомобильных ключах, и эту батарейку можно заменить.</p>
<p>Слабую батарейку выдаёт неровно мигающий светодиод или частые обрывы связи (по
{a("faq", "FAQ Żabka")}). Мы также видели крышки со слабой батарейкой, которые переставали
реагировать на кнопку, пока батарейку не вынимали и не вставляли обратно.</p>
<p><b>Замена.</b> Винтов и защёлок нет: зелёное дно просто вставлено в завальцованный металлический
край. Достаточно подцепить его чем-нибудь тонким и вынуть. Перед тем как вынуть батарейку,
запомните, какой стороной она стоит.</p>
<p><b>Сколько держит</b> — зависит от использования. При постоянном подключении новая батарейка
садится примерно за неделю. Крышка, которую не трогают, спит и почти не тратит заряд.</p>""",
    "connect": """<p>Сопряжения в обычном смысле нет. Крышка называет себя <code>Triki</code> с
десятизначным номером (тот же номер показывает приложение), и с ней может работать любое
устройство, которое к ней подключится.</p>
<ul>
<li><b>Она спит</b>, когда лежит неподвижно и к ней никто не подключён. Будит её только нажатие:
если её поднять или потрясти, она не проснётся. После нажатия её видно несколько секунд.</li>
<li><b>Одно подключение за раз.</b> Пока подключён телефон, компьютер или Home Assistant, остальные её
не видят.</li>
<li>После обрыва связи её видно ещё около трёх минут, потом она засыпает.</li>
</ul>
<h3>Если не подключается</h3>
<ol>
<li>Нажмите на крышку один раз, чтобы разбудить, и подключайтесь в течение нескольких секунд.</li>
<li>Проверьте, не держит ли её другое устройство: второй телефон, компьютер или Home Assistant.
Если выключить на нём Bluetooth, крышка освободится.</li>
<li>Замените батарейку, если светодиод мигает неровно или связь рвётся.</li>
<li>Выньте батарейку на несколько секунд. Это единственный сброс у крышки; ничего не теряется.</li>
</ol>""",
    "noapp": f"""<p>Крышка использует обычный Bluetooth Low Energy, без шифрования и без аккаунта.
Сообщество разобрало её протокол ({a("elektroda", "elektroda.pl")}, {a("reddit", "r/Polska")}), и
для неё есть программы с открытым кодом. Все они неофициальные. Компьютеру нужен Bluetooth Low
Energy (Bluetooth 4.0 или новее).</p>""",
    "pg_docs": "Протокол и библиотеки", "pg_pc": "На компьютере", "pg_other": "Другое",
    "pg_hw": "Железо",
    "p_flops": "самое полное описание протокола и железа, библиотека на TypeScript",
    "p_scope": "просмотр данных датчика в терминале",
    "p_pylib": "библиотека на Python", "p_pyapi": "ещё одно API на Python",
    "p_ctrl": "программа для компьютера и понятное описание работы",
    "p_tray": "пульт в трее Windows", "p_reader": "3D-вид положения крышки (C#)",
    "p_mouse": "крышка как мышь для Android", "p_vr": "крышка как трекер SlimeVR",
    "p_esp": "клиент для ESP32", "p_find": "поиск потерянной крышки по сигналу",
    "p_hw": "фото платы, распиновка, разбор памяти и обновлений", "p_pcb": "плата в KiCad",
    "ha": f"""<p><a href="{GH}">ha-triki</a> — интеграция с открытым кодом, которая делает из крышки
пульт для {a("ha", "Home Assistant")}. Нажатие, долгое, двойное и тройное нажатие, вращение крышки
на столе как ручки, наклон и встряхивание приходят в Home Assistant как события. Автоматизации по
ним могут, например, включать или приглушать свет и запускать сцены. Работает локально, без
приложения Żappka и без облака.</p>
<p>У интеграции есть карточка, которая показывает крышку в 3D. Ниже она воспроизводит запись
настоящей крышки.</p>""",
    "replay": "Записано на настоящей Triki",
    "captions": ["Поворот на столе: шаги крутилки", "Поворот на столе: шаги крутилки",
                 "Наклон в руке вправо и влево", "Нажатие, двойное, удержание",
                 "Перевёрнута зелёной стороной вверх", "Встряхивание"],
    "ha_need": f"""<h3>Что понадобится</h3>
<ul>
<li>Home Assistant версии 2025.8 или новее.</li>
<li>Bluetooth-приёмник рядом с крышкой. Плата ESP32 с ESPHome Bluetooth proxy рядом с крышкой
подключается меньше чем за секунду; встроенный Bluetooth Raspberry Pi в другом конце комнаты часто
подключается медленно или вовсе нет (<a href="{L["proxy"]}">Bluetooth proxy для начинающих</a>, на английском).</li>
</ul>
<h3>Установка</h3>
<ol>
<li>Найдите <b>Żabka Triki</b> в <a href="{HACS}">HACS</a>, скачайте и перезапустите Home
Assistant.</li>
<li>Нажмите на крышку. Она появится в разделе <i>Обнаружено</i> в Настройки → Устройства и службы;
подтвердите её и отметьте нужные жесты.</li>
<li>Добавьте на панель карточку <b>Triki live 3D</b> и нажмите <b>Проверка</b>: она пройдёт по
кнопке, крутилке и жестам.</li>
</ol>
<p>Готовые блюпринты: <a href="{BP}triki_light.yaml">пульт для света</a> и
<a href="{BP}triki_actions.yaml">своё действие на каждый жест</a>.
Документация (на английском): <a href="{DOCS}installation.md">установка</a>,
<a href="{DOCS}configuration.md">настройки</a>,
<a href="{DOCS}events-and-automations.md">события и автоматизации</a>,
<a href="{DOCS}troubleshooting.md">проблемы</a>.
Другая интеграция для Home Assistant, которая показывает сырые данные датчиков: {a("unoff", "triki_unofficial")}.</p>""",
    "faq": [
        ("Как зарядить Triki?",
         "Никак: зарядки у Triki нет. Она работает от батарейки-таблетки CR2032, которую меняют."),
        ("Какая батарейка в Triki?", "Батарейка-таблетка CR2032."),
        ("Почему Triki не подключается?",
         "Крышка спит, и будит её только нажатие, а подключение она принимает одно за раз. Нажмите на "
         "неё один раз, проверьте, что она не подключена к другому телефону, компьютеру или Home "
         "Assistant, а если не поможет, замените батарейку или выньте её на несколько секунд."),
        ("Как сбросить Triki?",
         "Выньте батарейку на несколько секунд. Кнопки сброса нет, и ничего не теряется."),
        ("Работает ли Triki без приложения Żappka?",
         "Да. Это обычное устройство Bluetooth Low Energy; программы сообщества и интеграция для Home "
         "Assistant подключаются к нему напрямую. Они неофициальные."),
        ("Работает ли Triki на компьютере?",
         "Да, на компьютере с Bluetooth Low Energy, через программу сообщества, например TRIKI-Control "
         "или TrikiControl."),
        ("Может ли Triki управлять светом?",
         "Да, через Home Assistant и интеграцию ha-triki: нажатия, вращение, наклон и встряхивание "
         "становятся событиями для автоматизаций."),
    ],
    "foot": "Эту страницу ведёт проект ha-triki, а не Żabka. Triki, Żappka и Żabka — товарные знаки их "
            "владельцев; проект не связан с Żabka Polska и Caps Apps. Использование крышки вне "
            "приложения — на Ваш риск.",
    "foot_src": "Код на GitHub",
    "hint": "Эта страница есть и на русском",
    "not_found": "Такой страницы нет.",
    "home": "На главную",
}

ORDER = ["what", "inside", "battery", "connect", "noapp", "ha", "faq"]


def e(s: str) -> str:
    return html.escape(s, quote=True)


def head(lang: str, t: dict, path: str, root: str, *, index: bool = True) -> str:
    url = BASE + path
    alt = "".join(f'<link rel="alternate" hreflang="{k}" href="{BASE}{v}">' for k, v in LANGS.items())
    alt += f'<link rel="alternate" hreflang="x-default" href="{BASE}">'
    og_locale = {"en": "en_US", "pl": "pl_PL", "ru": "ru_RU"}[lang]
    ld = [
        {"@context": "https://schema.org", "@type": "TechArticle", "headline": t["h1"], "description": t["desc"],
         "inLanguage": lang, "url": url, "about": {"@type": "Product", "name": "Żabka Triki", "model": "CAP001"}},
        {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": lang, "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": ans}}
            for q, ans in t["faq"]]},
    ]
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t["title"])}</title>
<meta name="description" content="{e(t["desc"])}">
{'<meta name="robots" content="noindex">' if not index else ''}
<link rel="canonical" href="{url}">
{alt}
<meta property="og:type" content="article">
<meta property="og:title" content="{e(t["title"])}">
<meta property="og:description" content="{e(t["desc"])}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}assets/og-{lang}.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:locale" content="{og_locale}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#111418">
<link rel="icon" href="{root}assets/icon.png">
<link rel="stylesheet" href="{root}assets/style.css">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head>
"""


def header(lang: str, root: str) -> str:
    sw = "".join(
        f'<a href="{root}{p}" hreflang="{k}" lang="{k}"{" aria-current=page" if k == lang else ""}>{k.upper()}</a>'
        for k, p in LANGS.items())
    return f"""<header class="top"><div class="wrap">
<a class="brand" href="{root}{LANGS[lang]}">Triki</a>
<nav class="langs" aria-label="Language">{sw}</nav>
<a class="gh" href="{GH}">GitHub</a>
</div></header>
<div class="hint" id="hint" hidden></div>
"""


def page(lang: str) -> str:
    t = T[lang]
    path = LANGS[lang]
    root = "../" if path else ""
    hints = {k: T[k]["hint"] for k in LANGS}
    toc = "".join(f'<li><a href="#{k}">{e(t["s"][k])}</a></li>' for k in ORDER)
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(ans)}</p></details>" for q, ans in t["faq"])
    body = {
        "what": t["what"],
        "inside": f"""<div class="inside">{t["inside"]}
<figure class="photos"><img src="{root}assets/triki-front.jpg" alt="{e(t["photo_front"])}" width="160" height="160" loading="lazy">
<img src="{root}assets/triki-back.jpg" alt="{e(t["photo_back"])}" width="160" height="160" loading="lazy">
<figcaption>{e(t["photo_credit"])}</figcaption></figure></div>
<p class="src">{t["inside_src"]}</p>""",
        "battery": t["battery"],
        "connect": t["connect"],
        "noapp": t["noapp"] + projects(t),
        "ha": t["ha"] + f"""
<figure class="replay" id="replay" data-lang="{lang}" data-captions='{e(json.dumps(t["captions"], ensure_ascii=False))}'>
<div class="cap"><span class="rec" aria-hidden="true"></span><span id="capText">{e(t["captions"][0])}</span><span class="src">{e(t["replay"])}</span></div>
<div class="slot"><img class="poster" src="{root}assets/poster.png" alt="" width="540" height="645" loading="lazy"></div>
</figure>""" + t["ha_need"],
        "faq": faq,
    }
    sections = "".join(f'<section id="{k}"><h2>{e(t["s"][k])}</h2>{body[k]}</section>' for k in ORDER)
    return head(lang, t, path, root) + f"""<body>
{header(lang, root)}
<div class="wrap doc">
<nav class="toc" aria-label="{e(t["toc"])}"><p>{e(t["toc"])}</p><ol>{toc}</ol></nav>
<main>
<h1>{e(t["h1"])}</h1>
<p class="lead">{e(t["lead"])}</p>
{sections}
</main>
</div>
<footer><div class="wrap">
<p>{e(t["foot"])}</p>
<p><a href="{GH}">{e(t["foot_src"])}</a> · MIT</p>
</div></footer>
<script>window.TRIKI_HINTS={json.dumps(hints, ensure_ascii=False)};window.TRIKI_PAGES={json.dumps({k: root + v for k, v in LANGS.items()})};</script>
<script type="module" src="{root}assets/replay.js"></script>
<script src="{root}assets/hint.js" defer></script>
</body>
</html>
"""


def not_found() -> str:
    t = T["en"]
    return head("en", t, "404.html", "/ha-triki/", index=False) + f"""<body>
{header("en", "/ha-triki/")}
<main class="wrap"><h1>404</h1>
<p>{e(T["en"]["not_found"])} <a href="/ha-triki/">{e(T["en"]["home"])}</a></p>
<p>{e(T["pl"]["not_found"])} <a href="/ha-triki/pl/">{e(T["pl"]["home"])}</a></p>
<p>{e(T["ru"]["not_found"])} <a href="/ha-triki/ru/">{e(T["ru"]["home"])}</a></p>
</main></body></html>
"""


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "assets").mkdir(parents=True)
    for k, p in LANGS.items():
        d = OUT / p
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page(k), encoding="utf-8")
    (OUT / "404.html").write_text(not_found(), encoding="utf-8")
    shutil.copytree(REPO / "custom_components/triki/frontend", OUT / "assets/card")
    for f in ["icon.png", "triki-front.jpg", "triki-back.jpg"]:
        shutil.copy(REPO / "docs/images" / f, OUT / "assets" / f)
    for f in ["style.css", "replay.js", "hint.js", "timeline.json"]:
        shutil.copy(HERE / "src" / f, OUT / "assets" / f)
    for f in (HERE / "src").glob("*.png"):
        shutil.copy(f, OUT / "assets" / f.name)
    # ownership proofs for the search consoles: served from the page's root as they are
    for f in (HERE / "verify").iterdir():
        shutil.copy(f, OUT / f.name)
    urls = "".join(
        f"<url><loc>{BASE}{p}</loc>"
        + "".join(f'<xhtml:link rel="alternate" hreflang="{k}" href="{BASE}{v}"/>' for k, v in LANGS.items())
        + "</url>" for p in LANGS.values())
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{urls}</urlset>\n', encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print("built", OUT)


if __name__ == "__main__":
    main()
