# Einrichtung: WebUntis-Sync auf Google Apps Script

Diese Fassung läuft auf Googles Servern — immer an, kein Rechner nötig, keine
Nutzungsbeschränkung wie bei GitHub Actions.

Alles hier machst du im Browser. Dauer: etwa 10 Minuten.

---

## Schritt 1: Projekt anlegen

1. Öffne **https://script.google.com/home/projects/create**
   (mit dem Google-Konto angemeldet sein, in dem der Kalender liegt)
2. Oben links auf **„Unbenanntes Projekt"** klicken und umbenennen in: `Stundenplan-Sync`

## Schritt 2: Code einfügen

3. Im Editor siehst du eine Datei `Code.gs` mit ein paar Zeilen Beispielcode.
4. Klick in den Code, drück **Cmd+A** (alles markieren) und **Entf**.
5. Öffne die Datei [Code.gs](Code.gs) aus diesem Ordner, markiere alles (**Cmd+A**),
   kopiere (**Cmd+C**) und füge es im Apps-Script-Editor ein (**Cmd+V**).
6. **Cmd+S** zum Speichern.

## Schritt 3: Kalender-Dienst aktivieren

7. Links in der Seitenleiste steht **„Dienste"** mit einem **+** daneben. Klick das **+**.
8. In der Liste **„Google Calendar API"** auswählen.
9. Unten rechts auf **„Hinzufügen"** klicken.

   Danach muss links unter „Dienste" ein Eintrag **`Calendar`** stehen.

## Schritt 4: Zugangsdaten hinterlegen

Die Zugangsdaten kommen **nicht** in den Code, sondern in die Skripteigenschaften.
Dort sind sie nur für dich sichtbar.

10. Links auf das Zahnrad **„Projekteinstellungen"** klicken.
11. Ganz nach unten scrollen zu **„Skripteigenschaften"**.
12. Auf **„Skripteigenschaft hinzufügen"** klicken und diese fünf Paare eintragen:

| Eigenschaft | Wert |
|---|---|
| `UNTIS_SERVER` | dein WebUntis-Server, z. B. `xyz.webuntis.com` (steht in der Browser-URL) |
| `UNTIS_SCHOOL` | der technische Schulname (der Wert hinter `?school=` in der URL) |
| `UNTIS_USER` | dein WebUntis-Benutzername |
| `UNTIS_PASSWORD` | dein WebUntis-Passwort |
| `GCAL_ID` | die Kalender-ID von `Schule` (endet auf `@group.calendar.google.com`) |

13. Auf **„Skripteigenschaften speichern"** klicken.

## Schritt 5: Einrichtung prüfen

14. Zurück zum Editor (links auf das Code-Symbol).
15. Oben in der Leiste steht ein Auswahlfeld mit einem Funktionsnamen. Wähle dort
    **`einrichtungPruefen`** aus.
16. Auf **„Ausführen"** klicken.
17. Beim ersten Mal fragt Google nach Berechtigungen:
    - **„Berechtigungen überprüfen"** klicken
    - dein Google-Konto auswählen
    - Es erscheint **„Google hat diese App nicht überprüft"** — das ist normal, es ist
      dein eigenes Skript. Klick auf **„Erweitert"**, dann unten auf
      **„Zu Stundenplan-Sync (unsicher)"**
    - **„Zulassen"** klicken
18. Unten öffnet sich das Ausführungsprotokoll. Es sollte ungefähr so aussehen:

    ```
    Server: xyz.webuntis.com | Schule: xyz | Benutzer: …
    WebUntis-Anmeldung: OK, personId 1234
    Kalender: "Schule" (Europe/Berlin)
    Stundenplan: 76 Stunden im Fenster 2026-09-14 bis 2026-10-12
    Schreibrecht im Kalender: OK
    Einrichtung vollstaendig in Ordnung.
    ```

    Steht dort eine Fehlermeldung, siehe **Wenn etwas nicht klappt** unten.

## Schritt 6: Probelauf

19. Funktion **`probelauf`** auswählen, **„Ausführen"**.
20. Im Protokoll sollte etwas stehen wie: `PROBELAUF – ganzes Fenster bis 2027-03-16:
    0 angelegt, 0 aktualisiert, 0 geloescht, 412 unveraendert`.

    **Das ist der wichtige Moment:** Wenn dort `0 angelegt` steht, hat das Skript deine
    vorhandenen Termine korrekt wiedererkannt. Stünde dort eine grosse Zahl bei
    „angelegt", würde alles doppelt — dann bitte **nicht** weitermachen und Bescheid
    sagen.

## Schritt 7: Automatik einschalten

