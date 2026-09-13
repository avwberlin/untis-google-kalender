"""
Erkundung, vierter Durchgang.

A) Vollstaendige Struktur eines gridEntry aus /api/rest/view/v1/timetable/entries
   ansehen – welche Zusatzinfos haengen dort dran?
B) Den echten Hausaufgaben-Endpunkt der neuen Oberflaeche finden, indem wir die
   JavaScript-Bundles der Weboberflaeche laden und nach API-Pfaden durchsuchen.
   (Wir raten keine Endpunkte, wir lesen die aus, die die Oberflaeche selbst nutzt.)
"""

import datetime as dt
import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER = os.environ["UNTIS_SERVER"]
SCHULE = os.environ["UNTIS_SCHOOL"]
BENUTZER = os.environ["UNTIS_USER"]
PASSWORT = os.environ["UNTIS_PASSWORD"]
BASIS = f"https://{SERVER}"
PERSON_ID = int(os.environ.get("UNTIS_PERSON_ID", "0"))  # eigene ID in .env setzen

sess = requests.Session()
sess.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) untis-gcal-sync/explore"
sess.post(f"{BASIS}/WebUntis/j_spring_security_check",
          data={"school": SCHULE, "j_username": BENUTZER,
                "j_password": PASSWORT, "token": ""},
          timeout=30, allow_redirects=False)
jwt = sess.get(f"{BASIS}/WebUntis/api/token/new", timeout=30).text.strip()
sess.headers["Authorization"] = f"Bearer {jwt}"
print("Login ok.\n")

# ---------------------------------------------------------------- A
print("=" * 70)
print("A) Struktur der Stundenplan-Einträge")
print("=" * 70)
r = sess.get(f"{BASIS}/WebUntis/api/rest/view/v1/timetable/entries"
             f"?start=2026-08-24&end=2026-09-20&format=2&resourceType=STUDENT"
             f"&resources={PERSON_ID}&periodTypes=&timetableType=MY_TIMETABLE", timeout=30)
daten = r.json()
print(f"Top-Level-Schlüssel: {list(daten.keys())}, format={daten.get('format')}")

alle_eintraege = []
for tag in daten.get("days", []):
    for e in tag.get("gridEntries", []):
        e["_datum"] = tag["date"]
        alle_eintraege.append(e)
    if tag.get("dayEntries"):
        print(f"  dayEntries am {tag['date']}: {json.dumps(tag['dayEntries'], ensure_ascii=False)[:300]}")
    if tag.get("status") != "REGULAR":
        print(f"  Tagesstatus {tag['date']}: {tag.get('status')}")

print(f"\nGesamt {len(alle_eintraege)} Stundeneinträge im Fenster.")
if alle_eintraege:
    print("\nAlle Feldnamen eines Eintrags:")
    print(sorted(alle_eintraege[0].keys()))
    print("\nVollständiges Beispiel (erster Eintrag):")
    print(json.dumps(alle_eintraege[0], ensure_ascii=False, indent=2)[:2500])

    # Statistik ueber Status und Zusatzfelder
    status = {}
    mit_notes = mit_removed = mit_icons = 0
    for e in alle_eintraege:
        status[e.get("status")] = status.get(e.get("status"), 0) + 1
        if e.get("notesAll"):
            mit_notes += 1
        if e.get("icons"):
            mit_icons += 1
        for pos in ("position1", "position2", "position3", "position4", "position5"):
            for eintrag in e.get(pos) or []:
                if eintrag.get("removed"):
                    mit_removed += 1
                    break
    print(f"\nStatusverteilung: {status}")
    print(f"Einträge mit notesAll: {mit_notes}")
    print(f"Einträge mit icons: {mit_icons}")
    print(f"Einträge mit 'removed' (= Vertretung/Raumwechsel): {mit_removed}")

    # Ein Eintrag mit Abweichung
    for e in alle_eintraege:
        if e.get("status") not in (None, "REGULAR"):
            print(f"\nBeispiel MIT Abweichung (status={e.get('status')}):")
            print(json.dumps(e, ensure_ascii=False, indent=2)[:2500])
            break

# ---------------------------------------------------------------- B
print("\n" + "=" * 70)
print("B) Hausaufgaben-Endpunkt der Oberfläche suchen")
print("=" * 70)

seiten = ["/WebUntis/index.do", "/timetable/my-student", "/WebUntis/"]
skripte = set()
for seite in seiten:
    try:
        r = sess.get(BASIS + seite, timeout=30)
    except Exception:
        continue
    gefunden = re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', r.text)
    for g in gefunden:
        skripte.add(g if g.startswith("http") else BASIS + ("" if g.startswith("/") else "/") + g)
    print(f"{seite} -> HTTP {r.status_code}, {len(gefunden)} Skript-Verweise")

print(f"\n{len(skripte)} JavaScript-Dateien gefunden. Durchsuche nach API-Pfaden …")

muster = re.compile(r'["\'`](/WebUntis/api/[A-Za-z0-9_\-/{}.$]+)')
alle_pfade = set()
hausaufgaben_pfade = set()

for url in sorted(skripte):
    try:
        r = sess.get(url, timeout=45)
    except Exception:
        continue
    if r.status_code != 200:
        continue
    treffer = muster.findall(r.text)
    for t in treffer:
        alle_pfade.add(t)
        if "homework" in t.lower() or "hausaufgab" in t.lower():
            hausaufgaben_pfade.add(t)

print(f"\nInsgesamt {len(alle_pfade)} API-Pfade in den Bundles gefunden.")
print("\n--- Pfade mit 'homework' ---")
for p in sorted(hausaufgaben_pfade):
    print(f"  {p}")
if not hausaufgaben_pfade:
    print("  (keine)")

print("\n--- Weitere interessante Pfade (exam, lesson, note, text, calendar) ---")
for p in sorted(alle_pfade):
    if any(w in p.lower() for w in ("exam", "lesson", "note", "text", "calendar-entry", "classreg")):
        print(f"  {p}")
