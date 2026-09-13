"""Genaue Feldsemantik bei Ausfall (CANCELLED) und Vertretung (removed) ansehen."""
import os, json, requests
from dotenv import load_dotenv
load_dotenv()

# Eigene Personennummer aus .env (UNTIS_PERSON_ID)
PERSON_ID = os.environ.get("UNTIS_PERSON_ID", "")
B = f"https://{os.environ['UNTIS_SERVER']}"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 untis-gcal-sync/explore"
s.post(f"{B}/WebUntis/j_spring_security_check",
       data={"school": os.environ["UNTIS_SCHOOL"], "j_username": os.environ["UNTIS_USER"],
             "j_password": os.environ["UNTIS_PASSWORD"], "token": ""}, timeout=30, allow_redirects=False)
jwt = s.get(f"{B}/WebUntis/api/token/new", timeout=30).text.strip()
s.headers["Authorization"] = f"Bearer {jwt}"

d = s.get(f"{B}/WebUntis/api/rest/view/v1/timetable/entries"
          f"?start=2026-08-24&end=2026-09-20&format=2&resourceType=STUDENT"
          f"&resources={PERSON_ID}"
          f"&periodTypes=&timetableType=MY_TIMETABLE", timeout=30).json()

eintraege = []
for tag in d["days"]:
    for e in tag["gridEntries"]:
        e["_datum"] = tag["date"]
        eintraege.append(e)

def zeig(titel, e):
    print(f"\n{'='*60}\n{titel}\n{'='*60}")
    print(json.dumps(e, ensure_ascii=False, indent=1)[:2200])

for e in eintraege:
    if e["status"] == "CANCELLED":
        zeig("AUSGEFALLEN", e); break

for e in eintraege:
    if any((x or {}).get("removed") for p in ("position1","position2","position3","position4","position5")
           for x in (e.get(p) or [])):
        zeig("MIT ERSETZUNG (removed)", e); break

# Welche Typen tauchen in welchen Positionen auf?
typen = {}
for e in eintraege:
    for p in ("position1","position2","position3","position4","position5","position6","position7"):
        for x in (e.get(p) or []):
            t = (x.get("current") or {}).get("type")
            typen.setdefault(p, set()).add(t)
print("\n\nTypen je Position:")
for p in sorted(typen):
    print(f"  {p}: {sorted(t for t in typen[p] if t)}")

print("\nVorkommende 'type'-Werte:", sorted({e['type'] for e in eintraege}))
print("Vorkommende 'statusDetail':", sorted({str(e['statusDetail']) for e in eintraege}))
print("Vorkommende 'icons':", sorted({i for e in eintraege for i in (e.get('icons') or [])}))
print("Ganztags-Einträge (00:00-23:59):",
      sum(1 for e in eintraege if e['duration']['start'].endswith('T00:00') and e['duration']['end'].endswith('T23:59')))
