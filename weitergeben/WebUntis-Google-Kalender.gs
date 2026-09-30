/**
 * ============================================================================
 *  WebUntis  ->  Google Kalender
 * ============================================================================
 *
 *  Traegt den Stundenplan aus WebUntis automatisch in einen Google-Kalender ein.
 *  Laeuft auf Googles Servern, rund um die Uhr, alle zwei Minuten. Es muss kein
 *  Rechner eingeschaltet sein.
 *
 *  Was uebertragen wird:
 *    - Fach, Lehrer, Raum im Titel:  "Mathe · Schmidt · A203"
 *    - Raum zusaetzlich im Feld "Ort"
 *    - Stundenausfall:   Titel "FAELLT AUS: ...", grau, blockiert die
 *                        Verfuegbarkeit nicht
 *    - Vertretung und Raumwechsel: orange, Details in der Beschreibung
 *                        ("Raum: B105 (statt: A203)")
 *    - Klausuren und Pruefungen: rot
 *    - Vertretungstexte, Klassenbuchtexte und Lehrernotizen
 *    - Ferien: es werden einfach keine Termine angelegt, der Tag bleibt leer
 *
 *  Was NICHT geht:
 *    - Hausaufgaben. Der zustaendige Endpunkt /WebUntis/api/homeworks/lessons
 *      antwortet bei manchen Schulen dauerhaft mit HTTP 500. Das Modul ist
 *      vorhanden, aber ueber HAUSAUFGABEN_AKTIV abgeschaltet. Wer Glueck hat,
 *      kann den Schalter auf true stellen und es probieren.
 *
 *  Sicherheit:
 *    - Zugangsdaten stehen NICHT im Code, sondern in den Skripteigenschaften.
 *    - Angefasst werden nur Termine mit der Markierung managedBy=untis-sync.
 *      Eigene Termine im selben Kalender bleiben unberuehrt.
 *    - Von Hand geloeschte Termine werden nicht wieder angelegt.
 *
 *  Schutz vor Datenverlust (wichtig, aus einem echten Vorfall gelernt):
 *    - LOESCHSCHUTZ: Liefert WebUntis weniger als 70 Prozent der Stunden, die
 *      im Kalender stehen, wird NICHTS geloescht, sondern nur ergaenzt. Eine
 *      kurze Stoerung bei WebUntis kann so keinen Schultag mehr kosten.
 *    - Der Sync merkt sich, welche Termine er SELBST geloescht hat. Taucht so
 *      eine Stunde spaeter wieder auf, wird sie neu angelegt. Nur Loeschungen
 *      durch den Nutzer bleiben dauerhaft.
 *    - WAECHTER: prueft einmal taeglich, ob an einem Schultag der naechsten
 *      zwei Wochen Stunden fehlen, und schickt dann eine E-Mail.
 *    - Falls doch etwas fehlt: Funktion "reparieren" ausfuehren.
 *
 * ----------------------------------------------------------------------------
 *  EINRICHTUNG  (etwa 15 Minuten, alles im Browser)
 *
 *  Die Beschriftungen unten sind die englischen aus der Google-Oberflaeche.
 * ----------------------------------------------------------------------------
 *
 *  SCHRITT 1 - Eigenen Kalender anlegen
 *    Nicht in den Hauptkalender schreiben lassen, sondern einen eigenen nehmen.
 *    a) https://calendar.google.com/calendar/u/0/r/settings/createcalendar
 *    b) Name z. B. "Schule", Zeitzone auf die eigene stellen, "Create calendar"
 *    c) Links in der Seitenleiste den neuen Kalender anklicken, runterscrollen
 *       zu "Integrate calendar" und die "Calendar ID" kopieren.
 *       Sie sieht so aus:  abc123...@group.calendar.google.com
 *
 *  SCHRITT 2 - Apps-Script-Projekt anlegen
 *    a) https://script.google.com/home/projects/create
 *    b) Oben links "Untitled project" anklicken und umbenennen,
 *       z. B. "Stundenplan-Sync"
 *    c) Im Editor den vorhandenen Beispielcode komplett markieren (Cmd+A bzw.
 *       Strg+A), loeschen, und DIESE Datei vollstaendig einfuegen. Speichern.
 *
 *  SCHRITT 3 - Kalender-Dienst aktivieren
 *    a) Links in der Seitenleiste bei "Services" auf das "+"
 *    b) "Google Calendar API" auswaehlen, dann "Add"
 *    c) Danach muss links unter "Services" der Eintrag "Calendar" stehen.
 *
 *    Falls das "+" nicht reagiert, geht es auch ueber die Manifest-Datei:
 *      - Zahnrad "Project Settings" -> Haken bei
 *        "Show appsscript.json manifest file in editor"
 *      - Zurueck zum Editor, Datei "appsscript.json" oeffnen, Inhalt ersetzen
 *        durch den Block ganz unten in dieser Datei, speichern.
 *
 *  SCHRITT 4 - Zugangsdaten hinterlegen
 *    Zahnrad "Project Settings" -> runterscrollen zu "Script Properties" ->
 *    "Add script property". Diese fuenf Eintraege anlegen:
 *
 *      UNTIS_SERVER    Der Hostname aus der Browser-Adresszeile, wenn man in
 *                      WebUntis eingeloggt ist. Beispiel: nessa.webuntis.com
 *                      (nur der Teil zwischen https:// und /WebUntis)
 *
 *      UNTIS_SCHOOL    Der technische Schulname, NICHT der Anzeigename.
 *                      Steht in der URL hinter "?school=".
 *                      Zeigt die neue Oberflaeche ihn nicht an, einfach die
 *                      Funktion schuleSuchen() weiter unten benutzen.
 *
 *      UNTIS_USER      Der WebUntis-Benutzername
 *
 *      UNTIS_PASSWORD  Das WebUntis-Passwort
 *
 *      GCAL_ID         Die Kalender-ID aus Schritt 1
 *
 *    Danach unten auf "Save script properties".
 *
 *  SCHRITT 5 - Enddatum festlegen
 *    Weiter unten im Block EINSTELLUNGEN steht "endDatum". Bis zu diesem Tag
 *    werden Termine uebertragen, danach nicht mehr. Sinnvoll ist das Ende des
 *    Schulhalbjahres oder Schuljahres. Format: 'JJJJ-MM-TT'.
 *
 *  SCHRITT 6 - Pruefen
 *    a) Oben im Auswahlfeld neben "Run" die Funktion "einrichtungPruefen"
 *       waehlen, dann "Run".
 *    b) Google fragt nach Berechtigungen:
 *         "Review permissions" -> eigenes Konto -> es erscheint
 *         "Google hasn't verified this app" -> "Advanced" ->
 *         "Go to <Projektname> (unsafe)" -> alle Haken setzen ("Select all")
 *         -> "Continue"
 *       Das "unsafe" bedeutet nur, dass Google dieses private Skript nicht
 *       geprueft hat. Es ist der eigene Code.
 *    c) Unten im "Execution log" muss stehen:
 *         WebUntis-Anmeldung: OK, personId ...
 *         Kalender: "..." (...)
 *         Stundenplan: ... Stunden im Fenster ...
 *         Schreibrecht im Kalender: OK
 *         Einrichtung vollstaendig in Ordnung.
 *
 *  SCHRITT 7 - Probelauf
 *    Funktion "probelauf" waehlen, "Run". Es wird nichts geschrieben, man sieht
 *    nur, was passieren wuerde. Bei einem leeren Kalender steht dort die volle
 *    Anzahl unter "angelegt" - das ist richtig so.
 *
 *  SCHRITT 8 - Automatik einschalten
 *    Funktion "ausloeserEinrichten" waehlen, "Run".
 *    Ab jetzt laeuft es von allein.
 *
 * ----------------------------------------------------------------------------
 *  BEDIENUNG IM ALLTAG
 *
 *    sync                  einmal sofort synchronisieren
 *    probelauf             anzeigen, was passieren wuerde, ohne zu schreiben
 *    einrichtungPruefen    Zugangsdaten, Anmeldung und Schreibrecht testen
 *    schuleSuchen          den technischen Schulnamen herausfinden
 *    ausloeserEinrichten   Automatik einschalten
 *    ausloeserEntfernen    Automatik ausschalten
 *    waechter              prueft, ob Stunden fehlen, und warnt per Mail
 *    reparieren            holt fehlende Stunden zurueck (Notfall)
 *    alleEntfernen         Notausstieg: alle vom Skript angelegten Termine weg
 *
 *  Laufprotokolle: links in der schmalen Leiste auf "Executions".
 *
 * ----------------------------------------------------------------------------
 *  GOOGLE-KONTINGENT
 *
 *  Kostenlose Google-Konten duerfen Skripte insgesamt 90 Minuten pro Tag ueber
 *  Zeitausloeser laufen lassen. Diese Einstellung (rund um die Uhr, alle zwei
 *  Minuten) verbraucht erfahrungsgemaess etwa 35 bis 40 Minuten pro Tag.
 *
 *  Falls doch eine Kontingentmeldung kommt: unten "mindestAbstandSekunden" von
 *  120 auf 300 stellen. Dann sind es noch etwa 15 Minuten pro Tag.
 *
 * ----------------------------------------------------------------------------
 *  WENN ETWAS NICHT KLAPPT
 *
 *    "Diese Skript-Eigenschaften fehlen: ..."
 *        Schritt 4 unvollstaendig. Die Namen muessen exakt stimmen,
 *        Grossschreibung inklusive.
 *
 *    "WebUntis-Anmeldung abgelehnt"
 *        Benutzername, Passwort oder Schulname falsch. Schulnamen mit
 *        schuleSuchen() pruefen.
 *
 *    "Calendar is not defined"
 *        Schritt 3 fehlt - die Google Calendar API ist nicht als Dienst
 *        hinzugefuegt.
 *
 *    "Not Found" beim Kalender
 *        GCAL_ID stimmt nicht. Es muss die lange Adresse auf
 *        @group.calendar.google.com sein, nicht der Anzeigename.
 *
 *    "startDate and endDate are not within a single school year"
 *        Das Enddatum liegt im naechsten Schuljahr. WebUntis erlaubt keine
 *        Abfrage ueber eine Schuljahresgrenze hinweg. Enddatum vorziehen.
 *
 *    Termine doppelt
 *        Sofort "ausloeserEntfernen" ausfuehren, dann "alleEntfernen",
 *        danach neu starten.
 *
 * ----------------------------------------------------------------------------
 *  INHALT DER DATEI appsscript.json  (nur noetig, wenn Schritt 3 ueber das
 *  Manifest gemacht wird)
 *
 *  {
 *    "timeZone": "Europe/Berlin",
 *    "runtimeVersion": "V8",
 *    "exceptionLogging": "STACKDRIVER",
 *    "dependencies": {
 *      "enabledAdvancedServices": [
 *        { "userSymbol": "Calendar", "serviceId": "calendar", "version": "v3" }
 *      ]
 *    },
 *    "oauthScopes": [
 *      "https://www.googleapis.com/auth/calendar",
 *      "https://www.googleapis.com/auth/script.external_request",
 *      "https://www.googleapis.com/auth/script.scriptapp"
 *    ]
 *  }
 *
 * ----------------------------------------------------------------------------
 *  HINWEIS ZUR SCHNITTSTELLE
 *
 *  WebUntis hat keine oeffentliche, dokumentierte Schnittstelle fuer Schueler.
 *  Dieses Skript benutzt dieselbe interne Schnittstelle wie die WebUntis-
 *  Weboberflaeche. Die kann sich ohne Ankuendigung aendern. Typisches Zeichen
 *  dafuer: ploetzlich HTTP 403 oder 404 im Protokoll.
 * ============================================================================
 */

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------

