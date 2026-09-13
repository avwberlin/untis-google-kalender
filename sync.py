"""
WebUntis -> Google Kalender.

Betriebsmodi:
    python sync.py --dry-run    zeigt nur, was passieren würde, schreibt nichts
    python sync.py              führt den Sync aus
    python sync.py --purge      löscht alle vom Skript verwalteten Termine im Fenster

Beendet sich mit Exit-Code ungleich 0, wenn etwas schiefgeht – damit GitHub
Actions den Lauf als fehlgeschlagen markiert und eine Mail verschickt. Ein leerer
Stundenplan waehrend der Ferien ist ausdruecklich KEIN Fehler.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import tempfile
import time

from dotenv import load_dotenv

from kalender import Kalender, KalenderFehler, MARKIERUNG
from modelle import Status, Stunde, ZEITZONE
from untis import RestQuelle, UntisFehler

# Sync-Fenster: heute bis heute plus 28 Tage
VORLAUF_TAGE = 28

# Kurze Pause zwischen Schreibvorgaengen. Google begrenzt die Schreibrate je
# Kalender; ohne Pause laeuft der erste Lauf mit rund 100 neuen Terminen dagegen.
SCHREIBPAUSE = 0.15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-9s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sync")


# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------

def lade_konfiguration() -> dict:
    """Liest die Zugangsdaten aus .env beziehungsweise den GitHub-Secrets."""
    load_dotenv()
    fehlend = [name for name in
               ("UNTIS_SERVER", "UNTIS_SCHOOL", "UNTIS_USER", "UNTIS_PASSWORD", "GCAL_ID")
               if not os.environ.get(name)]
    if fehlend:
        raise SystemExit(f"FEHLER: Diese Angaben fehlen: {', '.join(fehlend)}")

    # Der Schlüssel kommt entweder als Datei (lokal) oder als JSON-Text (GitHub Secret).
    schluesseldatei = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
    inhalt = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if inhalt:
        temp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        temp.write(inhalt)
        temp.close()
        schluesseldatei = temp.name
    elif not os.path.exists(schluesseldatei):
        raise SystemExit(
            f"FEHLER: Service-Konto-Schlüssel nicht gefunden ({schluesseldatei}) und "
            "GOOGLE_SERVICE_ACCOUNT_JSON ist nicht gesetzt."
        )

    return {
        "server": os.environ["UNTIS_SERVER"],
        "schule": os.environ["UNTIS_SCHOOL"],
        "benutzer": os.environ["UNTIS_USER"],
        "passwort": os.environ["UNTIS_PASSWORD"],
        "kalender_id": os.environ["GCAL_ID"],
        "schluesseldatei": schluesseldatei,
    }


# ----------------------------------------------------------------------
# Anzeige
# ----------------------------------------------------------------------

def zeige_stunden(stunden: list[Stunde], anzahl: int = 10) -> None:
    """Gibt die ersten Termine im Klartext aus, damit man sie mit Untis vergleichen kann."""
    print()
    print("=" * 78)
    print(f"Die ersten {min(anzahl, len(stunden))} von {len(stunden)} geplanten Terminen:")
    print("=" * 78)
    for stunde in sorted(stunden, key=lambda s: s.start)[:anzahl]:
        wochentag = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][stunde.start.weekday()]
        if stunde.ganztags:
            zeit = "ganztägig      "
        else:
            zeit = f"{stunde.start:%H:%M}–{stunde.ende:%H:%M}  "
        print(f"\n{wochentag} {stunde.start:%d.%m.%Y}  {zeit}  {stunde.titel()}")
        for zeile in stunde.beschreibung().splitlines():
            if zeile.strip():
                print(f"        {zeile}")
    print()


# ----------------------------------------------------------------------
# Hauptablauf
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="WebUntis in den Google Kalender übertragen.")
    gruppe = parser.add_mutually_exclusive_group()
    gruppe.add_argument("--dry-run", action="store_true",
                        help="nur anzeigen, was passieren würde – nichts schreiben")
    gruppe.add_argument("--purge", action="store_true",
                        help="alle vom Skript verwalteten Termine im Fenster löschen")
    argumente = parser.parse_args()

    konfiguration = lade_konfiguration()

    heute = dt.datetime.now(ZEITZONE).date()
    fenster_start = heute
    fenster_ende = heute + dt.timedelta(days=VORLAUF_TAGE)
    log.info("Sync-Fenster: %s bis %s", fenster_start, fenster_ende)

    # --- Google-Kalender vorbereiten ---------------------------------
    try:
        kalender = Kalender(konfiguration["schluesseldatei"], konfiguration["kalender_id"])
        name = kalender.pruefe_zugriff()
        log.info("Zielkalender: '%s'", name)
    except KalenderFehler as fehler:
        log.error("Google-Kalender: %s", fehler)
        return 1

    # --- Notausstieg -------------------------------------------------
    if argumente.purge:
        return purge(kalender, fenster_start, fenster_ende)

    # --- WebUntis abrufen --------------------------------------------
    quelle = RestQuelle(konfiguration["server"], konfiguration["schule"],
                        konfiguration["benutzer"], konfiguration["passwort"])
    try:
        quelle.anmelden()

        zugeschnitten = quelle.schuljahr_fenster(fenster_start, fenster_ende)
        if zugeschnitten is None:
            log.info("Das gesamte Fenster liegt ausserhalb jedes Schuljahres – Ferien. "
                     "Nichts zu tun.")
            return 0
        abruf_start, abruf_ende = zugeschnitten
        if (abruf_start, abruf_ende) != (fenster_start, fenster_ende):
            log.info("Fenster auf das Schuljahr zugeschnitten: %s bis %s", abruf_start, abruf_ende)

        stunden = quelle.hole_stunden(abruf_start, abruf_ende)
    except UntisFehler as fehler:
        log.error("WebUntis: %s", fehler)
        return 1
    finally:
        quelle.abmelden()

    if not stunden:
        # Kein Unterricht im ganzen Fenster. Das ist nur dann ein Fehler, wenn
        # das Fenster tatsaechlich Schulzeit enthaelt.
        log.info("Keine Stunden im Zeitraum %s bis %s – das Fenster liegt vollständig "
                 "in den Ferien. Kein Fehler.", abruf_start, abruf_ende)
        return 0

    # --- Dry-Run -----------------------------------------------------
    if argumente.dry_run:
        zeige_stunden(stunden)
        return vorschau(kalender, stunden, fenster_start, fenster_ende)

    # --- Echter Sync -------------------------------------------------
    return schreibe(kalender, stunden, fenster_start, fenster_ende)


def _geplante_termine(stunden: list[Stunde], kalender: Kalender) -> dict[str, dict]:
    """Baut die Google-Termine und erkennt dabei doppelte Event-IDs."""
    geplant: dict[str, dict] = {}
    for stunde in stunden:
        termin = kalender.baue_termin(stunde)
        if termin["id"] in geplant:
            log.warning("Zwei Untis-Stunden ergeben dieselbe Kennung (%s) – "
                        "die spätere wird übersprungen: %s", stunde.schluessel(), stunde.titel())
            continue
        geplant[termin["id"]] = termin
    return geplant


def vorschau(kalender: Kalender, stunden: list[Stunde],
             start: dt.date, ende: dt.date) -> int:
    """--dry-run: berechnet die Änderungen, schreibt aber nichts."""
    geplant = _geplante_termine(stunden, kalender)
    try:
        vorhanden = kalender.hole_verwaltete(start, ende)
        von_hand_geloescht = kalender.hole_geloeschte(start, ende) & set(geplant)
    except KalenderFehler as fehler:
        log.error("%s", fehler)
        return 1

    anlegen = aktualisieren = unveraendert = uebersprungen = 0
    for event_id, termin in geplant.items():
        if event_id in von_hand_geloescht:
            uebersprungen += 1
            continue
        alt = vorhanden.get(event_id)
        if alt is None:
            anlegen += 1
        elif _hash_von(alt) != termin["extendedProperties"]["private"]["contentHash"]:
            aktualisieren += 1
        else:
            unveraendert += 1
    loeschen = [e for e in vorhanden if e not in geplant]

    print("=" * 78)
    print("PROBELAUF – es wurde nichts geschrieben.")
    print("=" * 78)
    log.info("Würde ausführen: %d angelegt, %d aktualisiert, %d gelöscht, %d unverändert",
             anlegen, aktualisieren, len(loeschen), unveraendert)
    if uebersprungen:
        log.info("%d Termine bleiben gelöscht, weil du sie im Kalender entfernt hast.",
                 uebersprungen)
    for event_id in loeschen:
        log.info("  würde löschen: %s", vorhanden[event_id].get("summary", event_id))
    return 0


def schreibe(kalender: Kalender, stunden: list[Stunde],
             start: dt.date, ende: dt.date) -> int:
    """Führt den eigentlichen Abgleich durch."""
    geplant = _geplante_termine(stunden, kalender)
    try:
        vorhanden = kalender.hole_verwaltete(start, ende)
        log.info("Im Kalender liegen bereits %d verwaltete Termine im Fenster.", len(vorhanden))

        # Termine, die von Hand im Google-Kalender geloescht wurden, bleiben geloescht.
        # Gezaehlt wird nur, was auch wirklich eine aktuelle Untis-Stunde betrifft –
        # alte Grabsteine laengst vergangener Stunden sind ohne Belang.
        von_hand_geloescht = kalender.hole_geloeschte(start, ende) & set(geplant)
        if von_hand_geloescht:
            log.info("%d von dir gelöschte Termine werden nicht wieder angelegt.",
                     len(von_hand_geloescht))

        angelegt = aktualisiert = unveraendert = geloescht = uebersprungen = 0

        for event_id, termin in geplant.items():
            if event_id in von_hand_geloescht:
                uebersprungen += 1
                continue
            alt = vorhanden.get(event_id)
            neuer_hash = termin["extendedProperties"]["private"]["contentHash"]
            if alt is None:
                kalender.anlegen_oder_aktualisieren(termin)
                angelegt += 1
                time.sleep(SCHREIBPAUSE)
            elif _hash_von(alt) != neuer_hash:
                kalender.anlegen_oder_aktualisieren(termin)
                aktualisiert += 1
                time.sleep(SCHREIBPAUSE)
            else:
                # Inhalt identisch – kein API-Aufruf
                unveraendert += 1

        # Termine, die es in Untis nicht mehr gibt, entfernen
        for event_id in [e for e in vorhanden if e not in geplant]:
            if kalender.loeschen(event_id, vorhanden):
                log.info("Gelöscht: %s", vorhanden[event_id].get("summary", event_id))
                geloescht += 1

    except KalenderFehler as fehler:
        log.error("%s", fehler)
        return 1

    log.info("Fertig: %d angelegt, %d aktualisiert, %d gelöscht, %d unverändert",
             angelegt, aktualisiert, geloescht, unveraendert)
    if uebersprungen:
        log.info("%d Termine blieben gelöscht, weil du sie selbst entfernt hast.", uebersprungen)
    return 0


def purge(kalender: Kalender, start: dt.date, ende: dt.date) -> int:
    """--purge: alle verwalteten Termine im Fenster entfernen."""
    try:
        vorhanden = kalender.hole_verwaltete(start, ende)
        log.info("%d verwaltete Termine im Fenster gefunden.", len(vorhanden))
        geloescht = sum(1 for event_id in list(vorhanden)
                        if kalender.loeschen(event_id, vorhanden))
    except KalenderFehler as fehler:
        log.error("%s", fehler)
        return 1
    log.info("Notausstieg fertig: %d gelöscht. Termine ohne die Markierung '%s' "
             "wurden nicht angefasst.", geloescht, MARKIERUNG)
    return 0


def _hash_von(termin: dict) -> str | None:
    return (((termin.get("extendedProperties") or {}).get("private")) or {}).get("contentHash")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.warning("Abgebrochen.")
        sys.exit(130)
