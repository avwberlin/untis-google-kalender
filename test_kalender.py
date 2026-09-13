"""Prueft, ob das Service-Konto wirklich in den Kalender schreiben darf.
Legt einen Testtermin an und loescht ihn sofort wieder."""
import datetime as dt, os
from dotenv import load_dotenv
from kalender import Kalender, KalenderFehler, MARKIERUNG
from modelle import ZEITZONE
load_dotenv()

k = Kalender(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], os.environ["GCAL_ID"])
print("Kalendername:", k.pruefe_zugriff())

jetzt = dt.datetime.now(ZEITZONE).replace(microsecond=0)
test = {
    "id": "untis" + "0" * 40,
    "summary": "TEST – wird sofort gelöscht",
    "start": {"dateTime": jetzt.isoformat(), "timeZone": "Europe/Berlin"},
    "end": {"dateTime": (jetzt + dt.timedelta(minutes=15)).isoformat(), "timeZone": "Europe/Berlin"},
    "extendedProperties": {"private": {"managedBy": MARKIERUNG, "contentHash": "test"}},
}
k.anlegen_oder_aktualisieren(test)
print("Schreiben: OK – Testtermin angelegt.")

gefunden = k.hole_verwaltete(jetzt.date(), jetzt.date())
print(f"Lesen: OK – {len(gefunden)} verwaltete Termine gefunden.")

if k.loeschen(test["id"], gefunden):
    print("Löschen: OK – Testtermin wieder entfernt.")

# Schutzregel pruefen: ein Termin OHNE Markierung darf nicht geloescht werden
fremd = {"nichtunser": {"summary": "Fremder Termin", "extendedProperties": {"private": {}}}}
if not k.loeschen("nichtunser", fremd):
    print("Schutzregel: OK – Termin ohne Markierung wurde NICHT gelöscht.")
