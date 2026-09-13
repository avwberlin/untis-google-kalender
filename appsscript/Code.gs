/**
 * WebUntis -> Google Kalender, Fassung fuer Google Apps Script.
 *
 * Laeuft auf Googles Servern, rund um die Uhr, ohne dass ein Rechner an sein muss.
 *
 * Wichtig: Die Termin-Kennungen und der Inhalts-Hash sind identisch zur
 * Python-Fassung. Dadurch uebernimmt dieses Skript vorhandene Termine, statt
 * sie doppelt anzulegen.
 *
 * Einrichtung: siehe ANLEITUNG.md
 */

// ---------------------------------------------------------------------------
// Einstellungen
// ---------------------------------------------------------------------------

var EINSTELLUNGEN = {
  // Sync-Fenster: heute bis heute plus so viele Tage
  vorlaufTage: 28,

  // Nur waehrend der Schulzeit wirklich synchronisieren. Ausserhalb bricht das
  // Skript sofort ab und verbraucht praktisch keine Laufzeit. Das schont das
  // Apps-Script-Kontingent von 90 Minuten Ausfuehrungszeit pro Tag.
  vonStunde: 6,          // Berliner Zeit
  bisStunde: 19,
  nurWerktags: true,

  // Mindestabstand zwischen zwei echten Syncs, in Sekunden. Der Ausloeser
  // feuert jede Minute; hierueber laesst sich der Takt gezielt strecken.
  mindestAbstandSekunden: 60,

  // Abstand des Zeitausloesers in Minuten. Erlaubt sind 1, 5, 10, 15 und 30.
  // Bei 1 Minute liegt die taegliche Laufzeit bei etwa 60 der 90 erlaubten Minuten.
  // Falls Google wegen des Kontingents meckert: hier auf 5 stellen.
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
  var fenster = syncFenster();
  var vorhanden = holeVerwaltete(k.kalenderId, fenster.start, fenster.ende, false);
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
    if (t.getHandlerFunction() === 'sync') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('sync').timeBased()
    .everyMinutes(EINSTELLUNGEN.ausloeserMinuten).create();
  Logger.log('Ausloeser angelegt: sync() laeuft alle ' +
             EINSTELLUNGEN.ausloeserMinuten + ' Minute(n).');
}

/** Entfernt den Zeitausloeser wieder. */
function ausloeserEntfernen() {
  var anzahl = 0;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'sync') { ScriptApp.deleteTrigger(t); anzahl++; }
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

  var fenster = syncFenster();
  var stunden = holeStunden(k, sitzung, fenster.start, fenster.ende);
  Logger.log('Stundenplan: ' + stunden.length + ' Stunden im Fenster ' +
             datumIso(fenster.start) + ' bis ' + datumIso(fenster.ende));

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
    return;   // ausserhalb der Schulzeit: sofort raus, kostet kaum Laufzeit
  }
  if (!nurVorschau && !abstandEingehalten(beginn)) {
    return;   // Mindestabstand noch nicht erreicht
  }

  var sperre = LockService.getScriptLock();
  if (!sperre.tryLock(5000)) {
    return;   // ein anderer Lauf ist noch aktiv
  }

  try {
    var k = konfiguration();
    var fenster = syncFenster();
    var sitzung = anmelden(k);
    var stunden = holeStunden(k, sitzung, fenster.start, fenster.ende);

    if (!stunden.length) {
      Logger.log('Keine Stunden im Fenster – Ferien. Nichts zu tun.');
      return;
    }

    var geplant = {};
    stunden.forEach(function (s) {
      var termin = baueTermin(s);
      if (!geplant[termin.id]) geplant[termin.id] = termin;
    });

    var vorhanden = holeVerwaltete(k.kalenderId, fenster.start, fenster.ende, false);
    var geloescht = holeGeloeschte(k.kalenderId, fenster.start, fenster.ende);

    var angelegt = 0, aktualisiert = 0, unveraendert = 0, entfernt = 0, uebersprungen = 0;

    Object.keys(geplant).forEach(function (id) {
      if (geloescht[id]) { uebersprungen++; return; }
      var neu = geplant[id];
      var alt = vorhanden[id];
      var neuerHash = neu.extendedProperties.private.contentHash;

      if (!alt) {
        if (!nurVorschau) einfuegen(k.kalenderId, neu);
        angelegt++;
      } else if (hashVon(alt) !== neuerHash) {
        if (!nurVorschau) Calendar.Events.update(neu, k.kalenderId, id);
        aktualisiert++;
      } else {
        unveraendert++;
      }
    });

    Object.keys(vorhanden).forEach(function (id) {
      if (geplant[id]) return;
      if (!istUnser(vorhanden[id])) {
        Logger.log('Termin ' + id + ' wird NICHT entfernt – ohne Markierung.');
        return;
      }
      if (!nurVorschau) Calendar.Events.remove(k.kalenderId, id);
      entfernt++;
    });

    var dauer = ((new Date()) - beginn) / 1000;
    var text = (nurVorschau ? 'PROBELAUF – ' : '') +
               angelegt + ' angelegt, ' + aktualisiert + ' aktualisiert, ' +
               entfernt + ' geloescht, ' + unveraendert + ' unveraendert' +
               (uebersprungen ? ', ' + uebersprungen + ' bleiben geloescht' : '') +
               ' (' + dauer.toFixed(1) + ' s)';

    // Nur protokollieren, wenn sich etwas getan hat – sonst laeuft das Protokoll voll.
    if (nurVorschau || angelegt || aktualisiert || entfernt) {
      Logger.log(text);
      console.log(text);
    }

    if (!nurVorschau) {
      PropertiesService.getScriptProperties()
        .setProperty('letzterLauf', String(beginn.getTime()));
    }
  } finally {
    sperre.releaseLock();
  }
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

function syncFenster() {
  var heute = new Date();
  var ende = new Date(heute.getTime());
  ende.setDate(ende.getDate() + EINSTELLUNGEN.vorlaufTage);
  return { start: heute, ende: ende };
}

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
  if (s.unterrichtsnotiz && s.infos.indexOf(s.unterrichtsnotiz) === -1) {
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

/** Kennungen der von Hand geloeschten Termine (Grabsteine mit status 'cancelled'). */
function holeGeloeschte(kalenderId, start, ende) {
  var alle = holeVerwaltete(kalenderId, start, ende, true);
  var geloescht = {};
  Object.keys(alle).forEach(function (id) {
    if (alle[id].status === 'cancelled') geloescht[id] = true;
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
