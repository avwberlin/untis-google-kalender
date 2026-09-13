"""
Wegwerf-Erkundungsskript: prüft, welcher WebUntis-Zugangsweg bei dieser Schule
funktioniert und welche Zusatzdaten (Hausaufgaben, Notizen, Vertretungstexte)
tatsächlich ankommen.

Weg A = JSON-RPC (Bibliothek python-webuntis)
Weg B = interne REST-API der Weboberflaeche (undokumentiert)

Aufruf:  .venv/bin/python explore.py
"""

import datetime as dt
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER = os.environ["UNTIS_SERVER"]
SCHULE = os.environ["UNTIS_SCHOOL"]
BENUTZER = os.environ["UNTIS_USER"]
PASSWORT = os.environ["UNTIS_PASSWORD"]

BASIS = f"https://{SERVER}"
HEUTE = dt.date.today()
ENDE = HEUTE + dt.timedelta(days=7)


def titel(text):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def kuerzen(text, laenge=500):
    """Antworten fuer die Log-Ausgabe kuerzen, damit nichts explodiert."""
    text = str(text)
    return text if len(text) <= laenge else text[:laenge] + f" … [{len(text)} Zeichen gesamt]"


# ----------------------------------------------------------------------
# Weg A: JSON-RPC
# ----------------------------------------------------------------------

def weg_a():
    titel("WEG A – JSON-RPC über python-webuntis")
    ergebnis = {"login": False, "perioden": 0, "felder": {}, "person_id": None,
                "person_typ": None}
    try:
        import webuntis
    except ImportError:
        print("Bibliothek 'webuntis' fehlt.")
        return ergebnis

    try:
        s = webuntis.Session(
            server=SERVER,
            username=BENUTZER,
            password=PASSWORT,
            school=SCHULE,
            useragent="untis-gcal-sync/explore",
        )
        s.login()
    except Exception as e:
        print(f"LOGIN FEHLGESCHLAGEN: {type(e).__name__}: {e}")
        return ergebnis

    print("Login erfolgreich.")
    ergebnis["login"] = True

    # personId / personType aus der Session-Antwort ziehen
    for attribut in ("personId", "personType", "klasseId"):
        wert = getattr(s, "_session_info", {}).get(attribut) if hasattr(s, "_session_info") else None
        if wert is not None:
            print(f"  {attribut}: {wert}")
    try:
        info = s._request("getUserData2017", {}) if hasattr(s, "_request") else {}
        print("  getUserData2017:", kuerzen(json.dumps(info, ensure_ascii=False), 400))
    except Exception as e:
        print(f"  getUserData2017 nicht verfügbar: {type(e).__name__}")

    # my_timetable
    perioden = None
    for name, aufruf in (
        ("my_timetable", lambda: s.my_timetable(start=HEUTE, end=ENDE)),
        ("timetable_extended", lambda: s.timetable_extended(start=HEUTE, end=ENDE)),
    ):
        try:
            perioden = list(aufruf())
            print(f"\n{name}: {len(perioden)} Perioden")
            if perioden:
                break
        except Exception as e:
            print(f"\n{name} FEHLER: {type(e).__name__}: {e}")

    if not perioden:
        print("Keine Perioden erhalten.")
        s.logout()
        return ergebnis

    ergebnis["perioden"] = len(perioden)

    # Welche Felder sind tatsächlich befüllt?
    interessant = ["code", "substText", "lstext", "lstext2", "info", "activityType",
                   "statflags", "bkText", "bkRemark", "exam", "rescheduleInfo"]
    gefunden = {k: 0 for k in interessant}
    codes = {}
    for p in perioden:
        roh = p._data
        for k in interessant:
            if roh.get(k):
                gefunden[k] += 1
        c = roh.get("code")
        codes[c] = codes.get(c, 0) + 1

    print(f"\nVerteilung 'code': {codes}")
    print("Befüllte Zusatzfelder (Anzahl Perioden mit Inhalt):")
    for k, v in gefunden.items():
        print(f"  {k:16s}: {v}")
    ergebnis["felder"] = gefunden

    # original_teachers / original_rooms
    try:
        p = perioden[0]
        print("\nBeispielperiode – Rohdaten:")
        print(kuerzen(json.dumps(p._data, ensure_ascii=False), 900))
        for attr in ("original_teachers", "original_rooms"):
            try:
                print(f"  {attr}: {list(getattr(p, attr))}")
            except Exception as e:
                print(f"  {attr}: nicht verfügbar ({type(e).__name__})")
    except Exception as e:
        print("Beispielperiode nicht lesbar:", e)

    s.logout()
    return ergebnis


# ----------------------------------------------------------------------
# Weg B: interne REST-API
# ----------------------------------------------------------------------

