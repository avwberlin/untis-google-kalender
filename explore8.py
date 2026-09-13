"""Letzte Eingrenzung: liegt der 500er am Endpunkt selbst oder an den Parametern?
Getestet wird ausschliesslich der bekannte Endpunkt /WebUntis/api/homeworks/lessons
in verschiedenen Parametervarianten – es werden keine neuen Endpunkte erfunden."""
import os, requests
from dotenv import load_dotenv
load_dotenv()
S = os.environ["UNTIS_SERVER"]; B = f"https://{S}"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/140.0"
s.post(f"{B}/WebUntis/j_spring_security_check",
       data={"school": os.environ["UNTIS_SCHOOL"], "j_username": os.environ["UNTIS_USER"],
             "j_password": os.environ["UNTIS_PASSWORD"], "token": ""},
       timeout=30, allow_redirects=False)
jwt = s.get(f"{B}/WebUntis/api/token/new", timeout=30).text.strip()
s.headers.update({"Authorization": f"Bearer {jwt}", "Accept": "application/json",
                  "Referer": f"{B}/WebUntis/index.do"})

varianten = [
    ("ohne Parameter", "/WebUntis/api/homeworks/lessons"),
    ("kompaktes Datum", "/WebUntis/api/homeworks/lessons?startDate=20260824&endDate=20260920"),
    ("ISO-Datum", "/WebUntis/api/homeworks/lessons?startDate=2026-08-24&endDate=2026-09-20"),
    ("eine Woche", "/WebUntis/api/homeworks/lessons?startDate=20260824&endDate=20260828"),
    ("ein Tag", "/WebUntis/api/homeworks/lessons?startDate=20260825&endDate=20260825"),
]
for name, pfad in varianten:
    r = s.get(B + pfad, timeout=30)
    print(f"[{name:18s}] HTTP {r.status_code}  {r.text[:180]}")