var EINSTELLUNGEN = {
  // Letzter Tag, der ueberhaupt in den Kalender kommt (einschliesslich).
  // Termine dahinter werden nicht angelegt und bereits angelegte entfernt.
  endDatum: '2027-03-16',

  // Die naechsten so vielen Tage werden bei JEDEM Lauf geprueft. Hier passieren
  // die kurzfristigen Aenderungen (Ausfall, Vertretung, Raumwechsel).
  nahTage: 14,

  // Das gesamte Fenster bis zum Enddatum wird nur so oft geprueft. Das haelt
  // die taegliche Laufzeit klein, erkennt aber auch Aenderungen weit im Voraus.
  fernIntervallMinuten: 30,

  // Hoechstzahl an Schreibvorgaengen je Lauf. Apps Script bricht nach sechs
  // Minuten ab; der Rest wird beim naechsten Lauf nachgeholt.
  maxSchreibvorgaengeProLauf: 100,

  // --- Schutz vor Datenverlust ---------------------------------------------
  // Liefert WebUntis deutlich weniger Stunden als im Kalender stehen, ist das
  // fast immer eine Stoerung und keine echte Planaenderung. Unterhalb dieses
  // Anteils wird NICHTS geloescht. 0.7 heisst: mindestens 70 Prozent erwartet.
  mindestAnteilFuerLoeschen: 0.7,

  // Erst ab so vielen vorhandenen Terminen greift diese Pruefung. Bei wenigen
  // Terminen sind grosse Schwankungen normal.
  loeschschutzAbAnzahl: 5,

  // Adresse fuer Warnmeldungen; leer lassen, um keine Mails zu bekommen.
  warnEmail: '',

  // Zeitfenster, in dem ueberhaupt synchronisiert wird. Standard ist rund um
  // die Uhr an allen Tagen – genau dafuer gibt es diese Fassung. Wer Laufzeit
  // sparen will, kann hier einschraenken, z. B. vonStunde 6 und bisStunde 19.
  vonStunde: 0,          // Berliner Zeit
  bisStunde: 24,
  nurWerktags: false,

  // Mindestabstand zwischen zwei echten Syncs, in Sekunden. Der Ausloeser
  // feuert jede Minute; hierueber laesst sich der Takt gezielt strecken.
  // Bei 120 Sekunden rund um die Uhr liegt die taegliche Laufzeit bei etwa
  // 50 der 90 erlaubten Minuten. Auf 60 zu gehen waere zu knapp.
  mindestAbstandSekunden: 120,

  // Abstand des Zeitausloesers in Minuten. Erlaubt sind 1, 5, 10, 15 und 30.
  // Der eigentliche Takt wird ueber mindestAbstandSekunden gesteuert; der
  // Ausloeser darf ruhig jede Minute feuern und sofort wieder aussteigen.
  ausloeserMinuten: 1,

  zeitzone: 'Europe/Berlin',
  markierung: 'untis-sync',

  farbeAusgefallen: '8',   // Graphit
  farbeAenderung: '6',     // Tangerine
  farbePruefung: '11'      // Tomato
};

