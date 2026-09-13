"""
Erkundung, dritter Durchgang – gezielte Fragen:

1. personId ist 87 (steht in data.loginServiceConfig.user.personId und im JWT).
   Funktionieren damit die Stundenplan-REST-Endpunkte?
2. Der 500er bei /api/homeworks/lessons – liegt er an den Ferien
   (currentSchoolyearId = -1) oder ist der Endpunkt generell kaputt?
   Test: derselbe Aufruf mit einem Zeitraum im ABGESCHLOSSENEN Schuljahr 2025/2026.
"""

import datetime as dt
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

SERVER = os.environ["UNTIS_SERVER"]
SCHULE = os.environ["UNTIS_SCHOOL"]
BENUTZER = os.environ["UNTIS_USER"]
PASSWORT = os.environ["UNTIS_PASSWORD"]
BASIS = f"https://{SERVER}"
PERSON_ID = int(os.environ.get("UNTIS_PERSON_ID", "0"))  # eigene ID in .env setzen


def kuerzen(x, n=700):
    x = str(x)
    return x if len(x) <= n else x[:n] + f" … [{len(x)} Zeichen]"


sess = requests.Session()
sess.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) untis-gcal-sync/explore"
sess.post(f"{BASIS}/WebUntis/j_spring_security_check",
          data={"school": SCHULE, "j_username": BENUTZER,
                "j_password": PASSWORT, "token": ""},
          timeout=30, allow_redirects=False)
jwt = sess.get(f"{BASIS}/WebUntis/api/token/new", timeout=30).text.strip()
sess.headers["Authorization"] = f"Bearer {jwt}"
print(f"Login ok (JWT {len(jwt)} Zeichen), personId={PERSON_ID}\n")

# Zeitraeume
NEU_START, NEU_ENDE = dt.date(2026, 8, 24), dt.date(2026, 9, 20)   # neues Schuljahr
ALT_START, ALT_ENDE = dt.date(2026, 6, 1), dt.date(2026, 6, 30)    # altes Schuljahr


def probe(name, pfad):
    try:
        r = sess.get(BASIS + pfad, timeout=30)
    except Exception as e:
        print(f"[{name}] AUSNAHME {type(e).__name__}: {e}\n")
        return None
    print(f"[{name}] HTTP {r.status_code}")
    print("   " + kuerzen(r.text))
    print()
    return r


def kompakt(d):
    return d.strftime("%Y%m%d")


print("--- Frage 2: Hausaufgaben, altes vs. neues Schuljahr ---")
probe("homeworks NEUES Schuljahr",
      f"/WebUntis/api/homeworks/lessons?startDate={kompakt(NEU_START)}&endDate={kompakt(NEU_ENDE)}")
probe("homeworks ALTES Schuljahr",
      f"/WebUntis/api/homeworks/lessons?startDate={kompakt(ALT_START)}&endDate={kompakt(ALT_ENDE)}")

print("--- Prüfungen, altes vs. neues Schuljahr ---")
probe("exams NEUES Schuljahr",
      f"/WebUntis/api/exams?startDate={kompakt(NEU_START)}&endDate={kompakt(NEU_ENDE)}")
probe("exams ALTES Schuljahr",
      f"/WebUntis/api/exams?startDate={kompakt(ALT_START)}&endDate={kompakt(ALT_ENDE)}")

print("--- Frage 1: Stundenplan-REST mit personId=87 ---")
probe("public weekly (elementType=5)",
      f"/WebUntis/api/public/timetable/weekly/data?elementType=5&elementId={PERSON_ID}"
      f"&date={NEU_START.isoformat()}&formatId=2")
probe("rest v1 entries",
      f"/WebUntis/api/rest/view/v1/timetable/entries?start={NEU_START.isoformat()}"
      f"&end={NEU_ENDE.isoformat()}&format=2&resourceType=STUDENT&resources={PERSON_ID}"
      f"&periodTypes=&timetableType=MY_TIMETABLE")
