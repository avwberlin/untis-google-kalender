"""
Anbindung an den Google Kalender.

Sicherheitsregeln, die hier durchgesetzt werden:

* Es wird ausschliesslich in den Kalender geschrieben, dessen ID uebergeben wurde.
* Angefasst (geaendert oder geloescht) werden nur Termine, die
  extendedProperties.private.managedBy == "untis-sync" tragen.
  Alles andere wird nicht einmal veraendert gelesen.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from modelle import Status, Stunde, ZEITZONE

log = logging.getLogger("kalender")

BEREICH = ["https://www.googleapis.com/auth/calendar"]
MARKIERUNG = "untis-sync"

# Google-Farbkennungen
FARBE_AUSGEFALLEN = "8"    # Graphit
FARBE_AENDERUNG = "6"      # Tangerine
FARBE_PRUEFUNG = "11"      # Tomato


class KalenderFehler(RuntimeError):
    """Fehler beim Zugriff auf den Google Kalender."""


# Google begrenzt die Schreibrate je Kalender. Bei vielen Terminen auf einmal
# (etwa beim allerersten Lauf) laeuft man dagegen. Google empfiehlt dafuer
# ausdruecklich, den Aufruf mit wachsender Wartezeit zu wiederholen.
VORUEBERGEHEND = {403, 429, 500, 502, 503, 504}
MAX_VERSUCHE = 6


def _ist_ratenfehler(fehler: HttpError) -> bool:
    """Unterscheidet 'zu schnell' von 'keine Berechtigung' – beide sind HTTP 403."""
    if fehler.resp.status != 403:
        return fehler.resp.status in VORUEBERGEHEND
    text = str(fehler).lower()
    return "ratelimit" in text or "quota" in text or "userratelimit" in text


def _mit_wiederholung(aufruf, beschreibung: str):
    """Führt einen Google-Aufruf aus und wiederholt ihn bei Ratenbegrenzung."""
    for versuch in range(1, MAX_VERSUCHE + 1):
        try:
            return aufruf()
        except HttpError as fehler:
            if not _ist_ratenfehler(fehler) or versuch == MAX_VERSUCHE:
                raise
            # Exponentiell warten, mit etwas Zufall, damit nicht alle Aufrufe
            # gleichzeitig wieder loslaufen.
            warten = min(2 ** versuch, 32) + random.uniform(0, 1)
            log.warning("%s: Google bremst (Versuch %d von %d) – warte %.1fs.",
                        beschreibung, versuch, MAX_VERSUCHE, warten)
            time.sleep(warten)


class Kalender:
    def __init__(self, schluesseldatei: str, kalender_id: str):
        if not kalender_id:
            raise KalenderFehler("Keine Kalender-ID gesetzt (GCAL_ID).")
        self.kalender_id = kalender_id
        try:
            zugangsdaten = service_account.Credentials.from_service_account_file(
                schluesseldatei, scopes=BEREICH)
        except Exception as fehler:            # noqa: BLE001
            raise KalenderFehler(f"Service-Konto-Schlüssel nicht lesbar: {fehler}") from fehler
        self.dienst = build("calendar", "v3", credentials=zugangsdaten, cache_discovery=False)

    # ------------------------------------------------------------------

    def pruefe_zugriff(self) -> str:
        """Prüft, ob das Service-Konto den Kalender lesen darf. Gibt den Namen zurück."""
        try:
            eintrag = self.dienst.calendars().get(calendarId=self.kalender_id).execute()
        except HttpError as fehler:
            raise KalenderFehler(
                f"Kalender {self.kalender_id} nicht erreichbar (HTTP {fehler.resp.status}). "
                "Ist er für die Service-Konto-Adresse mit der Berechtigung "
                "'Termine ändern' freigegeben?"
            ) from fehler
        return eintrag.get("summary", "(ohne Namen)")

    # ------------------------------------------------------------------

    def _liste(self, start: dt.date, ende: dt.date, mit_geloeschten: bool) -> list[dict]:
        """Blättert durch alle verwalteten Termine im Fenster."""
        alle: list[dict] = []
        seite = None
        zeit_von = dt.datetime.combine(start, dt.time.min, ZEITZONE).isoformat()
        zeit_bis = dt.datetime.combine(ende + dt.timedelta(days=1), dt.time.min, ZEITZONE).isoformat()
        while True:
            try:
                antwort = _mit_wiederholung(
                    lambda s=seite: self.dienst.events().list(
                        calendarId=self.kalender_id,
                        timeMin=zeit_von,
                        timeMax=zeit_bis,
                        privateExtendedProperty=f"managedBy={MARKIERUNG}",
                        singleEvents=True,
                        showDeleted=mit_geloeschten,
                        maxResults=2500,
                        pageToken=s,
                    ).execute(),
                    "Termine lesen")
            except HttpError as fehler:
                raise KalenderFehler(f"Termine konnten nicht gelesen werden: {fehler}") from fehler

            alle.extend(antwort.get("items", []))
            seite = antwort.get("nextPageToken")
            if not seite:
                break
        return alle

    def hole_verwaltete(self, start: dt.date, ende: dt.date) -> dict[str, dict]:
        """Alle von diesem Skript verwalteten, noch bestehenden Termine, nach Event-ID."""
        return {t["id"]: t for t in self._liste(start, ende, mit_geloeschten=False)}

    def hole_geloeschte(self, start: dt.date, ende: dt.date) -> set[str]:
        """Kennungen der Termine, die von Hand im Google-Kalender gelöscht wurden.

        Google behaelt geloeschte Termine als Grabstein mit status='cancelled'.
        Die Markierung managedBy bleibt dabei erhalten, der Filter greift also
        weiterhin – es werden ausschliesslich eigene Termine betrachtet.

        Achtung: Google raeumt diese Grabsteine irgendwann ab. Danach kann ein so
        geloeschter Termin wieder auftauchen.
        """
        return {t["id"] for t in self._liste(start, ende, mit_geloeschten=True)
                if t.get("status") == "cancelled"}

    # ------------------------------------------------------------------

    def baue_termin(self, stunde: Stunde) -> dict:
        """Übersetzt eine Stunde in einen Google-Termin."""
        termin: dict = {
            "id": stunde.event_id(),
            "summary": stunde.titel(),
            "description": stunde.beschreibung(),
            "extendedProperties": {
                "private": {
                    "managedBy": MARKIERUNG,
                    "contentHash": stunde.inhalts_hash(),
                    "untisSchluessel": stunde.schluessel(),
                }
            },
        }

        if stunde.ort():
            termin["location"] = stunde.ort()

        if stunde.ganztags:
            termin["start"] = {"date": stunde.start.date().isoformat()}
            termin["end"] = {"date": (stunde.start.date() + dt.timedelta(days=1)).isoformat()}
        else:
            termin["start"] = {"dateTime": stunde.start.isoformat(), "timeZone": "Europe/Berlin"}
            termin["end"] = {"dateTime": stunde.ende.isoformat(), "timeZone": "Europe/Berlin"}

        # Farbe und Verfügbarkeit je nach Zustand
        if stunde.status is Status.AUSGEFALLEN:
            termin["colorId"] = FARBE_AUSGEFALLEN
            termin["transparency"] = "transparent"
        elif stunde.ist_pruefung:
            termin["colorId"] = FARBE_PRUEFUNG
        elif stunde.hat_aenderung:
            termin["colorId"] = FARBE_AENDERUNG
        # sonst: keine colorId – der Termin erbt die Farbe des Kalenders

        return termin

    # ------------------------------------------------------------------

    def anlegen_oder_aktualisieren(self, termin: dict) -> None:
        """Idempotent schreiben: derselbe Untis-Termin ist immer derselbe Google-Termin."""
        try:
            _mit_wiederholung(
                lambda: self.dienst.events().update(
                    calendarId=self.kalender_id,
                    eventId=termin["id"],
                    body=termin,
                    sendUpdates="none",
                ).execute(),
                f"Termin {termin['id']} aktualisieren")
        except HttpError as fehler:
            if fehler.resp.status == 404:
                # Termin existiert noch nicht – anlegen
                try:
                    _mit_wiederholung(
                        lambda: self.dienst.events().insert(
                            calendarId=self.kalender_id,
                            body=termin,
                            sendUpdates="none",
                        ).execute(),
                        f"Termin {termin['id']} anlegen")
                except HttpError as anlegefehler:
                    raise KalenderFehler(
                        f"Termin {termin['id']} konnte nicht angelegt werden: {anlegefehler}"
                    ) from anlegefehler
            else:
                raise KalenderFehler(
                    f"Termin {termin['id']} konnte nicht geschrieben werden: {fehler}"
                ) from fehler

    def loeschen(self, event_id: str, vorhandene: dict[str, dict]) -> bool:
        """Löscht einen Termin – aber nur, wenn er unsere Markierung trägt.

        Die Prüfung ist bewusst doppelt: die Liste ist bereits gefiltert, und
        hier wird noch einmal kontrolliert, damit ein fremder Termin auch bei
        einem Programmierfehler nicht gelöscht werden kann.
        """
        termin = vorhandene.get(event_id)
        markierung = (((termin or {}).get("extendedProperties") or {})
                      .get("private") or {}).get("managedBy")
        if markierung != MARKIERUNG:
            log.warning("Termin %s wird NICHT gelöscht – er trägt nicht die Markierung "
                        "'%s'.", event_id, MARKIERUNG)
            return False
        try:
            _mit_wiederholung(
                lambda: self.dienst.events().delete(
                    calendarId=self.kalender_id, eventId=event_id,
                    sendUpdates="none").execute(),
                f"Termin {event_id} löschen")
        except HttpError as fehler:
            if fehler.resp.status in (404, 410):
                return True     # war schon weg
            raise KalenderFehler(f"Termin {event_id} konnte nicht gelöscht werden: {fehler}") from fehler
        return True
