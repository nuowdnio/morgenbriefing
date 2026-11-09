# Morgenbriefing

Erstellt jeden Morgen automatisch ein deutschsprachiges News-Briefing aus seriösen Quellen weltweit und zeigt es auf einer handytauglichen Webseite.

- Keine API-Schlüssel, keine Kosten. Alles läuft mit Open-Source-Software bei GitHub.
- Dein Computer muss morgens nicht eingeschaltet sein.
- Themen schaltest du direkt auf der Seite an und ab. Die Auswahl merkt sich dein Browser.

## Briefing von Hand starten

1. Öffne [Briefing starten](../../actions/workflows/briefing.yml) oder tippe auf der Webseite ganz unten auf **Briefing jetzt neu erstellen**.
2. Tippe auf **Run workflow** und dann auf den grünen Knopf **Run workflow**.

Nach etwa fünf Minuten ist das neue Briefing online und in deinem Postfach. Möchtest du keine Mail, nimm vor dem Start das Häkchen bei „Briefing auch per Mail schicken“ heraus.

## Die Mail am Morgen

Jeden Morgen gegen 6 Uhr schickt dir GitHub das Briefing an die Adresse deines GitHub-Kontos. Technisch legt das Programm dafür im Reiter **Issues** einen Eintrag an und erwähnt dich darin.

