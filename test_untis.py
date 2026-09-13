"""Testet den WebUntis-Teil ohne Google-Kalender."""
import datetime as dt, logging, os
from dotenv import load_dotenv
from untis import RestQuelle
from modelle import ZEITZONE, Status
from sync import zeige_stunden

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)-9s %(message)s")
load_dotenv()

q = RestQuelle(os.environ["UNTIS_SERVER"], os.environ["UNTIS_SCHOOL"],
               os.environ["UNTIS_USER"], os.environ["UNTIS_PASSWORD"])
q.anmelden()
heute = dt.datetime.now(ZEITZONE).date()
fenster = q.schuljahr_fenster(heute, heute + dt.timedelta(days=28))
print("Fenster:", fenster)
stunden = q.hole_stunden(*fenster)
q.abmelden()

print(f"\n{len(stunden)} Stunden.")
aus = [s for s in stunden if s.status is Status.AUSGEFALLEN]
geaendert = [s for s in stunden if s.hat_aenderung]
ganztags = [s for s in stunden if s.ganztags]
print(f"Ausgefallen: {len(aus)}, geändert: {len(geaendert)}, ganztägig: {len(ganztags)}")

print("\n### Beispiel AUSGEFALLEN ###")
for s in aus[:1]:
    print(s.titel()); print(s.beschreibung())
print("\n### Beispiel MIT LEHRERWECHSEL ###")
for s in stunden:
    if s.lehrer_original or s.raeume_original:
        print(s.titel()); print(s.beschreibung()); break
print("\n### Beispiel GANZTÄGIG ###")
for s in ganztags[:1]:
    print(s.titel()); print(s.beschreibung())

# Eindeutigkeit der Event-IDs pruefen
ids = [s.event_id() for s in stunden]
print(f"\nEvent-IDs: {len(ids)} gesamt, {len(set(ids))} eindeutig")
import re
ungueltig = [i for i in ids if not re.fullmatch(r"[a-v0-9]{5,1024}", i)]
print(f"Ungültige Event-IDs (Google-Regel a-v/0-9): {len(ungueltig)}")

zeige_stunden(stunden, 3)
