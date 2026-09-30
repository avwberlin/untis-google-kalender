"""Warum fehlen die Termine fuer morgen?"""
import datetime as dt, json, os
from dotenv import load_dotenv
from untis import RestQuelle
from kalender import Kalender
from modelle import ZEITZONE
load_dotenv()

heute = dt.datetime.now(ZEITZONE).date()
morgen = heute + dt.timedelta(days=1)
print(f"Heute: {heute} ({['Mo','Di','Mi','Do','Fr','Sa','So'][heute.weekday()]})")
print(f"Morgen: {morgen} ({['Mo','Di','Mi','Do','Fr','Sa','So'][morgen.weekday()]})\n")

q = RestQuelle(os.environ["UNTIS_SERVER"], os.environ["UNTIS_SCHOOL"],
               os.environ["UNTIS_USER"], os.environ["UNTIS_PASSWORD"])
q.anmelden()

print("=== A) Was sagt WebUntis roh für morgen? ===")
roh = q._get_json(
    f"/WebUntis/api/rest/view/v1/timetable/entries?start={morgen}&end={morgen}"
    f"&format=2&resourceType=STUDENT&resources={q.person_id}"
    f"&periodTypes=&timetableType=MY_TIMETABLE", "Morgen")
for tag in roh.get("days", []):
    ge = tag.get("gridEntries") or []
    print(f"  {tag['date']}  status={tag.get('status')}  Stunden={len(ge)}")
    for e in ge:
        f = next((x["current"]["shortName"] for n in range(1,8)
                  for x in (e.get(f"position{n}") or [])
                  if (x.get("current") or {}).get("type")=="SUBJECT"), "?")
        print(f"     {e['duration']['start'][11:]}-{e['duration']['end'][11:]} {f} status={e['status']}")
print(f"  errors: {roh.get('errors')}")

print("\n=== B) Was liefert meine Abstraktionsschicht? ===")
fenster = q.schuljahr_fenster(heute, dt.date(2027,3,16))
print(f"  Schuljahr-Fenster: {fenster}")
stunden = q.hole_stunden(heute, heute + dt.timedelta(days=7))
morgige = [s for s in stunden if s.datum == morgen]
print(f"  Stunden in den naechsten 7 Tagen: {len(stunden)}")
print(f"  davon morgen: {len(morgige)}")
for s in morgige:
    print(f"     {s.start:%H:%M}-{s.ende:%H:%M}  {s.titel()}   eventId={s.event_id()[:18]}…")
q.abmelden()

print("\n=== C) Was steht im Google-Kalender für morgen? ===")
k = Kalender(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], os.environ["GCAL_ID"])
im_kal = k.hole_verwaltete(morgen, morgen)
print(f"  verwaltete Termine: {len(im_kal)}")
for e in im_kal.values():
    print(f"     {e['start'].get('dateTime','')[11:16]} {e.get('summary')}")

print("\n=== D) Gibt es Grabsteine (von Hand geloescht) für morgen? ===")
grab = k.hole_geloeschte(morgen, morgen)
print(f"  Grabsteine: {len(grab)}")
for gid in list(grab)[:10]:
    print(f"     {gid[:22]}…")

print("\n=== E) Abgleich ===")
geplant_ids = {s.event_id() for s in morgige}
print(f"  Untis will:        {len(geplant_ids)}")
print(f"  Im Kalender:       {len(im_kal)}")
print(f"  Davon als geloescht markiert: {len(geplant_ids & grab)}")
fehlend = geplant_ids - set(im_kal)
print(f"  Fehlen im Kalender: {len(fehlend)}")
for f in list(fehlend)[:10]:
    print(f"     {f[:22]}…  Grabstein? {'JA' if f in grab else 'nein'}")