// ---------------------------------------------------------------------------
// Einstiegspunkte
// ---------------------------------------------------------------------------

/** Wird vom Zeitausloeser aufgerufen. */
function sync() {
  ausfuehren(false);
}

/** Probelauf: schreibt nichts, protokolliert nur. Von Hand im Editor starten. */
function probelauf() {
  ausfuehren(true);
}

/** Notausstieg: entfernt alle vom Skript verwalteten Termine im Fenster. */
function alleEntfernen() {
  var k = konfiguration();
  var start = new Date();
  var ende = new Date(start.getTime());
  ende.setDate(ende.getDate() + 500);
  var vorhanden = holeVerwaltete(k.kalenderId, start, ende, false);
  var anzahl = 0;
  Object.keys(vorhanden).forEach(function (id) {
    if (istUnser(vorhanden[id])) {
      Calendar.Events.remove(k.kalenderId, id);
      anzahl++;
    }
  });
  Logger.log('Notausstieg: ' + anzahl + ' Termine entfernt. Fremde Termine blieben unberuehrt.');
}

/** Einmalig im Editor ausfuehren: legt den Zeitausloeser an (jede Minute). */
function ausloeserEinrichten() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var name = t.getHandlerFunction();
    if (name === 'sync' || name === 'waechter') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('sync').timeBased()
    .everyMinutes(EINSTELLUNGEN.ausloeserMinuten).create();
  // Der Waechter prueft einmal am Abend, ob im Kalender Stunden fehlen, und
  // schickt notfalls eine Mail. Abends, damit man es vor dem naechsten
  // Schultag noch mitbekommt.
  ScriptApp.newTrigger('waechter').timeBased().atHour(20).everyDays(1).create();
  Logger.log('Ausloeser angelegt: sync() laeuft alle ' +
             EINSTELLUNGEN.ausloeserMinuten + ' Minute(n), ' +
             'waechter() einmal taeglich gegen 20 Uhr.');
}

/**
 * WAECHTER. Vergleicht WebUntis mit dem Kalender und schlaegt Alarm, wenn an
 * einem Schultag der naechsten zwei Wochen Stunden fehlen.
 *
 * Das ist die letzte Sicherung: Selbst wenn im Abgleich etwas schiefgeht,
 * faellt es hierdurch auf, statt dass man morgens vor einem leeren Kalender
 * steht. Laeuft ueber einen eigenen Ausloeser, siehe ausloeserEinrichten().
 */
function waechter() {
  var k = konfiguration();
  var heute = new Date();
  var bis = new Date(heute.getTime());
  bis.setDate(bis.getDate() + 14);
  var schluss = endDatumAlsDatum();
  if (bis > schluss) bis = schluss;
  if (bis < heute) return;          // hinter dem Enddatum gibt es nichts zu pruefen

  var sitzung = anmelden(k);
  var stunden = holeStunden(k, sitzung, heute, bis);
  if (!stunden.length) return;      // echte Ferien – kein Alarm

  var vorhanden = holeVerwaltete(k.kalenderId, heute, bis, false);

  // Nach Tagen gruppieren und vergleichen
  var sollProTag = {}, fehlendProTag = {};
  stunden.forEach(function (s) {
    var tag = s.startText.slice(0, 10);
    sollProTag[tag] = (sollProTag[tag] || 0) + 1;
    if (!vorhanden[eventId(s)]) {
      fehlendProTag[tag] = (fehlendProTag[tag] || 0) + 1;
    }
  });

  var betroffen = Object.keys(fehlendProTag).sort();
  if (!betroffen.length) {
    Logger.log('Waechter: alles vollstaendig (' + stunden.length + ' Stunden geprueft).');
    return;
  }

  var zeilen = betroffen.map(function (tag) {
    return '  ' + tag + ': ' + fehlendProTag[tag] + ' von ' + sollProTag[tag] +
           ' Stunden fehlen';
  });
  var fehlenGesamt = betroffen.reduce(function (summe, tag) {
    return summe + fehlendProTag[tag];
  }, 0);

  Logger.log('Waechter: ' + fehlenGesamt + ' Stunden fehlen.\n' + zeilen.join('\n'));
  warnen('Stundenplan-Sync: ' + fehlenGesamt + ' Stunden fehlen im Kalender',
         'Der Waechter hat einen Unterschied zwischen WebUntis und dem ' +
         'Google-Kalender gefunden:\n\n' + zeilen.join('\n') +
         '\n\nMeist behebt sich das beim naechsten Sync von selbst. Bleibt es ' +
         'bestehen, im Apps-Script-Editor einmal die Funktion "reparieren" ' +
         'ausfuehren.');
}

/**
 * NOTFALL-REPARATUR. Hebt alle Loeschsperren im Sync-Fenster auf und legt
 * jede Stunde neu an, die WebUntis kennt.
 *
 * Achtung: Damit kommen auch Termine zurueck, die absichtlich von Hand
 * geloescht wurden. Nur benutzen, wenn wirklich Stunden fehlen.
 */
function reparieren() {
  var k = konfiguration();
  var fenster = syncFenster(true);
  if (!fenster) {
    Logger.log('Das Enddatum liegt in der Vergangenheit – nichts zu reparieren.');
    return;
  }

  var sitzung = anmelden(k);
  var stunden = holeStunden(k, sitzung, fenster.start, fenster.ende);
  if (!stunden.length) {
    Logger.log('WebUntis lieferte keine Stunden – Reparatur abgebrochen, ' +
               'damit nichts kaputtgeht. Spaeter noch einmal versuchen.');
    return;
  }

  var vorhanden = holeVerwaltete(k.kalenderId, fenster.start, fenster.ende, false);
  var wiederhergestellt = 0;

  stunden.forEach(function (s) {
    var id = eventId(s);
    if (vorhanden[id]) return;              // ist schon da
    var termin = baueTermin(s);
    termin.status = 'confirmed';            // hebt einen Grabstein auf
    try {
      Calendar.Events.update(termin, k.kalenderId, id);
      selbstGeloeschtVergessen(id);
      wiederhergestellt++;
    } catch (fehler) {
      try {
        Calendar.Events.insert(termin, k.kalenderId);
        wiederhergestellt++;
      } catch (zweiter) {
        Logger.log('Konnte ' + titel(s) + ' nicht wiederherstellen: ' + zweiter);
      }
    }
  });

  // Loeschsperren zuruecksetzen, damit nichts Altes nachwirkt.
  PropertiesService.getScriptProperties().deleteProperty('selbstGeloescht');
  Logger.log('Reparatur fertig: ' + wiederhergestellt + ' Termine wiederhergestellt. ' +
             'WebUntis kennt ' + stunden.length + ' Stunden im Fenster.');
}

/** Entfernt den Zeitausloeser wieder. */
function ausloeserEntfernen() {
  var anzahl = 0;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var name = t.getHandlerFunction();
    if (name === 'sync' || name === 'waechter') {
      ScriptApp.deleteTrigger(t);
      anzahl++;
    }
  });
  Logger.log(anzahl + ' Ausloeser entfernt.');
}