21. Funktion **`ausloeserEinrichten`** auswählen, **„Ausführen"**.
22. Im Protokoll: `Ausloeser angelegt: sync() laeuft alle 1 Minute(n).`

Ab jetzt läuft der Sync von allein.

## Schritt 8: GitHub abschalten

Damit nicht beides gleichzeitig läuft:

23. Öffne https://github.com/avwberlin/untis-google-kalender/actions/workflows/sync.yml
24. Rechts auf die drei Punkte **⋯** klicken → **„Disable workflow"**.

Dasselbe für den Keepalive-Workflow (der wird dann auch nicht mehr gebraucht).

---

## Bedienung im Alltag

| Was | Wie |
|---|---|
| Läuft es? | script.google.com → Projekt öffnen → links **„Ausführungen"** |
| Sofort synchronisieren | Funktion `sync` auswählen, „Ausführen" |
| Sehen, was passieren würde | Funktion `probelauf` |
| Alles zurücksetzen | Funktion `alleEntfernen` (löscht nur die vom Skript angelegten Termine) |
| Automatik ausschalten | Funktion `ausloeserEntfernen` |

## Takt und Zeiten ändern

Ganz oben in `Code.gs` steht der Block `EINSTELLUNGEN`:

```js
  endDatum: '2027-03-16',          // letzter Tag, der übertragen wird
  nahTage: 14,                     // dieses Fenster bei JEDEM Lauf prüfen
  fernIntervallMinuten: 30,        // ganzes Fenster nur alle 30 Minuten prüfen
  maxSchreibvorgaengeProLauf: 100, // Rest kommt beim nächsten Lauf
  vonStunde: 6,                    // ab 6 Uhr Berliner Zeit
  bisStunde: 19,                   // bis 19 Uhr
  nurWerktags: true,               // Samstag und Sonntag aus
  mindestAbstandSekunden: 60,      // frühestens jede Minute ein echter Sync
  ausloeserMinuten: 1,             // Takt des Zeitauslösers
```

### Warum zwei Fenster?

Die nächsten 14 Tage werden bei **jedem** Lauf geprüft — dort passieren die
kurzfristigen Änderungen. Der gesamte Zeitraum bis zum Enddatum wird alle 30 Minuten
geprüft, damit auch eine Änderung im Januar ankommt, ohne das Tageskontingent zu
sprengen.

Nach jeder Änderung **Cmd+S** drücken. Änderst du `ausloeserMinuten`, danach einmal
`ausloeserEinrichten` erneut ausführen.

## Das Google-Kontingent

Kostenlose Google-Konten dürfen Skripte insgesamt **90 Minuten pro Tag** über
Zeitauslöser laufen lassen. Diese Einstellung verbraucht etwa **60 Minuten pro Tag**:

- Außerhalb der Schulzeit bricht das Skript sofort ab und kostet fast nichts.
- Während der Schulzeit dauert ein Sync etwa 4 Sekunden.

Sollte Google trotzdem eine Kontingentmeldung schicken, in `EINSTELLUNGEN` einfach
`ausloeserMinuten: 5` setzen und `ausloeserEinrichten` erneut ausführen. Dann sind es
nur noch etwa 12 Minuten pro Tag.

## Wenn etwas nicht klappt

| Meldung | Ursache und Lösung |
|---|---|
| `Diese Skript-Eigenschaften fehlen: …` | Schritt 4 unvollständig — Namen müssen exakt stimmen, Großschreibung beachten |
| `WebUntis-Anmeldung abgelehnt` | Passwort oder Benutzername falsch |
| `Calendar is not defined` | Schritt 3 vergessen — Google Calendar API als Dienst hinzufügen |
| `Not Found` beim Kalender | `GCAL_ID` falsch. Google Kalender → Einstellungen → `Schule` → „Kalender integrieren" → Kalender-ID |
| `Service invoked too many times` | Kontingent erschöpft — `ausloeserMinuten` auf 5 setzen |
| Termine doppelt | Sofort `ausloeserEntfernen` ausführen und Bescheid sagen |

## Was diese Fassung nicht kann

**Hausaufgaben.** Genau wie die Python-Fassung: Der WebUntis-Endpunkt
`/WebUntis/api/homeworks/lessons` antwortet bei dieser Schule immer mit HTTP 500.
Das ist ein Fehler auf dem WebUntis-Server, nicht im Skript.

## Verhältnis zur Python-Fassung

Beide erzeugen **identische Termin-Kennungen und Inhalts-Hashes** — nachgerechnet und
für alle 75 vorhandenen Termine bestätigt. Man kann daher jederzeit zwischen beiden
wechseln, ohne dass Termine doppelt entstehen. Es darf nur immer **eine von beiden**
gleichzeitig aktiv sein.
