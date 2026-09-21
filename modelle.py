"""Internes Datenmodell – unabhängig davon, aus welcher WebUntis-Quelle die Daten stammen."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

ZEITZONE = ZoneInfo("Europe/Berlin")


class Status(str, Enum):
    """Zustand einer Stunde, wie ihn WebUntis meldet."""

    REGULAER = "REGULAR"
    GEAENDERT = "CHANGED"
    AUSGEFALLEN = "CANCELLED"


@dataclass
class Pruefung:
    """Eine Klausur oder Prüfung aus dem WebUntis-Prüfungskalender."""

    art: str            # z. B. "Klausur"
    name: str           # z. B. "ge/603"
    fach: str
    datum: dt.date
    start: dt.time
    ende: dt.time
    lehrer: list[str] = field(default_factory=list)
    raeume: list[str] = field(default_factory=list)
    text: str = ""

    def beschriftung(self) -> str:
        """Kurzform für die Terminbeschreibung."""
        teile = [self.art]
        if self.fach:
            teile.append(self.fach)
        if self.name and self.name != self.fach:
            teile.append(self.name)
        zeile = " ".join(teile)
        return f"{zeile}: {self.text}" if self.text else zeile


@dataclass
class Stunde:
    """Eine einzelne Unterrichtsstunde beziehungsweise ein Termin aus WebUntis."""

    untis_ids: list[int]
    start: dt.datetime            # zeitzonenbehaftet, Europe/Berlin
    ende: dt.datetime
    ganztags: bool = False

    fach: str = ""                # Kürzel, z. B. "REJ"
    fach_lang: str = ""           # Langname, z. B. "Lk Religion"

    lehrer: list[str] = field(default_factory=list)
    lehrer_original: list[str] = field(default_factory=list)
    raeume: list[str] = field(default_factory=list)
    raeume_original: list[str] = field(default_factory=list)
    klassen: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)   # z. B. "Kursreisen"

    status: Status = Status.REGULAER
    vertretungstext: str = ""     # substitutionText
    klassenbuchtext: str = ""     # lessonText – Lehrertext im Klassenbuch
    unterrichtsnotiz: str = ""    # lessonInfo
    notizen: str = ""             # notesAll
    hausaufgaben: list[str] = field(default_factory=list)
    pruefung: Pruefung | None = None

    # ------------------------------------------------------------------
    # Abgeleitete Werte
    # ------------------------------------------------------------------

    @property
    def datum(self) -> dt.date:
        return self.start.date()

    @property
    def bezeichnung(self) -> str:
        """Das Fach, oder ersatzweise die Info (bei Terminen ohne Fach, z. B. Kursreisen)."""
        if self.fach:
            return self.fach
        if self.infos:
            return " / ".join(self.infos)
        if self.klassenbuchtext:
            return self.klassenbuchtext
        return "Termin"

    @property
    def ist_pruefung(self) -> bool:
        return self.pruefung is not None

    @property
    def hat_aenderung(self) -> bool:
        """Vertretung, Raumwechsel oder sonstige Abweichung (aber kein Ausfall)."""
        return self.status is Status.GEAENDERT or bool(
            self.lehrer_original or self.raeume_original
        )

    def titel(self) -> str:
        """Terminüberschrift: 'Fach · Lehrerkürzel · Raum', bei Ausfall mit Präfix."""
        teile = [self.bezeichnung]
        if self.lehrer:
            teile.append(", ".join(self.lehrer))
        if self.raeume:
            teile.append(", ".join(self.raeume))
        titel = " · ".join(teile)
        if self.status is Status.AUSGEFALLEN:
            titel = f"FÄLLT AUS: {titel}"
        return titel

    def ort(self) -> str:
        """Inhalt für das Google-Feld 'location'."""
        return ", ".join(self.raeume)

    # ------------------------------------------------------------------
    # Identität und Änderungserkennung
    # ------------------------------------------------------------------

    def schluessel(self) -> str:
        """Stabile Kennung dieser Stunde über alle Läufe hinweg."""
        ids = "-".join(str(i) for i in sorted(self.untis_ids))
        return f"{ids}-{self.start.date().isoformat()}-{self.start.strftime('%H%M')}"

    def event_id(self) -> str:
        """Deterministische Google-Event-ID.

        Google erlaubt nur base32hex-Zeichen (a bis v, 0 bis 9), mindestens 5 Zeichen.
        Ein SHA1-Hex-String plus das Präfix 'untis' erfüllt das.
        """
        h = hashlib.sha1(self.schluessel().encode("utf-8")).hexdigest()
        return f"untis{h}"

    def inhalts_hash(self) -> str:
        """Hash über alle inhaltlichen Felder – ändert er sich nicht, sparen wir den API-Aufruf."""
        bestandteile = [
            self.start.isoformat(),
            self.ende.isoformat(),
            "ganztags" if self.ganztags else "zeit",
            self.fach,
            self.fach_lang,
            "|".join(self.lehrer),
            "|".join(self.lehrer_original),
            "|".join(self.raeume),
            "|".join(self.raeume_original),
            "|".join(self.klassen),
            "|".join(self.infos),
            self.status.value,
            self.vertretungstext,
            self.klassenbuchtext,
            self.unterrichtsnotiz,
            self.notizen,
            "|".join(self.hausaufgaben),
            self.pruefung.beschriftung() if self.pruefung else "",
        ]
        roh = "\x1f".join(bestandteile)
        return hashlib.sha1(roh.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------

    def beschreibung(self, zeitstempel: dt.datetime | None = None) -> str:
        """Strukturierte Terminbeschreibung. Leere Blöcke werden weggelassen."""
        bloecke: list[str] = []

        # Block 1: Stammdaten mit Hinweis auf Abweichungen
        kopf: list[str] = []
        if self.fach_lang and self.fach_lang != self.fach:
            kopf.append(f"Fach: {self.fach_lang}")
        if self.lehrer or self.lehrer_original:
            kopf.append(f"Lehrer: {self._mit_original(self.lehrer, self.lehrer_original)}")
        if self.raeume or self.raeume_original:
            kopf.append(f"Raum: {self._mit_original(self.raeume, self.raeume_original)}")
        if self.klassen:
            kopf.append(f"Klasse: {', '.join(self.klassen)}")
        if self.infos:
            kopf.append(f"Info: {', '.join(self.infos)}")
        # lessonInfo ist an dieser Schule die Kursbezeichnung (z. B. "q3L1"),
        # keine Lehrernotiz – daher eigene Zeile statt unter "Notiz".
        # Bei Klausuren steht dort "Klausur PH/711"; das wiederholt nur die
        # Klausurzeile weiter unten und wird deshalb weggelassen.
        if (self.unterrichtsnotiz and self.unterrichtsnotiz not in self.infos
                and not self.unterrichtsnotiz.lower().startswith("klausur")):
            kopf.append(f"Kurs: {self.unterrichtsnotiz}")
        if self.status is Status.AUSGEFALLEN:
            kopf.insert(0, "Diese Stunde fällt aus.")
        if kopf:
            bloecke.append("\n".join(kopf))

        if self.vertretungstext:
            bloecke.append(f"Vertretungstext: {self.vertretungstext}")

        if self.hausaufgaben:
            bloecke.append("Hausaufgaben:\n" + "\n".join(f"– {h}" for h in self.hausaufgaben))

        # Echte Lehrertexte: Klassenbuchtext und freie Notizen
        notiz_zeilen = [t for t in (self.klassenbuchtext, self.notizen)
                        if t and t not in self.infos and t != self.unterrichtsnotiz]
        # Doppelte Texte vermeiden, Reihenfolge beibehalten
        gesehen: set[str] = set()
        eindeutig = [t for t in notiz_zeilen if not (t in gesehen or gesehen.add(t))]
        if eindeutig:
            bloecke.append("Notiz: " + " | ".join(eindeutig))

        if self.pruefung:
            bloecke.append(f"Klausur: {self.pruefung.beschriftung()}")

        zeitstempel = zeitstempel or dt.datetime.now(ZEITZONE)
        bloecke.append(f"Zuletzt aktualisiert: {zeitstempel.strftime('%d.%m.%Y, %H:%M')}")

        return "\n\n".join(bloecke)

    @staticmethod
    def _mit_original(aktuell: list[str], original: list[str]) -> str:
        """'B105 (statt: A203)' – oder nur den aktuellen Wert, wenn es keine Änderung gab."""
        jetzt = ", ".join(aktuell)
        vorher = ", ".join(original)
        if not aktuell and vorher:
            return f"entfällt (vorher: {vorher})"
        if vorher and vorher != jetzt:
            return f"{jetzt} (statt: {vorher})"
        return jetzt
