"""
Erkundung, zweiter Durchgang.

Erkenntnis aus Durchgang 1: Der Abfragezeitraum darf nicht zwei Schuljahre
überspannen. Daher hier zuerst die Schuljahresgrenzen holen und alle Abfragen
darauf zuschneiden. Ausserdem: personId sauber aus app/config ziehen.
"""

import datetime as dt
import json
import os

import requests
import webuntis
from dotenv import load_dotenv

load_dotenv()

SERVER = os.environ["UNTIS_SERVER"]
SCHULE = os.environ["UNTIS_SCHOOL"]
BENUTZER = os.environ["UNTIS_USER"]
PASSWORT = os.environ["UNTIS_PASSWORD"]
BASIS = f"https://{SERVER}"


def titel(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def kuerzen(x, n=600):
    x = str(x)
    return x if len(x) <= n else x[:n] + f" … [{len(x)} Zeichen]"


# ----------------------------------------------------------------------
titel("Schuljahre ermitteln (JSON-RPC)")
s = webuntis.Session(server=SERVER, username=BENUTZER, password=PASSWORT,
                     school=SCHULE, useragent="untis-gcal-sync/explore")
s.login()

# Hinweis: getCurrentSchoolyear() scheitert, wenn heute in den Ferien zwischen
# zwei Schuljahren liegt. Deshalb bestimmen wir das Schuljahr selbst.
_heute = dt.date.today()
_jahre = list(s.schoolyears())
for sj in _jahre:
    print(f"  {sj.name}: {sj.start.date()} bis {sj.end.date()}")

# Schuljahr, das heute enthaelt – sonst das naechste, das in der Zukunft beginnt
aktuelles_jahr = next((j for j in _jahre if j.start.date() <= _heute <= j.end.date()), None)
if aktuelles_jahr is None:
    kuenftige = sorted((j for j in _jahre if j.start.date() > _heute),
                       key=lambda j: j.start)
    aktuelles_jahr = kuenftige[0] if kuenftige else max(_jahre, key=lambda j: j.end)
    print(f"  -> heute liegt in keinem Schuljahr (Ferien), nehme: {aktuelles_jahr.name}")

SJ_START = aktuelles_jahr.start.date()
SJ_ENDE = aktuelles_jahr.end.date()
print(f"\nAktuelles Schuljahr: {aktuelles_jahr.name} ({SJ_START} bis {SJ_ENDE})")

# Abfragefenster auf das Schuljahr zuschneiden
HEUTE = dt.date.today()
START = max(HEUTE, SJ_START)
ENDE = min(HEUTE + dt.timedelta(days=28), SJ_ENDE)
print(f"Zugeschnittenes Fenster: {START} bis {ENDE}")

# ----------------------------------------------------------------------
titel("WEG A – Stundenplan mit korrektem Fenster")
perioden = []
try:
    perioden = list(s.my_timetable(start=START, end=ENDE))
    print(f"my_timetable: {len(perioden)} Perioden")
except Exception as e:
    print(f"my_timetable FEHLER: {type(e).__name__}: {e}")

if perioden:
    interessant = ["code", "substText", "lstext", "lstext2", "info", "activityType",
                   "statflags", "bkText", "bkRemark", "exam", "rescheduleInfo",
                   "sg", "te", "ro", "su", "kl"]
    zaehler = {k: 0 for k in interessant}
    codes = {}
    orig_te = orig_ro = 0
    for p in perioden:
        roh = p._data
        for k in interessant:
            if roh.get(k):
                zaehler[k] += 1
        c = roh.get("code")
        codes[c] = codes.get(c, 0) + 1
        for eintrag in roh.get("te", []) or []:
            if eintrag.get("orgid"):
                orig_te += 1
        for eintrag in roh.get("ro", []) or []:
            if eintrag.get("orgid"):
                orig_ro += 1

    print(f"\nVerteilung 'code': {codes}")
    print(f"Perioden mit Original-Lehrer (orgid in te): {orig_te}")
    print(f"Perioden mit Original-Raum   (orgid in ro): {orig_ro}")
    print("\nBefüllte Felder:")
    for k, v in zaehler.items():
        print(f"  {k:14s}: {v}")

    print("\nBeispiel – erste Periode (Rohdaten):")
    print(kuerzen(json.dumps(perioden[0]._data, ensure_ascii=False), 1200))

    # Eine Periode mit Abweichung suchen
    for p in perioden:
        if p._data.get("code") or p._data.get("substText"):
            print("\nBeispiel – Periode MIT Abweichung:")
            print(kuerzen(json.dumps(p._data, ensure_ascii=False), 1200))
            break
    else:
        print("\n(Im Fenster keine Periode mit code/substText – noch Schuljahresanfang.)")

s.logout()

# ----------------------------------------------------------------------
titel("WEG B – REST mit korrektem Fenster")
sess = requests.Session()
sess.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) untis-gcal-sync/explore"
sess.post(f"{BASIS}/WebUntis/j_spring_security_check",
          data={"school": SCHULE, "j_username": BENUTZER,
                "j_password": PASSWORT, "token": ""},
          timeout=30, allow_redirects=False)