/** Prueft die Einrichtung: Zugangsdaten, WebUntis-Anmeldung, Kalenderzugriff. */
function einrichtungPruefen() {
  var k = konfiguration();
  Logger.log('Server: ' + k.server + ' | Schule: ' + k.schule + ' | Benutzer: ' + k.benutzer);

  var sitzung = anmelden(k);
  Logger.log('WebUntis-Anmeldung: OK, personId ' + sitzung.personId);

  var kal = Calendar.Calendars.get(k.kalenderId);
  Logger.log('Kalender: "' + kal.summary + '" (' + kal.timeZone + ')');

  var fenster = syncFenster(true);
  if (!fenster) {
    Logger.log('Achtung: Das Enddatum ' + EINSTELLUNGEN.endDatum +
               ' liegt bereits in der Vergangenheit – es wird nichts mehr uebertragen.');
  } else {
    var stunden = holeStunden(k, sitzung, fenster.start, fenster.ende);
    Logger.log('Stundenplan: ' + stunden.length + ' Stunden im Fenster ' +
               datumIso(fenster.start) + ' bis ' + datumIso(fenster.ende));
  }

  // Schreibrecht pruefen: Testtermin anlegen und sofort wieder entfernen.
  var testId = 'untis' + '0123456789abcdef0123456789abcdef01234567';
  var jetzt = new Date();
  var gleich = new Date(jetzt.getTime() + 10 * 60 * 1000);
  var test = {
    id: testId,
    summary: 'TEST – wird sofort geloescht',
    start: { dateTime: Utilities.formatDate(jetzt, EINSTELLUNGEN.zeitzone,
             "yyyy-MM-dd'T'HH:mm:ssXXX"), timeZone: EINSTELLUNGEN.zeitzone },
    end: { dateTime: Utilities.formatDate(gleich, EINSTELLUNGEN.zeitzone,
           "yyyy-MM-dd'T'HH:mm:ssXXX"), timeZone: EINSTELLUNGEN.zeitzone },
    extendedProperties: { private: { managedBy: EINSTELLUNGEN.markierung,
                                     contentHash: 'test' } }
  };
  einfuegen(k.kalenderId, test);
  Calendar.Events.remove(k.kalenderId, testId);
  Logger.log('Schreibrecht im Kalender: OK');

  Logger.log('Einrichtung vollstaendig in Ordnung.');
}

// ---------------------------------------------------------------------------
// Hauptablauf
// ---------------------------------------------------------------------------