def weg_b():
    titel("WEG B – interne REST-API der Weboberfläche")
    ergebnis = {"login": False, "jwt": False, "endpunkte": {}, "person_id": None}

    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) untis-gcal-sync/explore"

    # Schritt 1: Formular-Login -> Cookies
    r = sess.post(
        f"{BASIS}/WebUntis/j_spring_security_check",
        data={"school": SCHULE, "j_username": BENUTZER,
              "j_password": PASSWORT, "token": ""},
        timeout=30,
        allow_redirects=False,
    )
    print(f"1) j_spring_security_check -> HTTP {r.status_code}")
    print(f"   Cookies: {sorted(sess.cookies.keys())}")
    print(f"   Antwort: {kuerzen(r.text, 300)}")

    if "JSESSIONID" not in sess.cookies:
        print("   Kein JSESSIONID-Cookie – Login fehlgeschlagen.")
        return ergebnis
    ergebnis["login"] = True

    # Schritt 2: JWT holen
    r = sess.get(f"{BASIS}/WebUntis/api/token/new", timeout=30)
    print(f"\n2) api/token/new -> HTTP {r.status_code}")
    jwt = r.text.strip()
    if r.status_code != 200 or not jwt.startswith("ey"):
        print(f"   Kein gültiges Token: {kuerzen(jwt, 200)}")
        return ergebnis
    print(f"   JWT erhalten, Länge {len(jwt)} Zeichen (Inhalt wird nicht geloggt).")
    ergebnis["jwt"] = True
    sess.headers["Authorization"] = f"Bearer {jwt}"

    # Schritt 3: personId ermitteln
    person_id = None
    r = sess.get(f"{BASIS}/WebUntis/api/app/config", timeout=30)
    print(f"\n3) api/app/config -> HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            cfg = r.json()
            nutzer = cfg.get("data", {}).get("loginServiceConfig", {}) or {}
            user = cfg.get("data", {}).get("user", {}) or {}
            person = user.get("person", {}) or {}
            person_id = person.get("id")
            print(f"   Anzeigename: {person.get('displayName')}")
            print(f"   personId: {person_id}   Rolle: {user.get('roles')}")
            ergebnis["person_id"] = person_id
        except Exception as e:
            print("   JSON nicht lesbar:", e)
            print("  ", kuerzen(r.text, 400))

    # Schritt 4: Kandidaten-Endpunkte durchprobieren
    iso_start = HEUTE.isoformat()
    iso_ende = ENDE.isoformat()
    kompakt_start = HEUTE.strftime("%Y%m%d")
    kompakt_ende = ENDE.strftime("%Y%m%d")
    pid = person_id if person_id is not None else ""

    kandidaten = [
        ("timetable/entries (format 2)",
         f"/WebUntis/api/rest/view/v1/timetable/entries?start={iso_start}&end={iso_ende}"
         f"&format=2&resourceType=STUDENT&resources={pid}&periodTypes=&timetableType=MY_TIMETABLE"),
        ("timetable/entries (format 1)",
         f"/WebUntis/api/rest/view/v1/timetable/entries?start={iso_start}&end={iso_ende}"
         f"&format=1&resourceType=STUDENT&resources={pid}&periodTypes=&timetableType=MY_TIMETABLE"),
        ("public timetable weekly",
         f"/WebUntis/api/public/timetable/weekly/data?elementType=5&elementId={pid}"
         f"&date={iso_start}&formatId=2"),
        ("homeworks/lessons",
         f"/WebUntis/api/homeworks/lessons?startDate={kompakt_start}&endDate={kompakt_ende}"),
        ("exams",
         f"/WebUntis/api/exams?startDate={kompakt_start}&endDate={kompakt_ende}"),
        ("news widget",
         f"/WebUntis/api/public/news/newsWidgetData?date={kompakt_start}"),
        ("messages",
         "/WebUntis/api/rest/view/v1/messages"),
    ]

    titel("Kandidaten-Endpunkte")
    for name, pfad in kandidaten:
        try:
            r = sess.get(BASIS + pfad, timeout=30)
        except Exception as e:
            print(f"\n[{name}] AUSNAHME: {type(e).__name__}: {e}")
            ergebnis["endpunkte"][name] = "Ausnahme"
            continue
        print(f"\n[{name}] HTTP {r.status_code}  ({pfad.split('?')[0]})")
        ergebnis["endpunkte"][name] = r.status_code
        print("   " + kuerzen(r.text, 500))

    return ergebnis, sess


if __name__ == "__main__":
    a = weg_a()
    try:
        b = weg_b()
    except Exception as e:
        print(f"\nWeg B abgebrochen: {type(e).__name__}: {e}")
        b = ({}, None)

    titel("KURZFAZIT")
    print(f"Weg A Login: {a['login']}, Perioden: {a['perioden']}")
    print(f"Weg B: {b[0] if isinstance(b, tuple) else b}")