- Kommt keine Mail: Prüfe den Spam-Ordner und unter [Notifications](https://github.com/settings/notifications), ob **Email** bei „Participating, @mentions and custom“ aktiv ist.
- Nur bestimmte Themen: In `config.yaml` bei `mail` zum Beispiel `topics: [deutschland, weltpolitik, klima]` eintragen. Die Themen-IDs stehen weiter unten in derselben Datei.
- Die Themenschalter gelten nur auf der Webseite, nicht in der Mail.

## Einrichten (etwa 10 Minuten, am besten am Computer)

### 1. Projekt zu GitHub bringen

1. Lege ein kostenloses Konto auf [github.com](https://github.com) an.
2. Klicke oben rechts auf **+** und dann auf **New repository**.
3. Gib einen Namen ein, z. B. `morgenbriefing`, wähle **Public** und klicke auf **Create repository**.
4. Entpacke die ZIP-Datei auf deinem Computer.
5. Klicke im neuen Repository auf **uploading an existing file**.
6. Ziehe den **gesamten Inhalt** des entpackten Ordners in das Fenster und klicke auf **Commit changes**.

Wichtig: Der Ordner `.github` muss mit hochgeladen werden. Auf dem Mac blendest du versteckte Ordner im Finder mit `Cmd + Shift + .` ein. Fehlt der Ordner nach dem Hochladen, nutze [GitHub Desktop](https://desktop.github.com) zum Hochladen.

### 2. Schreibrechte erlauben

1. Öffne im Repository **Settings → Actions → General**.
2. Wähle unten bei **Workflow permissions** die Option **Read and write permissions**.
3. Klicke auf **Save**.

### 3. Webseite einschalten

1. Öffne **Settings → Pages**.
2. Wähle bei **Source** die Option **GitHub Actions**.

### 4. Erstes Briefing starten

1. Öffne den Reiter **Actions**.
2. Klicke links auf **Briefing starten**.
3. Klicke rechts auf **Run workflow** und bestätige.

Der erste Lauf dauert länger, weil die Sprachmodelle geladen werden. Ist er grün, findest du die Adresse unter **Settings → Pages**. Sie sieht so aus: `https://DEINNAME.github.io/morgenbriefing/`. Speichere sie am Handy als Lesezeichen oder auf dem Startbildschirm.

Ab jetzt läuft alles automatisch.

## Anpassen

Dateien kannst du direkt auf GitHub bearbeiten: Datei öffnen, auf den Stift klicken, ändern, **Commit changes**.

### Quellen

In `config.yaml` steht unter `sources` jede Quelle in einer Zeile.

- **Abschalten:** `enabled: false` setzen.
- **Einschalten:** `enabled: true` setzen.
- **Neue Quelle:** Zeile kopieren und `id`, `name`, `url`, `country`, `region`, `language` und `ownership` anpassen. Nimm nur offizielle RSS-Feeds.

Unter **Actions → Quellen prüfen → Run workflow** testest du alle eingetragenen Feeds, auch die abgeschalteten. Das Ergebnis steht als Tabelle in der Zusammenfassung des Laufs. Einige bekannte Quellen wie tagesschau, BBC und The Guardian sind bereits eingetragen, aber noch abgeschaltet. Schalte nur ein, was bei dieser Prüfung funktioniert.

Andere Sprachen als Deutsch und Englisch sind möglich: `language` entsprechend setzen. Das passende Modell wird automatisch geladen.

Aktiv sind nur Medien ohne Bezahlschranke. Einträge mit `paywall: true` lassen sich nicht einschalten, das Programm bricht sonst mit einer Fehlermeldung ab. Einzelne Bezahlartikel werden zusätzlich über Muster in `exclude` aussortiert.

### Themen

Auf der Webseite wählst du Themen per Schalter an und ab. Neue Themen legst du in `config.yaml` unter `topics` an. Das Thema `weltpolitik` muss bleiben, weil es als Auffangthema dient.

Landet eine Meldung öfter im falschen Thema, ergänze passende Wörter bei `keywords`.

### Uhrzeit

Das Briefing startet um 05:40 Uhr deutscher Zeit, auch nach der Zeitumstellung. GitHub startet geplante Läufe manchmal verspätet, die Mail kann also auch etwas später kommen.

Für eine andere Zeit passt du in `.github/workflows/briefing.yml` die drei `cron`-Zeilen an und bei `--not-before` die früheste Uhrzeit. Die erste Zahl sind die Minuten, die zweite die Stunde in **UTC** (im Winter eine, im Sommer zwei Stunden hinter Deutschland).

### Namen und Begriffe

In `glossary.yaml` legst du fest, was unübersetzt bleibt (`keep`) und was nach der Übersetzung ersetzt wird (`replace`).

### Gruppierung

Werden verschiedene Ereignisse zusammengeworfen, erhöhe in `config.yaml` den Wert `similarity_threshold`, etwa auf `0.68`. Werden gleiche Ereignisse nicht erkannt, senke ihn, etwa auf `0.55`.

### Übersetzer

Standard ist Argos Translate. Unter **Actions → Übersetzer vergleichen → Run workflow** siehst du 20 aktuelle Meldungen in einer Tabelle, übersetzt von Argos und von Opus-MT. Gefällt dir Opus-MT besser, setze in `config.yaml` `translator: opus`. Opus-MT ist hier nur für Englisch nach Deutsch eingerichtet.

## So funktioniert es

1. Offizielle RSS-Feeds werden abgerufen, `robots.txt` wird dabei beachtet.
2. Alte Meldungen, Dubletten, Liveticker, Videohinweise und Meinungsstücke werden aussortiert.
3. Ein lokales mehrsprachiges Modell erkennt Berichte über dasselbe Ereignis, auch über Sprachgrenzen.
4. Themen werden über Adresse, Schlagwörter und Ähnlichkeit zugeordnet.
5. Regeln gewichten nach Zahl unabhängiger Quellen, Regionen, Aktualität und Quellengewicht. Ein Abzug für bereits häufige Regionen sorgt für Vielfalt.
6. Die Zusammenfassung besteht nur aus Sätzen, die in den Feeds stehen. Nichts wird dazuerfunden.
7. Fremdsprachige Texte werden lokal übersetzt.

## Grenzen

- Maschinelle Übersetzungen können holprig sein. Bei wichtigen Details zählt der verlinkte Originalartikel.
- „Mehr dazu“ zeigt, was die Feeds über die Kurzfassung hinaus enthalten, je Quelle bis zu 700 Zeichen (`max_detail_chars`). Komplette Artikel fremder Medien werden bewusst nicht gespeichert, der volle Text ist immer einen Tipp entfernt über den Link zum Original.
- Ob ein Medium frei lesbar ist, ist in `config.yaml` je Quelle festgelegt und wird nicht bei jedem Artikel geprüft. Führt ein Medium später eine Bezahlschranke ein, setze dort `enabled: false` und `paywall: true`.
- Mit einem kostenlosen Konto ist die Seite öffentlich erreichbar. Suchmaschinen werden zwar ausgesperrt, trotzdem solltest du den Link nicht weitergeben, weil die Seite übersetzte Kurztexte fremder Medien enthält.

## Wenn etwas nicht klappt

- **Roter Lauf unter Actions:** Das letzte Briefing bleibt online. Öffne den Lauf und lies den Schritt mit dem roten Kreuz. GitHub benachrichtigt dich standardmäßig per E-Mail.
- **„Nur X Quellen erreichbar“:** Zu viele Feeds sind ausgefallen. Starte **Quellen prüfen**.
- **Fehler beim Speichern des Archivs:** Prüfe Schritt 2 der Einrichtung.
- **Seite zeigt „Noch kein Briefing“:** Prüfe Schritt 3 und ob ein Lauf grün durchgelaufen ist.
- **Einzelne Quelle fehlt:** Das steht unten auf der Seite und stoppt das Briefing nicht.

## Für Entwickler

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m pytest -q
node --test tests/app.test.js
python -m briefing.main
python -m http.server -d site
```

Feed-Inhalte gelten als nicht vertrauenswürdig: HTML wird beim Einlesen entfernt, die Seite fügt Texte nur per `textContent` ein und lässt nur http(s)-Links zu.
