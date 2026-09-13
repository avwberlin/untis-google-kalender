# WebUntis → Google Kalender

Überträgt den Stundenplan aus WebUntis vollautomatisch in einen eigenen Google-Kalender
namens **Schule**. Ausfälle, Vertretungen, Raum- und Lehrerwechsel, Klausuren und
Lehrertexte kommen ohne Zutun mit. Der Sync läuft auf GitHub Actions, es muss also
kein Rechner eingeschaltet sein.

## Was ankommt

| Information | Wo sie landet |
|---|---|
| Fach, Lehrer, Raum | im Titel: `Mathe · Schmidt · A203` |
| Raum | zusätzlich im Google-Feld „Ort" |
| Stundenausfall | Titel `FÄLLT AUS: …`, graue Farbe, blockiert die Verfügbarkeit **nicht** |
| Vertretung, Raumwechsel | orange Farbe, Details in der Beschreibung: `Raum: B105 (statt: A203)` |
| Klausuren und Prüfungen | rote Farbe, Details in der Beschreibung |
| Vertretungstexte, Klassenbuchtexte, Notizen | in der Beschreibung |
| Ferien und unterrichtsfreie Tage | es werden schlicht keine Termine angelegt |

**Ausnahme: Hausaufgaben kommen derzeit nicht mit.** Der zuständige WebUntis-Endpunkt
`/WebUntis/api/homeworks/lessons` antwortet bei dieser Schule ausnahmslos mit HTTP 500 —
geprüft ohne Parameter, mit verschiedenen Datumsformaten, für einzelne Tage und Wochen
sowie zusätzlich in einem bereits abgeschlossenen Schuljahr. Das ist ein Fehler auf dem
Server der Schule, nicht in diesem Programm. Die Alternative JSON-RPC kennt überhaupt
keine Hausaufgaben-Funktion. Das Modul ist in [untis.py](untis.py) als Klasse
`HausaufgabenModul` bereits gebaut, aber über den Schalter `HAUSAUFGABEN_AKTIV = False`
abgeschaltet. Sollte Untis den Fehler beheben, genügt es, diesen Schalter auf `True` zu
setzen und die Feldzuordnung gegen die dann tatsächliche Antwort zu prüfen.

## Termine selbst löschen

Löschst du einen Termin von Hand im Google-Kalender, **bleibt er gelöscht**. Das
Skript legt ihn nicht wieder an. Nützlich für Stunden, die dich nicht interessieren
oder die du ohnehin schon kennst.

Wie das funktioniert: Google behält gelöschte Termine als Grabstein mit
`status = "cancelled"`. Der Sync fragt diese Liste mit ab und überspringt die
betroffenen Kennungen beim Anlegen.

**Zwei Einschränkungen, die du kennen solltest:**

1. Google räumt diese Grabsteine irgendwann ab (der Zeitraum ist nicht garantiert).
   Danach kann ein so gelöschter Termin wieder auftauchen. Dann einfach erneut löschen.
2. Ein gelöschter Termin bleibt auch dann weg, wenn Untis die Stunde später ändert –
   du bekommst für diese eine Stunde also keine Ausfall- oder Vertretungsmeldung mehr.

Einen versehentlich gelöschten Termin bekommst du am einfachsten zurück, indem du ihn
im Google-Kalender-Papierkorb wiederherstellst.

## Termine verschieben oder umbenennen

Das bleibt ebenfalls bestehen. Der Sync vergleicht nur die Untis-Daten; solange sich
dort nichts ändert, fasst er den Termin nicht an. Ändert Untis aber etwas an der Stunde,
wird der Termin überschrieben und deine Änderung geht verloren.

## Ausgefallene Stunden werden nicht gelöscht

Sie bleiben als grauer Termin stehen, damit sichtbar ist, dass die Stunde ausfällt.
Weil sie auf „frei" gestellt sind, blockieren sie keine Verfügbarkeit.

## Links

* **Repository:** https://github.com/avwberlin/untis-google-kalender
* **Actions (Laufprotokolle):** https://github.com/avwberlin/untis-google-kalender/actions
* **Kalender:** https://calendar.google.com/calendar/r

## Sync manuell auslösen