function ausfuehren(nurVorschau) {
  var beginn = new Date();

  if (!nurVorschau && !istSchulzeit(beginn)) {
    return;   // ausserhalb des Aktivfensters: sofort raus, kostet kaum Laufzeit
  }
  if (!nurVorschau && !abstandEingehalten(beginn)) {
    return;   // Mindestabstand noch nicht erreicht
  }

  var sperre = LockService.getScriptLock();
  if (!sperre.tryLock(5000)) {
    return;   // ein anderer Lauf ist noch aktiv
  }

  try {
    var eigenschaften = PropertiesService.getScriptProperties();
    var k = konfiguration();

    // Das grosse Fenster nur gelegentlich pruefen, das nahe bei jedem Lauf.
    var fernFaellig = nurVorschau || fernLaufFaellig(beginn, eigenschaften);
    var fenster = syncFenster(fernFaellig);

    if (!fenster) {
      // Das Enddatum liegt hinter uns – es gibt nichts mehr zu uebertragen.
      var weg = raeumeHinterEnddatumAuf(k.kalenderId, nurVorschau);
      if (weg) Logger.log(weg + ' Termine hinter dem Enddatum entfernt.');
      return;
    }

    var sitzung = anmelden(k);
    var stunden = holeStunden(k, sitzung, fenster.start, fenster.ende);

    var geplant = {};
    stunden.forEach(function (s) {
      var termin = baueTermin(s);
      if (!geplant[termin.id]) geplant[termin.id] = termin;
    });

    var vorhanden = holeVerwaltete(k.kalenderId, fenster.start, fenster.ende, false);
    var geloescht = holeGeloeschte(k.kalenderId, fenster.start, fenster.ende);

    // SCHUTZ 1: Liefert WebUntis auffaellig wenig, ist das fast immer eine
    // Stoerung. Dann wird nichts geloescht – lieber ein veralteter Termin zu
    // viel als ein fehlender Schultag.
    var pruefung = loeschenErlaubt(Object.keys(geplant).length,
                                   Object.keys(vorhanden).length);
    if (!pruefung.erlaubt) {
      Logger.log('LOESCHSCHUTZ: ' + pruefung.grund +
                 ' – es wird nichts entfernt, nur ergaenzt.');
      warnen('Stundenplan-Sync: Loeschschutz hat angeschlagen',
             pruefung.grund + '\n\nEs wurde nichts geloescht. Der Sync ergaenzt ' +
             'weiterhin fehlende Termine. Meist ist das eine kurze Stoerung bei ' +
             'WebUntis und erledigt sich von selbst.\n\nFenster: ' +
             datumIso(fenster.start) + ' bis ' + datumIso(fenster.ende));
    }

    var angelegt = 0, aktualisiert = 0, unveraendert = 0, entfernt = 0;
    var uebersprungen = 0, offen = 0;
    var budget = EINSTELLUNGEN.maxSchreibvorgaengeProLauf;

    Object.keys(geplant).forEach(function (id) {
      if (geloescht[id]) { uebersprungen++; return; }
      var neu = geplant[id];
      var alt = vorhanden[id];
      var neuerHash = neu.extendedProperties.private.contentHash;

      if (alt && hashVon(alt) === neuerHash) { unveraendert++; return; }

      if (budget <= 0) { offen++; return; }
      budget--;

      if (!alt) {
        if (!nurVorschau) {
          einfuegen(k.kalenderId, neu);
          // Der Termin ist wieder da – aus der Liste der selbst geloeschten raus.
          selbstGeloeschtVergessen(id);
        }
        angelegt++;
      } else {
        if (!nurVorschau) Calendar.Events.update(neu, k.kalenderId, id);
        aktualisiert++;
      }
    });

    Object.keys(vorhanden).forEach(function (id) {
      if (geplant[id]) return;
      if (!pruefung.erlaubt) return;          // SCHUTZ 1 greift
      if (!istUnser(vorhanden[id])) {
        Logger.log('Termin ' + id + ' wird NICHT entfernt – ohne Markierung.');
        return;
      }
      if (budget <= 0) { offen++; return; }
      budget--;
      if (!nurVorschau) {
        // SCHUTZ 2: Eigene Loeschungen merken. Sonst waere der Grabstein
        // spaeter nicht von einer Loeschung durch den Nutzer zu unterscheiden
        // und der Termin koennte nie wieder angelegt werden.
        selbstGeloeschtMerken(id);
        Calendar.Events.remove(k.kalenderId, id);
      }
      entfernt++;
    });

    // Beim grossen Durchgang zusaetzlich hinter dem Enddatum aufraeumen.
    if (fernFaellig) {
      entfernt += raeumeHinterEnddatumAuf(k.kalenderId, nurVorschau);
    }

    var dauer = ((new Date()) - beginn) / 1000;
    var text = (nurVorschau ? 'PROBELAUF – ' : '') +
               (fernFaellig ? 'ganzes Fenster' : 'naechste ' + EINSTELLUNGEN.nahTage + ' Tage') +
               ' bis ' + datumIso(fenster.ende) + ': ' +
               angelegt + ' angelegt, ' + aktualisiert + ' aktualisiert, ' +
               entfernt + ' geloescht, ' + unveraendert + ' unveraendert' +
               (uebersprungen ? ', ' + uebersprungen + ' bleiben geloescht' : '') +
               (offen ? ', ' + offen + ' auf den naechsten Lauf verschoben' : '') +
               ' (' + dauer.toFixed(1) + ' s)';

    // Nur protokollieren, wenn sich etwas getan hat – sonst laeuft das Protokoll voll.
    if (nurVorschau || angelegt || aktualisiert || entfernt || offen) {
      Logger.log(text);
      console.log(text);
    }

    if (!nurVorschau) {
      eigenschaften.setProperty('letzterLauf', String(beginn.getTime()));
      // Der grosse Durchgang gilt erst als erledigt, wenn nichts offen blieb.
      if (fernFaellig && !offen) {
        eigenschaften.setProperty('letzterFernLauf', String(beginn.getTime()));
      }
    }
  } finally {
    sperre.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// Schutz vor Datenverlust
// ---------------------------------------------------------------------------

/**
 * Darf ueberhaupt geloescht werden?
 *
 * Hintergrund: Liefert WebUntis einmal eine leere oder unvollstaendige Antwort,
 * sieht das fuer den Abgleich aus wie "diese Stunden gibt es nicht mehr". Ohne
 * diese Bremse wuerde der Sync dann ganze Schultage loeschen. Genau das ist
 * einmal passiert und hat zwoelf Schultage gekostet.
 */
function loeschenErlaubt(anzahlGeplant, anzahlVorhanden) {
  if (anzahlVorhanden === 0) {
    return { erlaubt: true, grund: '' };
  }
  if (anzahlGeplant === 0) {
    return { erlaubt: false,
             grund: 'WebUntis lieferte keine einzige Stunde, im Kalender stehen ' +
                    anzahlVorhanden + '.' };
  }
  if (anzahlVorhanden >= EINSTELLUNGEN.loeschschutzAbAnzahl) {
    var anteil = anzahlGeplant / anzahlVorhanden;
    if (anteil < EINSTELLUNGEN.mindestAnteilFuerLoeschen) {
      return { erlaubt: false,
               grund: 'WebUntis lieferte nur ' + anzahlGeplant + ' Stunden, im ' +
                      'Kalender stehen ' + anzahlVorhanden + ' (' +
                      Math.round(anteil * 100) + ' Prozent).' };
    }
  }
  return { erlaubt: true, grund: '' };
}

/**
 * Kennungen, die der Sync SELBST geloescht hat.
 *
 * Google unterscheidet nicht, wer einen Termin geloescht hat – ein Grabstein
 * sieht immer gleich aus. Ohne diese Liste koennte ein vom Sync geloeschter
 * Termin nie wieder angelegt werden, weil er als "vom Nutzer geloescht" gilt.
 */
function ladeSelbstGeloescht() {
  var roh = PropertiesService.getScriptProperties().getProperty('selbstGeloescht');
  if (!roh) return {};
  try {
    return JSON.parse(roh) || {};
  } catch (fehler) {
    return {};
  }
}

function selbstGeloeschtMerken(id) {
  var liste = ladeSelbstGeloescht();
  liste[id] = Date.now();
  // Nicht unbegrenzt wachsen lassen: nur die 400 juengsten behalten.
  var kennungen = Object.keys(liste);
  if (kennungen.length > 400) {
    kennungen.sort(function (a, b) { return liste[b] - liste[a]; });
    var neu = {};
    kennungen.slice(0, 400).forEach(function (k) { neu[k] = liste[k]; });
    liste = neu;
  }
  PropertiesService.getScriptProperties()
    .setProperty('selbstGeloescht', JSON.stringify(liste));
}

function selbstGeloeschtVergessen(id) {
  var liste = ladeSelbstGeloescht();
  if (!(id in liste)) return;
  delete liste[id];
  PropertiesService.getScriptProperties()
    .setProperty('selbstGeloescht', JSON.stringify(liste));
}

/** Schickt eine Warnmail, wenn eine Adresse hinterlegt ist. */
function warnen(betreff, text) {
  var adresse = EINSTELLUNGEN.warnEmail;
  if (!adresse) {
    try {
      adresse = Session.getEffectiveUser().getEmail();
    } catch (fehler) {
      return;
    }
  }
  if (!adresse) return;

  // Hoechstens eine Mail pro Stunde und Betreff, damit das Postfach nicht
  // volllaeuft, wenn eine Stoerung laenger anhaelt.
  var schluessel = 'warnung_' + betreff.replace(/[^a-zA-Z]/g, '').slice(0, 40);
  var eigenschaften = PropertiesService.getScriptProperties();
  var letzte = Number(eigenschaften.getProperty(schluessel) || 0);
  if (Date.now() - letzte < 60 * 60 * 1000) return;

  try {
    MailApp.sendEmail(adresse, betreff, text);
    eigenschaften.setProperty(schluessel, String(Date.now()));
  } catch (fehler) {
    Logger.log('Warnmail konnte nicht gesendet werden: ' + fehler);
  }
}

/** Entfernt verwaltete Termine, die hinter dem Enddatum liegen. */
function raeumeHinterEnddatumAuf(kalenderId, nurVorschau) {
  var ab = new Date(endDatumAlsDatum().getTime());
  ab.setDate(ab.getDate() + 1);
  var bis = new Date(ab.getTime());
  bis.setDate(bis.getDate() + 400);

  var verwaiste = holeVerwaltete(kalenderId, ab, bis, false);
  var anzahl = 0;
  Object.keys(verwaiste).forEach(function (id) {
    if (!istUnser(verwaiste[id])) return;
    if (!nurVorschau) Calendar.Events.remove(kalenderId, id);
    anzahl++;
  });
  return anzahl;
}

// ---------------------------------------------------------------------------
// Konfiguration und Zeitfenster
// ---------------------------------------------------------------------------

function konfiguration() {
  var p = PropertiesService.getScriptProperties();
  var noetig = ['UNTIS_SERVER', 'UNTIS_SCHOOL', 'UNTIS_USER', 'UNTIS_PASSWORD', 'GCAL_ID'];
  var fehlend = noetig.filter(function (n) { return !p.getProperty(n); });
  if (fehlend.length) {
    throw new Error('Diese Skript-Eigenschaften fehlen: ' + fehlend.join(', ') +
                    ' (Projekteinstellungen -> Skripteigenschaften)');
  }
  return {
    server: p.getProperty('UNTIS_SERVER'),
    schule: p.getProperty('UNTIS_SCHOOL'),
    benutzer: p.getProperty('UNTIS_USER'),
    passwort: p.getProperty('UNTIS_PASSWORD'),
    kalenderId: p.getProperty('GCAL_ID')
  };
}

/** Das Enddatum aus den Einstellungen als Date-Objekt. */
function endDatumAlsDatum() {
  var teile = EINSTELLUNGEN.endDatum.split('-');
  return new Date(Number(teile[0]), Number(teile[1]) - 1, Number(teile[2]));
}

/**
 * Liefert das Abfragefenster, oder null, wenn das Enddatum bereits vorbei ist.
 * Beim grossen Durchgang reicht es bis zum Enddatum, sonst nur nahTage weit.
 */
function syncFenster(ganzesFenster) {
  var heute = new Date();
  var schluss = endDatumAlsDatum();

  // Auf Tagesgrenzen normieren, damit der Vergleich nicht an der Uhrzeit haengt.
  var heuteTag = new Date(heute.getFullYear(), heute.getMonth(), heute.getDate());
  if (schluss < heuteTag) return null;

  var ende = schluss;
  if (!ganzesFenster) {
    var nah = new Date(heuteTag.getTime());
    nah.setDate(nah.getDate() + EINSTELLUNGEN.nahTage);
    ende = (nah < schluss) ? nah : schluss;
  }
  return { start: heute, ende: ende };
}

/** Ist der grosse Durchgang ueber das ganze Fenster wieder faellig? */
function fernLaufFaellig(jetzt, eigenschaften) {
  var letzter = eigenschaften.getProperty('letzterFernLauf');
  if (!letzter) return true;
  return (jetzt.getTime() - Number(letzter)) >=
         EINSTELLUNGEN.fernIntervallMinuten * 60 * 1000;
}

/** Liegt der Zeitpunkt im eingestellten Aktivfenster? */
function istSchulzeit(jetzt) {
  var stunde = Number(Utilities.formatDate(jetzt, EINSTELLUNGEN.zeitzone, 'H'));
  var wochentag = Utilities.formatDate(jetzt, EINSTELLUNGEN.zeitzone, 'u'); // 1=Mo … 7=So
  if (EINSTELLUNGEN.nurWerktags && Number(wochentag) > 5) return false;
  return stunde >= EINSTELLUNGEN.vonStunde && stunde < EINSTELLUNGEN.bisStunde;
}

function abstandEingehalten(jetzt) {
  var letzter = PropertiesService.getScriptProperties().getProperty('letzterLauf');
  if (!letzter) return true;
  return (jetzt.getTime() - Number(letzter)) >= EINSTELLUNGEN.mindestAbstandSekunden * 1000;
}

// ---------------------------------------------------------------------------
// WebUntis
// ---------------------------------------------------------------------------

function anmelden(k) {
  var basis = 'https://' + k.server;

  var antwort = UrlFetchApp.fetch(basis + '/WebUntis/j_spring_security_check', {
    method: 'post',
    payload: { school: k.schule, j_username: k.benutzer, j_password: k.passwort, token: '' },
    followRedirects: false,
    muteHttpExceptions: true
  });

  var kekse = keksZeileBauen(antwort);
  if (kekse.indexOf('JSESSIONID') === -1) {
    throw new Error('WebUntis-Anmeldung abgelehnt (HTTP ' + antwort.getResponseCode() +
                    '). Benutzername, Passwort oder Schulname pruefen.');
  }

  var tokenAntwort = UrlFetchApp.fetch(basis + '/WebUntis/api/token/new', {
    headers: { Cookie: kekse },
    muteHttpExceptions: true
  });
  var jwt = tokenAntwort.getContentText().trim();
  if (tokenAntwort.getResponseCode() !== 200 || jwt.indexOf('ey') !== 0) {
    throw new Error('Kein gueltiges Zugriffstoken (HTTP ' + tokenAntwort.getResponseCode() + ').');
  }

  var sitzung = { basis: basis, kekse: kekse, jwt: jwt, personId: null };

  var cfg = holeJson(sitzung, '/WebUntis/api/app/config', 'Konfiguration lesen');
  var nutzer = ((cfg.data || {}).loginServiceConfig || {}).user || {};
  sitzung.personId = nutzer.personId;
  if (!sitzung.personId) throw new Error('personId konnte nicht ermittelt werden.');

  return sitzung;
}

function holeJson(sitzung, pfad, beschreibung) {
  var letzterFehler = null;
  for (var versuch = 1; versuch <= 3; versuch++) {
    try {
      var antwort = UrlFetchApp.fetch(sitzung.basis + pfad, {
        headers: {
          Cookie: sitzung.kekse,
          Authorization: 'Bearer ' + sitzung.jwt,
          Accept: 'application/json'
        },
        muteHttpExceptions: true
      });
      if (antwort.getResponseCode() !== 200) {
        throw new Error(beschreibung + ': HTTP ' + antwort.getResponseCode());
      }
      return JSON.parse(antwort.getContentText());
    } catch (fehler) {
      letzterFehler = fehler;
      if (versuch < 3) Utilities.sleep(Math.pow(2, versuch) * 1000);
    }
  }
  throw new Error(beschreibung + ' nach 3 Versuchen fehlgeschlagen: ' + letzterFehler);
}

/** Setzt aus den Set-Cookie-Kopfzeilen eine Cookie-Zeile zusammen. */
function keksZeileBauen(antwort) {
  var kopf = antwort.getAllHeaders()['Set-Cookie'] || antwort.getAllHeaders()['set-cookie'] || [];
  if (typeof kopf === 'string') kopf = [kopf];
  return kopf.map(function (z) { return String(z).split(';')[0]; }).join('; ');
}

function holeStunden(k, sitzung, start, ende) {
  var pfad = '/WebUntis/api/rest/view/v1/timetable/entries' +
             '?start=' + datumIso(start) + '&end=' + datumIso(ende) +
             '&format=2&resourceType=STUDENT&resources=' + sitzung.personId +
             '&periodTypes=&timetableType=MY_TIMETABLE';
  var daten = holeJson(sitzung, pfad, 'Stundenplan abrufen');
  var pruefungen = holePruefungen(sitzung, start, ende);

  var stunden = [];
  (daten.days || []).forEach(function (tag) {
    (tag.gridEntries || []).forEach(function (eintrag) {
      var stunde = baueStunde(eintrag);
      if (!stunde) return;
      stunde.pruefung = passendePruefung(stunde, pruefungen);
      stunden.push(stunde);
    });
  });
  return stunden;
}

function holePruefungen(sitzung, start, ende) {
  var pfad = '/WebUntis/api/exams?startDate=' + datumKompakt(start) +
             '&endDate=' + datumKompakt(ende);
  try {
    var daten = holeJson(sitzung, pfad, 'Pruefungen abrufen');
    return ((daten.data || {}).exams || []).map(function (e) {
      return {
        art: e.examType || 'Pruefung',
        name: e.name || '',
        fach: e.subject || '',
        datum: String(e.examDate),
        start: Number(e.startTime || 0),
        ende: Number(e.endTime || 0),
        text: (e.text || '').trim()
      };
    });
  } catch (fehler) {
    Logger.log('Pruefungen nicht abrufbar: ' + fehler);
    return [];
  }
}

function baueStunde(e) {
  var dauer = e.duration || {};
  if (!dauer.start || !dauer.end) return null;

  var stunde = {
    ids: (e.ids || []).slice(),
    startText: dauer.start,               // z. B. "2026-08-24T08:00"
    endeText: dauer.end,
    ganztags: /T00:00$/.test(dauer.start) && /T23:59$/.test(dauer.end),
    fach: '', fachLang: '',
    lehrer: [], lehrerOriginal: [],
    raeume: [], raeumeOriginal: [],
    klassen: [], infos: [],
    status: e.status || 'REGULAR',
    vertretungstext: (e.substitutionText || '').trim(),
    klassenbuchtext: (e.lessonText || '').trim(),
    unterrichtsnotiz: (e.lessonInfo || '').trim(),
    notizen: (e.notesAll || '').trim(),
    pruefung: null
  };

  // position1..7 sind nicht typfest – nach dem 'type'-Feld verteilen.
  for (var n = 1; n <= 7; n++) {
    (e['position' + n] || []).forEach(function (element) {
      var aktuell = element.current, entfernt = element.removed;
      var art = (aktuell || entfernt || {}).type;
      var nameAktuell = nameVon(aktuell), nameEntfernt = nameVon(entfernt);

      if (art === 'TEACHER') {
        anhaengen(stunde.lehrer, nameAktuell);
        anhaengen(stunde.lehrerOriginal, nameEntfernt);
      } else if (art === 'ROOM') {
        anhaengen(stunde.raeume, nameAktuell);
        anhaengen(stunde.raeumeOriginal, nameEntfernt);
      } else if (art === 'CLASS') {
        anhaengen(stunde.klassen, nameAktuell || nameEntfernt);
      } else if (art === 'SUBJECT') {
        if (aktuell) {
          stunde.fach = stunde.fach || aktuell.shortName || '';
          stunde.fachLang = stunde.fachLang || aktuell.longName || '';
        } else if (entfernt && !stunde.fach) {
          stunde.fach = entfernt.shortName || '';
          stunde.fachLang = entfernt.longName || '';
        }
      } else if (art === 'INFO') {
        anhaengen(stunde.infos, nameAktuell || nameEntfernt);
      }
    });
  }

  // Zusatztexte; LESSON_INFO steckt bereits in unterrichtsnotiz
  (e.texts || []).forEach(function (t) {
    if (t.type === 'LESSON_INFO') return;
    var inhalt = (t.text || '').trim();
    if (!inhalt) return;
    if ([stunde.unterrichtsnotiz, stunde.klassenbuchtext,
         stunde.notizen, stunde.vertretungstext].indexOf(inhalt) !== -1) return;
    stunde.notizen = stunde.notizen ? (stunde.notizen + ' | ' + inhalt) : inhalt;
  });

  return stunde;
}

function passendePruefung(stunde, pruefungen) {
  var datum = stunde.startText.slice(0, 10).replace(/-/g, '');
  var beginn = Number(stunde.startText.slice(11, 13) + stunde.startText.slice(14, 16));
  var schluss = Number(stunde.endeText.slice(11, 13) + stunde.endeText.slice(14, 16));
  for (var i = 0; i < pruefungen.length; i++) {
    var p = pruefungen[i];
    if (p.datum !== datum) continue;
    if (!(beginn < p.ende && p.start < schluss)) continue;
    if (p.fach && stunde.fach && p.fach.toLowerCase() !== stunde.fach.toLowerCase()) continue;
    return p;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Termine bauen – Kennungen und Hash identisch zur Python-Fassung
// ---------------------------------------------------------------------------

function bezeichnung(s) {
  if (s.fach) return s.fach;
  if (s.infos.length) return s.infos.join(' / ');
  if (s.klassenbuchtext) return s.klassenbuchtext;
  return 'Termin';
}

function titel(s) {
  var teile = [bezeichnung(s)];
  if (s.lehrer.length) teile.push(s.lehrer.join(', '));
  if (s.raeume.length) teile.push(s.raeume.join(', '));
  var t = teile.join(' · ');       // Mittelpunkt
  return s.status === 'CANCELLED' ? 'FÄLLT AUS: ' + t : t;
}

function hatAenderung(s) {
  return s.status === 'CHANGED' || s.lehrerOriginal.length > 0 || s.raeumeOriginal.length > 0;
}

function pruefungsText(p) {
  if (!p) return '';
  var teile = [p.art];
  if (p.fach) teile.push(p.fach);
  if (p.name && p.name !== p.fach) teile.push(p.name);
  var zeile = teile.join(' ');
  return p.text ? (zeile + ': ' + p.text) : zeile;
}

function mitOriginal(aktuell, original) {
  var jetzt = aktuell.join(', '), vorher = original.join(', ');
  if (!aktuell.length && vorher) return 'entfällt (vorher: ' + vorher + ')';
  if (vorher && vorher !== jetzt) return jetzt + ' (statt: ' + vorher + ')';
  return jetzt;
}

function beschreibung(s) {
  var bloecke = [], kopf = [];

  if (s.fachLang && s.fachLang !== s.fach) kopf.push('Fach: ' + s.fachLang);
  if (s.lehrer.length || s.lehrerOriginal.length) {
    kopf.push('Lehrer: ' + mitOriginal(s.lehrer, s.lehrerOriginal));
  }
  if (s.raeume.length || s.raeumeOriginal.length) {
    kopf.push('Raum: ' + mitOriginal(s.raeume, s.raeumeOriginal));
  }
  if (s.klassen.length) kopf.push('Klasse: ' + s.klassen.join(', '));
  if (s.infos.length) kopf.push('Info: ' + s.infos.join(', '));
  // Bei Klausuren steht in lessonInfo "Klausur PH/711"; das wiederholt nur die
  // Klausurzeile weiter unten und wird deshalb weggelassen.
  if (s.unterrichtsnotiz && s.infos.indexOf(s.unterrichtsnotiz) === -1 &&
      s.unterrichtsnotiz.toLowerCase().indexOf('klausur') !== 0) {
    kopf.push('Kurs: ' + s.unterrichtsnotiz);
  }
  if (s.status === 'CANCELLED') kopf.unshift('Diese Stunde fällt aus.');
  if (kopf.length) bloecke.push(kopf.join('\n'));

  if (s.vertretungstext) bloecke.push('Vertretungstext: ' + s.vertretungstext);

  var notizen = [s.klassenbuchtext, s.notizen].filter(function (t) {
    return t && s.infos.indexOf(t) === -1 && t !== s.unterrichtsnotiz;
  });
  var gesehen = {};
  notizen = notizen.filter(function (t) {
    if (gesehen[t]) return false;
    gesehen[t] = true; return true;
  });
  if (notizen.length) bloecke.push('Notiz: ' + notizen.join(' | '));

  if (s.pruefung) bloecke.push('Klausur: ' + pruefungsText(s.pruefung));

  bloecke.push('Zuletzt aktualisiert: ' +
    Utilities.formatDate(new Date(), EINSTELLUNGEN.zeitzone, 'dd.MM.yyyy, HH:mm'));

  return bloecke.join('\n\n');
}

/** Zeitangabe wie Pythons datetime.isoformat(), z. B. "2026-08-24T08:00:00+02:00". */
function isoMitZone(text) {
  var d = new Date(text + ':00');   // wird als lokale Zeit des Skripts gelesen
  var versatz = Utilities.formatDate(d, EINSTELLUNGEN.zeitzone, 'XXX');
  return text + ':00' + versatz;
}

function schluesselVon(s) {
  var ids = s.ids.slice().sort(function (a, b) { return a - b; }).join('-');
  return ids + '-' + s.startText.slice(0, 10) + '-' +
         s.startText.slice(11, 13) + s.startText.slice(14, 16);
}

function eventId(s) {
  return 'untis' + sha1Hex(schluesselVon(s));
}

function inhaltsHash(s) {
  var teile = [
    isoMitZone(s.startText),
    isoMitZone(s.endeText),
    s.ganztags ? 'ganztags' : 'zeit',
    s.fach,
    s.fachLang,
    s.lehrer.join('|'),
    s.lehrerOriginal.join('|'),
    s.raeume.join('|'),
    s.raeumeOriginal.join('|'),
    s.klassen.join('|'),
    s.infos.join('|'),
    s.status,
    s.vertretungstext,
    s.klassenbuchtext,
    s.unterrichtsnotiz,
    s.notizen,
    '',                       // Hausaufgaben – Endpunkt liefert HTTP 500
    pruefungsText(s.pruefung)
  ];
  // Trennzeichen muss exakt dem der Python-Fassung entsprechen (Unit Separator),
  // sonst gelten alle vorhandenen Termine faelschlich als geaendert.
  return sha1Hex(teile.join('\x1f'));
}

function baueTermin(s) {
  var termin = {
    id: eventId(s),
    summary: titel(s),
    description: beschreibung(s),
    extendedProperties: {
      private: {
        managedBy: EINSTELLUNGEN.markierung,
        contentHash: inhaltsHash(s),
        untisSchluessel: schluesselVon(s)
      }
    }
  };

  if (s.raeume.length) termin.location = s.raeume.join(', ');

  if (s.ganztags) {
    var tag = s.startText.slice(0, 10);
    termin.start = { date: tag };
    termin.end = { date: naechsterTag(tag) };
  } else {
    termin.start = { dateTime: isoMitZone(s.startText), timeZone: EINSTELLUNGEN.zeitzone };
    termin.end = { dateTime: isoMitZone(s.endeText), timeZone: EINSTELLUNGEN.zeitzone };
  }

  if (s.status === 'CANCELLED') {
    termin.colorId = EINSTELLUNGEN.farbeAusgefallen;
    termin.transparency = 'transparent';
  } else if (s.pruefung) {
    termin.colorId = EINSTELLUNGEN.farbePruefung;
  } else if (hatAenderung(s)) {
    termin.colorId = EINSTELLUNGEN.farbeAenderung;
  }

  return termin;
}

// ---------------------------------------------------------------------------
// Google Kalender
// ---------------------------------------------------------------------------

function holeVerwaltete(kalenderId, start, ende, mitGeloeschten) {
  var gefunden = {}, seite = null;
  do {
    var antwort = Calendar.Events.list(kalenderId, {
      timeMin: tagesBeginnIso(start),
      timeMax: tagesBeginnIso(naechsterTagDatum(ende)),
      privateExtendedProperty: 'managedBy=' + EINSTELLUNGEN.markierung,
      singleEvents: true,
      showDeleted: !!mitGeloeschten,
      maxResults: 2500,
      pageToken: seite
    });
    (antwort.items || []).forEach(function (e) {
      if (mitGeloeschten || e.status !== 'cancelled') gefunden[e.id] = e;
    });
    seite = antwort.nextPageToken;
  } while (seite);
  return gefunden;
}

/**
 * Kennungen der Termine, die DER NUTZER von Hand geloescht hat.
 *
 * Google legt fuer jeden geloeschten Termin einen Grabstein mit
 * status 'cancelled' an – unabhaengig davon, wer geloescht hat. Termine, die
 * der Sync selbst entfernt hat, werden hier deshalb bewusst ausgenommen:
 * Taucht so eine Stunde in WebUntis wieder auf, soll sie auch wieder im
 * Kalender erscheinen. Nur eine Loeschung durch den Nutzer bleibt bestehen.
 */
function holeGeloeschte(kalenderId, start, ende) {
  var alle = holeVerwaltete(kalenderId, start, ende, true);
  var eigene = ladeSelbstGeloescht();
  var geloescht = {};
  Object.keys(alle).forEach(function (id) {
    if (alle[id].status !== 'cancelled') return;
    if (id in eigene) return;        // vom Sync geloescht – darf zurueckkommen
    geloescht[id] = true;
  });
  return geloescht;
}

function einfuegen(kalenderId, termin) {
  try {
    Calendar.Events.insert(termin, kalenderId);
  } catch (fehler) {
    // Ein Grabstein mit derselben Kennung blockiert das Einfuegen – dann aktualisieren.
    if (String(fehler).indexOf('duplicate') !== -1 ||
        String(fehler).indexOf('already exists') !== -1) {
      Calendar.Events.update(termin, kalenderId, termin.id);
    } else {
      throw fehler;
    }
  }
}

function istUnser(termin) {
  var p = ((termin.extendedProperties || {}).private) || {};
  return p.managedBy === EINSTELLUNGEN.markierung;
}

function hashVon(termin) {
  var p = ((termin.extendedProperties || {}).private) || {};
  return p.contentHash;
}

// ---------------------------------------------------------------------------
// Kleinkram
// ---------------------------------------------------------------------------

function sha1Hex(text) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_1, text, Utilities.Charset.UTF_8);
  return bytes.map(function (b) {
    return ('0' + (b & 0xFF).toString(16)).slice(-2);
  }).join('');
}

function nameVon(element) {
  if (!element) return null;
  return element.shortName || element.displayName || element.longName || null;
}

function anhaengen(liste, wert) {
  if (wert && liste.indexOf(wert) === -1) liste.push(wert);
}

function datumIso(d) {
  return Utilities.formatDate(d, EINSTELLUNGEN.zeitzone, 'yyyy-MM-dd');
}

function datumKompakt(d) {
  return Utilities.formatDate(d, EINSTELLUNGEN.zeitzone, 'yyyyMMdd');
}

function tagesBeginnIso(d) {
  return Utilities.formatDate(d, EINSTELLUNGEN.zeitzone, "yyyy-MM-dd'T'00:00:00XXX");
}

function naechsterTagDatum(d) {
  var n = new Date(d.getTime());
  n.setDate(n.getDate() + 1);
  return n;
}

function naechsterTag(tagText) {
  var teile = tagText.split('-');
  var d = new Date(Number(teile[0]), Number(teile[1]) - 1, Number(teile[2]));
  d.setDate(d.getDate() + 1);
  return Utilities.formatDate(d, EINSTELLUNGEN.zeitzone, 'yyyy-MM-dd');
}
/**
 * Findet den technischen Schulnamen (den Wert fuer UNTIS_SCHOOL).
 *
 * Den Suchbegriff unten eintragen, Funktion auswaehlen und "Run" druecken.
 * Im Execution log erscheinen Anzeigename, technischer Name und Server.
 */
function schuleSuchen() {
  var suchbegriff = 'Name oder Ort der Schule hier eintragen';

  var antwort = UrlFetchApp.fetch('https://mobile.webuntis.com/ms/schoolquery2', {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({
      id: 'suche', method: 'searchSchool',
      params: [{ search: suchbegriff }], jsonrpc: '2.0'
    }),
    muteHttpExceptions: true
  });

  var schulen = ((JSON.parse(antwort.getContentText()).result) || {}).schools || [];
  if (!schulen.length) {
    Logger.log('Kein Treffer fuer "' + suchbegriff + '". Anderen Begriff probieren, ' +
               'zum Beispiel nur den Ort oder einen Teil des Schulnamens.');
    return;
  }
  schulen.forEach(function (s) {
    Logger.log('Anzeigename : ' + s.displayName);
    Logger.log('UNTIS_SCHOOL: ' + s.loginName);
    Logger.log('UNTIS_SERVER: ' + s.server);
    Logger.log('Adresse     : ' + s.address);
    Logger.log('---');
  });
}
