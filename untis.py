"""
Anbindung an WebUntis.

Aufbau als dünne Abstraktionsschicht: `Datenquelle` beschreibt, was der Sync
braucht. Konkret gibt es zwei Umsetzungen:

* `RestQuelle`      – die interne REST-API der Weboberfläche. Sie liefert die
                      besten Daten (Klarnamen, alter Lehrer/Raum bei Vertretung,
                      Lehrertexte) und ist die Standardquelle.
* `JsonRpcQuelle`   – die JSON-RPC-Schnittstelle über die Bibliothek
                      python-webuntis. Reserve, falls Untis die interne API ändert.

Ändert Untis die interne API, genügt es, in `sync.py` auf `JsonRpcQuelle`
umzustellen – am Rest des Programms muss nichts angefasst werden.

Hausaufgaben: siehe `HausaufgabenModul` weiter unten. Der zuständige Endpunkt
antwortet bei dieser Schule dauerhaft mit HTTP 500; das Modul ist deshalb
abgeschaltet.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Protocol

import requests

from modelle import Pruefung, Status, Stunde, ZEITZONE

log = logging.getLogger("untis")

# Der Hausaufgaben-Endpunkt von WebUntis liefert bei dieser Schule immer HTTP 500
# (geprüft mit und ohne Parameter, in zwei verschiedenen Schuljahren). Sobald Untis
# das behebt, hier auf True stellen – der Rest ist bereits gebaut.
HAUSAUFGABEN_AKTIV = False


class UntisFehler(RuntimeError):
    """Alles, was den Abruf aus WebUntis unmöglich macht."""


def mit_wiederholung(aufruf, beschreibung: str, versuche: int = 3):
    """Führt `aufruf` aus und wiederholt bei Fehlern mit wachsender Wartezeit.

    Die Untis-Server sind regelmäßig kurz nicht erreichbar; ein einzelner
    Aussetzer soll den Lauf nicht scheitern lassen.
    """
    letzter_fehler: Exception | None = None
    for versuch in range(1, versuche + 1):
        try:
            return aufruf()
        except Exception as fehler:      # noqa: BLE001 – wir wollen wirklich alles abfangen
            letzter_fehler = fehler
            if versuch < versuche:
                warten = 2 ** versuch     # 2, 4 Sekunden
                log.warning("%s fehlgeschlagen (Versuch %d von %d): %s – neuer Versuch in %ds",
                            beschreibung, versuch, versuche, fehler, warten)
                time.sleep(warten)
    raise UntisFehler(f"{beschreibung} nach {versuche} Versuchen fehlgeschlagen: {letzter_fehler}")


class Datenquelle(Protocol):
    """Das, was der Sync von einer WebUntis-Quelle erwartet."""

    def anmelden(self) -> None: ...

    def schuljahr_fenster(self, start: dt.date, ende: dt.date) -> tuple[dt.date, dt.date] | None:
        """Schneidet das Wunschfenster auf das passende Schuljahr zu.

        Gibt None zurück, wenn das Fenster komplett ausserhalb jedes Schuljahres
        liegt (dann sind Ferien und ein leerer Plan ist kein Fehler).
        """
        ...

    def hole_stunden(self, start: dt.date, ende: dt.date) -> list[Stunde]: ...

    def abmelden(self) -> None: ...


# ----------------------------------------------------------------------
# Weg B: interne REST-API (Standard)
# ----------------------------------------------------------------------

class RestQuelle:
    """Interne REST-API der WebUntis-Weboberfläche."""

    def __init__(self, server: str, schule: str, benutzer: str, passwort: str):
        self.basis = f"https://{server}"
        self.schule = schule
        self.benutzer = benutzer
        self.passwort = passwort
        self.person_id: int | None = None
        self.sitzung = requests.Session()
        self.sitzung.headers.update({
            "User-Agent": "untis-gcal-sync/1.0",
            "Accept": "application/json",
        })

    # -- Anmeldung ------------------------------------------------------

    def anmelden(self) -> None:
        def _login():
            antwort = self.sitzung.post(
                f"{self.basis}/WebUntis/j_spring_security_check",
                data={"school": self.schule, "j_username": self.benutzer,
                      "j_password": self.passwort, "token": ""},
                timeout=30, allow_redirects=False,
            )
            if "JSESSIONID" not in self.sitzung.cookies:
                raise UntisFehler(
                    f"Anmeldung abgelehnt (HTTP {antwort.status_code}) – "
                    "Benutzername, Passwort oder Schulname prüfen."
                )
            return antwort

        mit_wiederholung(_login, "WebUntis-Anmeldung")

        def _token():
            antwort = self.sitzung.get(f"{self.basis}/WebUntis/api/token/new", timeout=30)
            jwt = antwort.text.strip()
            if antwort.status_code != 200 or not jwt.startswith("ey"):
                raise UntisFehler(f"Kein gültiges Zugriffstoken erhalten (HTTP {antwort.status_code}).")
            return jwt

        jwt = mit_wiederholung(_token, "Token abholen")
        self.sitzung.headers["Authorization"] = f"Bearer {jwt}"
        log.info("Bei WebUntis angemeldet (Token erhalten).")

        # personId aus der Anwendungs-Konfiguration ziehen
        cfg = self._get_json("/WebUntis/api/app/config", "Konfiguration lesen")
        nutzer = (cfg.get("data", {}).get("loginServiceConfig", {}) or {}).get("user", {}) or {}
        self.person_id = nutzer.get("personId")
        if not self.person_id:
            raise UntisFehler("personId konnte nicht ermittelt werden.")
        log.info("Angemeldet als personId %s.", self.person_id)

    def abmelden(self) -> None:
        try:
            self.sitzung.get(f"{self.basis}/WebUntis/saml/logout", timeout=10)
        except Exception:                      # noqa: BLE001 – Abmeldung ist unkritisch
            pass
        self.sitzung.close()

    # -- Hilfsmittel ----------------------------------------------------

    def _get_json(self, pfad: str, beschreibung: str) -> dict:
        def _hole():
            antwort = self.sitzung.get(self.basis + pfad, timeout=45)
            if antwort.status_code != 200:
                raise UntisFehler(f"{beschreibung}: HTTP {antwort.status_code}")
            return antwort.json()

        return mit_wiederholung(_hole, beschreibung)

    # -- Schuljahr ------------------------------------------------------

    def schuljahr_fenster(self, start: dt.date, ende: dt.date) -> tuple[dt.date, dt.date] | None:
        """Nutzt die JSON-RPC-Schuljahresliste – die REST-API bietet das nicht an.

        WebUntis lehnt Abfragen ab, die zwei Schuljahre überspannen.
        """
        jahre = _schuljahre(self.basis, self.schule, self.benutzer, self.passwort)
        # Schuljahr, in das der Fensterstart faellt
        treffer = next((j for j in jahre if j[0] <= start <= j[1]), None)
        if treffer is None:
            # Ferien zwischen zwei Schuljahren: das naechste Schuljahr nehmen,
            # sofern es noch im Wunschfenster beginnt.
            kuenftig = sorted((j for j in jahre if j[0] > start), key=lambda j: j[0])
            if not kuenftig or kuenftig[0][0] > ende:
                return None
            treffer = kuenftig[0]
        return max(start, treffer[0]), min(ende, treffer[1])

    # -- Stundenplan ----------------------------------------------------

    def hole_stunden(self, start: dt.date, ende: dt.date) -> list[Stunde]:
        pfad = (f"/WebUntis/api/rest/view/v1/timetable/entries"
                f"?start={start.isoformat()}&end={ende.isoformat()}"
                f"&format=2&resourceType=STUDENT&resources={self.person_id}"
                f"&periodTypes=&timetableType=MY_TIMETABLE")
        daten = self._get_json(pfad, "Stundenplan abrufen")

        pruefungen = self._hole_pruefungen(start, ende)
        hausaufgaben = HausaufgabenModul(self).hole(start, ende)

        stunden: list[Stunde] = []
        ferientage = 0
        for tag in daten.get("days", []):
            if tag.get("status") == "NO_DATA" and not tag.get("gridEntries"):
                ferientage += 1
            for eintrag in tag.get("gridEntries", []):
                stunde = self._baue_stunde(eintrag)
                if stunde is None:
                    continue
                stunde.pruefung = _passende_pruefung(stunde, pruefungen)
                stunde.hausaufgaben = hausaufgaben.get(stunde.schluessel(), [])
                stunden.append(stunde)

        log.info("REST-Quelle: %d Stunden, %d Tage ohne Unterricht.", len(stunden), ferientage)
        return stunden

    def _baue_stunde(self, e: dict) -> Stunde | None:
        dauer = e.get("duration") or {}
        try:
            start = dt.datetime.fromisoformat(dauer["start"]).replace(tzinfo=ZEITZONE)
            ende = dt.datetime.fromisoformat(dauer["end"]).replace(tzinfo=ZEITZONE)
        except (KeyError, ValueError):
            log.warning("Eintrag ohne verwertbare Zeit übersprungen: %s", e.get("ids"))
            return None

        # Ein Eintrag von 00:00 bis 23:59 ist ein Ganztagstermin (z. B. Kursreise).
        ganztags = start.strftime("%H:%M") == "00:00" and ende.strftime("%H:%M") == "23:59"

        stunde = Stunde(
            untis_ids=list(e.get("ids") or []),
            start=start,
            ende=ende,
            ganztags=ganztags,
            status=_status_aus(e.get("status")),
            vertretungstext=(e.get("substitutionText") or "").strip(),
            klassenbuchtext=(e.get("lessonText") or "").strip(),
            unterrichtsnotiz=(e.get("lessonInfo") or "").strip(),
            notizen=(e.get("notesAll") or "").strip(),
        )

        # Die position1..7-Felder sind nicht typfest – wir verteilen nach dem
        # 'type'-Feld, nicht nach der Position.
        for nummer in range(1, 8):
            for element in (e.get(f"position{nummer}") or []):
                aktuell = element.get("current")
                entfernt = element.get("removed")
                art = (aktuell or entfernt or {}).get("type")
                name_aktuell = _name_von(aktuell)
                name_entfernt = _name_von(entfernt)

                if art == "TEACHER":
                    _anhaengen(stunde.lehrer, name_aktuell)
                    _anhaengen(stunde.lehrer_original, name_entfernt)
                elif art == "ROOM":
                    _anhaengen(stunde.raeume, name_aktuell)
                    _anhaengen(stunde.raeume_original, name_entfernt)
                elif art == "CLASS":
                    _anhaengen(stunde.klassen, name_aktuell or name_entfernt)
                elif art == "SUBJECT":
                    if aktuell:
                        stunde.fach = stunde.fach or aktuell.get("shortName") or ""
                        stunde.fach_lang = stunde.fach_lang or aktuell.get("longName") or ""
                    elif entfernt and not stunde.fach:
                        stunde.fach = entfernt.get("shortName") or ""
                        stunde.fach_lang = entfernt.get("longName") or ""
                elif art == "INFO":
                    _anhaengen(stunde.infos, name_aktuell or name_entfernt)

        # Zusatztexte aus dem texts-Feld übernehmen, falls dort etwas steht, das
        # noch nicht erfasst ist. LESSON_INFO steckt bereits in lessonInfo.
        for text in (e.get("texts") or []):
            if text.get("type") == "LESSON_INFO":
                continue
            inhalt = (text.get("text") or "").strip()
            if inhalt and inhalt not in (stunde.unterrichtsnotiz, stunde.klassenbuchtext,
                                         stunde.notizen, stunde.vertretungstext):
                stunde.notizen = f"{stunde.notizen} | {inhalt}".strip(" |") if stunde.notizen else inhalt

        return stunde

    # -- Prüfungen ------------------------------------------------------

    def _hole_pruefungen(self, start: dt.date, ende: dt.date) -> list[Pruefung]:
        pfad = (f"/WebUntis/api/exams?startDate={start.strftime('%Y%m%d')}"
                f"&endDate={ende.strftime('%Y%m%d')}")
        try:
            daten = self._get_json(pfad, "Prüfungen abrufen")
        except UntisFehler as fehler:
            log.warning("Prüfungen konnten nicht geladen werden: %s", fehler)
            return []

        ergebnis: list[Pruefung] = []
        for e in (daten.get("data", {}) or {}).get("exams", []) or []:
            try:
                datum = dt.datetime.strptime(str(e["examDate"]), "%Y%m%d").date()
                ergebnis.append(Pruefung(
                    art=e.get("examType") or "Prüfung",
                    name=e.get("name") or "",
                    fach=e.get("subject") or "",
                    datum=datum,
                    start=_zeit_aus(e.get("startTime")),
                    ende=_zeit_aus(e.get("endTime")),
                    lehrer=list(dict.fromkeys(e.get("teachers") or [])),
                    raeume=list(dict.fromkeys(e.get("rooms") or [])),
                    text=(e.get("text") or "").strip(),
                ))
            except (KeyError, ValueError) as fehler:
                log.warning("Prüfung übersprungen (%s): %s", fehler, e.get("name"))
        log.info("%d Prüfungen im Zeitraum gefunden.", len(ergebnis))
        return ergebnis


class HausaufgabenModul:
    """Hausaufgaben aus WebUntis.

    ABGESCHALTET. Der Endpunkt /WebUntis/api/homeworks/lessons antwortet bei
    dieser Schule ausnahmslos mit HTTP 500 – geprüft ohne Parameter, mit
    kompaktem und mit ISO-Datum, für einzelne Tage, für Wochen und zusätzlich
    in einem bereits abgeschlossenen Schuljahr. Das ist ein Fehler auf dem
    WebUntis-Server der Schule, nicht in diesem Programm. Die JSON-RPC-
    Schnittstelle kennt überhaupt keine Hausaufgaben-Methode.

    Sobald der Endpunkt wieder funktioniert: HAUSAUFGABEN_AKTIV auf True setzen.
    Die Zuordnung unten geht davon aus, dass die Antwort eine Liste von
    Hausaufgaben mit Datum und lessonId enthält, und muss beim Aktivieren
    gegen die dann tatsächliche Antwort geprüft werden.
    """

    def __init__(self, quelle: "RestQuelle"):
        self.quelle = quelle

    def hole(self, start: dt.date, ende: dt.date) -> dict[str, list[str]]:
        if not HAUSAUFGABEN_AKTIV:
            log.info("Hausaufgaben-Modul ist abgeschaltet (Endpunkt liefert HTTP 500).")
            return {}

        pfad = (f"/WebUntis/api/homeworks/lessons?startDate={start.strftime('%Y%m%d')}"
                f"&endDate={ende.strftime('%Y%m%d')}")
        try:
            daten = self.quelle._get_json(pfad, "Hausaufgaben abrufen")
        except UntisFehler as fehler:
            log.warning("Hausaufgaben nicht abrufbar: %s", fehler)
            return {}

        zuordnung: dict[str, list[str]] = {}
        for h in (daten.get("data", {}) or {}).get("homeworks", []) or []:
            text = (h.get("text") or "").strip()
            if not text:
                continue
            faellig = h.get("dueDate")
            beschriftung = f"{text} (bis {_datum_kurz(faellig)})" if faellig else text
            schluessel = str(h.get("lessonId") or h.get("id"))
            zuordnung.setdefault(schluessel, []).append(beschriftung)
        return zuordnung


# ----------------------------------------------------------------------
# Weg A: JSON-RPC (Reserve)
# ----------------------------------------------------------------------

class JsonRpcQuelle:
    """Reserve-Quelle über die Bibliothek python-webuntis.

    Liefert weniger: Lehrer und Räume kommen nur als IDs, die nachgeschlagen
    werden müssen, und es gibt keine Prüfungszuordnung über den Prüfungskalender.
    Wird nur gebraucht, falls Untis die interne REST-API ändert.
    """

    def __init__(self, server: str, schule: str, benutzer: str, passwort: str):
        self.server, self.schule = server, schule
        self.benutzer, self.passwort = benutzer, passwort
        self.sitzung = None
        self._lehrer: dict[int, str] = {}
        self._raeume: dict[int, str] = {}
        self._faecher: dict[int, tuple[str, str]] = {}
        self._klassen: dict[int, str] = {}

    def anmelden(self) -> None:
        import webuntis

        def _login():
            s = webuntis.Session(server=self.server, username=self.benutzer,
                                 password=self.passwort, school=self.schule,
                                 useragent="untis-gcal-sync/1.0")
            s.login()
            return s

        self.sitzung = mit_wiederholung(_login, "JSON-RPC-Anmeldung")
        # Stammdaten einmalig laden, um IDs auflösen zu können
        for t in self.sitzung.teachers():
            self._lehrer[t.id] = t.name
        for r in self.sitzung.rooms():
            self._raeume[r.id] = r.name
        for f in self.sitzung.subjects():
            self._faecher[f.id] = (f.name, f.long_name)
        for k in self.sitzung.klassen():
            self._klassen[k.id] = k.name
        log.info("JSON-RPC-Quelle bereit (%d Lehrer, %d Räume).", len(self._lehrer), len(self._raeume))

    def abmelden(self) -> None:
        if self.sitzung:
            try:
                self.sitzung.logout()
            except Exception:                  # noqa: BLE001
                pass

    def schuljahr_fenster(self, start: dt.date, ende: dt.date) -> tuple[dt.date, dt.date] | None:
        jahre = [(j.start.date(), j.end.date()) for j in self.sitzung.schoolyears()]
        treffer = next((j for j in jahre if j[0] <= start <= j[1]), None)
        if treffer is None:
            kuenftig = sorted((j for j in jahre if j[0] > start), key=lambda j: j[0])
            if not kuenftig or kuenftig[0][0] > ende:
                return None
            treffer = kuenftig[0]
        return max(start, treffer[0]), min(ende, treffer[1])

    def hole_stunden(self, start: dt.date, ende: dt.date) -> list[Stunde]:
        perioden = mit_wiederholung(
            lambda: list(self.sitzung.my_timetable(start=start, end=ende)),
            "Stundenplan abrufen (JSON-RPC)")

        stunden: list[Stunde] = []
        for p in perioden:
            roh = p._data
            try:
                datum = dt.datetime.strptime(str(roh["date"]), "%Y%m%d").date()
                start_zeit = _zeit_aus(roh["startTime"])
                end_zeit = _zeit_aus(roh["endTime"])
            except (KeyError, ValueError):
                continue

            beginn = dt.datetime.combine(datum, start_zeit, ZEITZONE)
            schluss = dt.datetime.combine(datum, end_zeit, ZEITZONE)
            code = roh.get("code")
            status = (Status.AUSGEFALLEN if code == "cancelled"
                      else Status.GEAENDERT if code == "irregular"
                      else Status.REGULAER)

            stunde = Stunde(
                untis_ids=[roh["id"]],
                start=beginn,
                ende=schluss,
                ganztags=(start_zeit.hour == 0 and start_zeit.minute == 0
                          and end_zeit.hour == 23 and end_zeit.minute == 59),
                status=status,
                vertretungstext=(roh.get("substText") or "").strip(),
                klassenbuchtext=(roh.get("lstext") or "").strip(),
                unterrichtsnotiz=(roh.get("info") or "").strip(),
            )
            for eintrag in roh.get("su", []) or []:
                name, lang = self._faecher.get(eintrag.get("id"), ("", ""))
                stunde.fach = stunde.fach or name
                stunde.fach_lang = stunde.fach_lang or lang
            for eintrag in roh.get("te", []) or []:
                _anhaengen(stunde.lehrer, self._lehrer.get(eintrag.get("id")))
                if eintrag.get("orgid"):
                    _anhaengen(stunde.lehrer_original, self._lehrer.get(eintrag["orgid"]))
            for eintrag in roh.get("ro", []) or []:
                _anhaengen(stunde.raeume, self._raeume.get(eintrag.get("id")))
                if eintrag.get("orgid"):
                    _anhaengen(stunde.raeume_original, self._raeume.get(eintrag["orgid"]))
            for eintrag in roh.get("kl", []) or []:
                _anhaengen(stunde.klassen, self._klassen.get(eintrag.get("id")))

            stunden.append(stunde)

        log.info("JSON-RPC-Quelle: %d Stunden.", len(stunden))
        return stunden


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------

def _schuljahre(basis: str, schule: str, benutzer: str, passwort: str) -> list[tuple[dt.date, dt.date]]:
    """Schuljahresgrenzen über JSON-RPC holen.

    Hinweis: getCurrentSchoolyear() scheitert, wenn heute in den Ferien zwischen
    zwei Schuljahren liegt. Deshalb holen wir die vollständige Liste und wählen
    selbst aus.
    """
    import webuntis

    server = basis.replace("https://", "").replace("http://", "")

    def _hole():
        s = webuntis.Session(server=server, username=benutzer, password=passwort,
                             school=schule, useragent="untis-gcal-sync/1.0")
        s.login()
        try:
            return [(j.start.date(), j.end.date()) for j in s.schoolyears()]
        finally:
            try:
                s.logout()
            except Exception:                  # noqa: BLE001
                pass

    return mit_wiederholung(_hole, "Schuljahre abrufen")


def _status_aus(wert: str | None) -> Status:
    try:
        return Status(wert)
    except (ValueError, TypeError):
        return Status.REGULAER


def _name_von(element: dict | None) -> str | None:
    if not element:
        return None
    return (element.get("shortName") or element.get("displayName")
            or element.get("longName") or None)


def _anhaengen(liste: list[str], wert: str | None) -> None:
    """Fügt einen Wert hinzu, wenn er gesetzt und noch nicht enthalten ist."""
    if wert and wert not in liste:
        liste.append(wert)


def _zeit_aus(wert) -> dt.time:
    """WebUntis liefert Uhrzeiten als Zahl: 800 = 08:00, 1445 = 14:45."""
    zahl = int(wert or 0)
    return dt.time(zahl // 100, zahl % 100)


def _datum_kurz(wert) -> str:
    try:
        return dt.datetime.strptime(str(wert), "%Y%m%d").strftime("%d.%m.")
    except (ValueError, TypeError):
        return str(wert)


def _passende_pruefung(stunde: Stunde, pruefungen: list[Pruefung]) -> Pruefung | None:
    """Ordnet einer Stunde die Prüfung zu, die am selben Tag zeitlich überlappt."""
    for p in pruefungen:
        if p.datum != stunde.datum:
            continue
        p_start = dt.datetime.combine(p.datum, p.start, ZEITZONE)
        p_ende = dt.datetime.combine(p.datum, p.ende, ZEITZONE)
        # Überlappen sich die Zeiträume?
        if stunde.start < p_ende and p_start < stunde.ende:
            # Wenn ein Fach bekannt ist, muss es zusammenpassen
            if p.fach and stunde.fach and p.fach.lower() != stunde.fach.lower():
                continue
            return p
    return None