jwt = sess.get(f"{BASIS}/WebUntis/api/token/new", timeout=30).text.strip()
sess.headers["Authorization"] = f"Bearer {jwt}"
print(f"Login + JWT ok (Token {len(jwt)} Zeichen).")

# app/config vollständig ansehen, um personId zu finden
r = sess.get(f"{BASIS}/WebUntis/api/app/config", timeout=30)
cfg = r.json()
print("\napp/config – Struktur:")


def struktur(objekt, pfad="", tiefe=0):
    """Zeigt Schlüsselpfade, die nach einer Personen-ID aussehen."""
    if tiefe > 4:
        return
    if isinstance(objekt, dict):
        for k, v in objekt.items():
            neuer_pfad = f"{pfad}.{k}" if pfad else k
            if isinstance(v, (dict, list)):
                struktur(v, neuer_pfad, tiefe + 1)
            else:
                if any(w in k.lower() for w in ("id", "person", "name", "type", "role", "klasse", "student")):
                    print(f"  {neuer_pfad} = {kuerzen(v, 80)}")


struktur(cfg)

# JWT-Nutzdaten (Mittelteil) dekodieren – enthält oft personId
import base64
try:
    teil = jwt.split(".")[1]
    teil += "=" * (-len(teil) % 4)
    nutzdaten = json.loads(base64.urlsafe_b64decode(teil))
    print("\nJWT-Nutzdaten (Schlüssel):", list(nutzdaten.keys()))
    for k, v in nutzdaten.items():
        if any(w in k.lower() for w in ("person", "user", "sub", "tenant", "school", "type", "id")):
            print(f"  {k} = {kuerzen(v, 100)}")
except Exception as e:
    print("JWT nicht dekodierbar:", e)

person_id = (cfg.get("data", {}).get("user", {}) or {}).get("personId")
print(f"\npersonId aus app/config: {person_id}")

# Endpunkte erneut, jetzt mit Datum innerhalb des Schuljahres
ks, ke = START.strftime("%Y%m%d"), ENDE.strftime("%Y%m%d")
tests = [
    ("homeworks/lessons", f"/WebUntis/api/homeworks/lessons?startDate={ks}&endDate={ke}"),
    ("exams", f"/WebUntis/api/exams?startDate={ks}&endDate={ke}"),
]
if person_id:
    tests += [
        ("public weekly (personId)",
         f"/WebUntis/api/public/timetable/weekly/data?elementType=5&elementId={person_id}"
         f"&date={START.isoformat()}&formatId=2"),
        ("rest v1 entries (personId)",
         f"/WebUntis/api/rest/view/v1/timetable/entries?start={START.isoformat()}"
         f"&end={ENDE.isoformat()}&format=2&resourceType=STUDENT&resources={person_id}"
         f"&periodTypes=&timetableType=MY_TIMETABLE"),
    ]

for name, pfad in tests:
    r = sess.get(BASIS + pfad, timeout=30)
    print(f"\n[{name}] HTTP {r.status_code}")
    print("   " + kuerzen(r.text, 700))