1. [Repository auf GitHub öffnen](https://github.com/avwberlin/untis-google-kalender).
2. Oben auf den Reiter **Actions** klicken.
3. Links **Stundenplan-Sync** auswählen.
4. Rechts auf **Run workflow** klicken, dann noch einmal auf den grünen Knopf **Run workflow**.
5. Nach etwa einer Minute die Zeile anklicken, um das Protokoll zu sehen.

## Lokal ausführen

```bash
.venv/bin/python sync.py --dry-run
```

Drei Betriebsmodi:

| Befehl | Wirkung |
|---|---|
| `python sync.py --dry-run` | zeigt nur an, was passieren würde; schreibt nichts |
| `python sync.py` | führt den Sync aus |
| `python sync.py --purge` | **Notausstieg**: löscht alle vom Skript angelegten Termine im Fenster |

`--purge` fasst ausschließlich Termine an, die das Skript selbst angelegt hat. Eigene
Termine im Kalender `Schule` bleiben unberührt.

## Takt ändern

Der Sync läuft **alle 2 Minuten**. Das steckt nicht im Cron-Zeitplan, sondern in einer
Schleife innerhalb des Workflows – siehe [.github/workflows/sync.yml](.github/workflows/sync.yml):

```yaml
          TAKT: "120"            # Sekunden zwischen zwei Syncs
          FEIERABEND_UTC: "17"   # ab dieser UTC-Stunde wird nicht mehr gesynct
          MAX_LAUFZEIT: "19800"  # Schleife endet spätestens nach 5 h 30 min
```

Langsamer: `TAKT` erhöhen, z. B. `"300"` für alle 5 Minuten.

### Kurz testen, ohne den Zeitplan anzufassen

Beim manuellen Start (Actions → Stundenplan-Sync → Run workflow) lassen sich Takt,
Laufzeit und Feierabendstunde einmalig überschreiben. Nützlich, um abends zu prüfen,
ob die Schleife läuft:

| Feld | Testwert | Bedeutung |
|---|---|---|
| `takt` | `30` | alle 30 Sekunden syncen |
| `max_laufzeit` | `150` | nach 2,5 Minuten aufhören |
| `feierabend_utc` | `99` | Feierabend-Prüfung abschalten |

### Warum eine Schleife und kein häufigerer Cron?

GitHub drosselt geplante Workflows massiv. Gemessen: Von 52 angeforderten Starts pro Tag
(`*/15`) wurden tatsächlich nur etwa **3** ausgeführt. Der Cron-Eintrag bleibt deshalb
bewusst häufig stehen – aber jeder Start, den GitHub tatsächlich zulässt, startet nun eine
Schleife, die den restlichen Schultag abdeckt.

`cancel-in-progress: true` sorgt dafür, dass ein neuer Start die alte Schleife ablöst,
statt sich dahinter aufzustauen. Ein Abbruch mitten im Sync ist unkritisch, weil jeder
Lauf idempotent ist.

### Warum das Repository öffentlich ist

Die Schleife verbraucht etwa 990 Actions-Minuten pro Tag. Für private Repositories wären
im kostenlosen Plan nur 2.000 Minuten **im Monat** verfügbar – das würde nach zwei Tagen
reißen. Für öffentliche Repositories sind die Actions-Minuten **unbegrenzt**.

Deshalb ist das Repository öffentlich. Die Zugangsdaten sind davon nicht betroffen: Sie
liegen als verschlüsselte GitHub-Secrets und sind auch in öffentlichen Repositories für
Fremde unsichtbar. Schulname und Personennummer wurden vor der Veröffentlichung aus Code
und Historie entfernt.

Wer es lieber privat hätte: Repository auf privat stellen und in
[sync.yml](.github/workflows/sync.yml) die Schleife entfernen, also nur noch einen
einzelnen `python sync.py`-Aufruf stehen lassen. Dann gilt wieder der gedrosselte
Cron-Takt von etwa dreimal täglich.

## Keepalive

GitHub schaltet geplante Workflows nach **60 Tagen ohne Repo-Aktivität** automatisch ab.
Damit der Sync nicht stillschweigend stehenbleibt, läuft
[.github/workflows/keepalive.yml](.github/workflows/keepalive.yml) einmal pro Woche und
erzeugt einen kleinen Commit.

## Fehlerbenachrichtigung

Schlägt ein Lauf fehl, verschickt GitHub automatisch eine E-Mail. Zusätzliche Push- oder
Telegram-Nachrichten gibt es bewusst nicht.

Ein **leerer Stundenplan während der Ferien ist kein Fehler** und löst keine Mail aus.
Fehlgeschlagene Anmeldungen, HTTP-Fehler und ein unerwartet leerer Plan während der
Schulzeit dagegen schon.

## Was tun, wenn WebUntis seine interne API ändert

Der Sync holt die Stundenplandaten über die interne REST-API der WebUntis-Weboberfläche.
Die ist nicht dokumentiert und kann sich ohne Ankündigung ändern. Typisches Anzeichen:
Der Workflow schlägt fehl mit „Stundenplan abrufen: HTTP 404" oder „HTTP 403".

Die Datenquelle ist deshalb austauschbar gebaut. In [untis.py](untis.py) gibt es zwei
Umsetzungen derselben Schnittstelle:

* `RestQuelle` — die interne REST-API (Standard, beste Daten)
* `JsonRpcQuelle` — die stabilere, ältere JSON-RPC-Schnittstelle als Reserve

**Umstellen auf die Reserve:** In [sync.py](sync.py) den Import und die eine Zeile ändern,
in der die Quelle erzeugt wird:

```python
from untis import JsonRpcQuelle          # statt RestQuelle
...
quelle = JsonRpcQuelle(konfiguration["server"], konfiguration["schule"],
                       konfiguration["benutzer"], konfiguration["passwort"])
```

Die JSON-RPC-Quelle liefert etwas weniger: keine Prüfungszuordnung und teilweise gröbere
Vertretungsangaben. Der Rest funktioniert unverändert.

**Wenn beides nicht mehr geht:** `explore.py` bis `explore9.py` im Repository sind die
Erkundungsskripte, mit denen die funktionierenden Endpunkte ursprünglich gefunden wurden.
Sie geben Statuscode und Antwortanfang jedes Endpunkts aus und lassen sich erneut laufen
lassen, um zu sehen, was sich geändert hat.

## Technische Eckpunkte

* **Kein Zustandsspeicher.** Der Google-Kalender selbst ist der Speicher. Jeder Termin
  bekommt eine aus der Untis-Stunde berechnete, gleichbleibende Kennung
  (`untis` + SHA1 aus Stunden-ID, Datum und Startzeit). Derselbe Untis-Termin ist bei
  jedem Lauf derselbe Google-Termin, deshalb entstehen keine Duplikate.
* **Änderungserkennung über einen Inhalts-Hash**, abgelegt in
  `extendedProperties.private.contentHash`. Ist er unverändert, wird gar kein
  API-Aufruf gemacht. Ein zweiter Lauf direkt nach dem ersten ergibt daher
  `0 angelegt, 0 aktualisiert, 0 gelöscht`.
* **Von Hand gelöschte Termine** werden über die Grabsteine (`status = "cancelled"`)
  erkannt und nicht wieder angelegt.
* **Schutz fremder Termine.** Angefasst werden nur Termine mit
  `extendedProperties.private.managedBy = "untis-sync"`. Vor jedem Löschen wird das
  ein zweites Mal geprüft.
* **Zeitzone** immer explizit `Europe/Berlin`, nie naive Zeitstempel.
* **Wiederholung mit wachsender Wartezeit** (3 Versuche) bei allen WebUntis-Aufrufen,
  weil die Untis-Server regelmäßig kurz nicht erreichbar sind.
* **Googles Schreibratenbegrenzung** wird abgefangen (6 Versuche mit wachsender
  Wartezeit, plus eine kurze Pause zwischen den Schreibvorgängen). Nötig ist das nur
  beim allerersten Lauf, wenn rund 100 Termine auf einmal angelegt werden.
* **Schuljahresgrenzen** werden beachtet: WebUntis lehnt Abfragen ab, die zwei
  Schuljahre überspannen. Das Fenster wird automatisch zugeschnitten.

## Zweite Fassung: Google Apps Script

Im Ordner [appsscript/](appsscript/) liegt dieselbe Funktion noch einmal als
Google-Apps-Script. Die läuft auf Googles Servern statt auf GitHub Actions:

* rund um die Uhr verfügbar, kein Rechner nötig
* Takt bis herunter auf **eine Minute**
* keine Actions-Minuten, keine Drosselung geplanter Läufe
* kein Service-Konto nötig — das Skript läuft im eigenen Google-Konto

Beide Fassungen erzeugen **identische Termin-Kennungen und Inhalts-Hashes**
(nachgerechnet und für alle 75 vorhandenen Termine bestätigt). Man kann daher
zwischen ihnen wechseln, ohne dass Termine doppelt entstehen — es darf nur immer
**eine von beiden** aktiv sein.

Einrichtung: [appsscript/ANLEITUNG.md](appsscript/ANLEITUNG.md)

## Dateien

| Datei | Zweck |
|---|---|
| [sync.py](sync.py) | Hauptskript mit den drei Betriebsmodi |
| [untis.py](untis.py) | WebUntis-Anbindung, austauschbare Datenquellen |
| [kalender.py](kalender.py) | Google-Kalender-Anbindung und Schutzregeln |
| [modelle.py](modelle.py) | internes Datenmodell, Titel- und Beschreibungsaufbau |
| `explore*.py` | Erkundungsskripte aus der Analysephase |
| `.env` | Zugangsdaten, **wird nie hochgeladen** |
| `service-account.json` | Google-Schlüssel, **wird nie hochgeladen** |

## Zugangsdaten

Lokal stehen sie in `.env` und `service-account.json`. Beide Dateien sind über
[.gitignore](.gitignore) vom Repository ausgeschlossen und landen nie auf GitHub.

Auf GitHub liegen sie als verschlüsselte Secrets:
`UNTIS_SERVER`, `UNTIS_SCHOOL`, `UNTIS_USER`, `UNTIS_PASSWORD`,
`GOOGLE_SERVICE_ACCOUNT_JSON`, `GCAL_ID`.
