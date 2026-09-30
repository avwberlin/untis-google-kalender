"""Stellt faelschlich unterdrueckte Termine wieder her."""
import datetime as dt, os, collections, time
from dotenv import load_dotenv
from untis import RestQuelle
from kalender import Kalender
from modelle import ZEITZONE
load_dotenv()
heute = dt.datetime.now(ZEITZONE).date()
ende = dt.date(2027, 3, 16)

q = RestQuelle(os.environ["UNTIS_SERVER"], os.environ["UNTIS_SCHOOL"],
               os.environ["UNTIS_USER"], os.environ["UNTIS_PASSWORD"])
q.anmelden()
stunden = q.hole_stunden(heute, ende)
q.abmelden()
if len(stunden) < 100:
    raise SystemExit(f"ABBRUCH: nur {len(stunden)} Stunden – Antwort unplausibel.")

k = Kalender(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], os.environ["GCAL_ID"])
im_kal = k.hole_verwaltete(heute, ende)
grab = k.hole_geloeschte(heute, ende)

zu_retten = [s for s in stunden if s.event_id() in grab and s.event_id() not in im_kal]
print(f"{len(zu_retten)} Termine werden wiederhergestellt.\n")

erfolg = fehler = 0
for s in zu_retten:
    termin = k.baue_termin(s)
    termin["status"] = "confirmed"
    try:
        k.dienst.events().update(calendarId=k.kalender_id, eventId=termin["id"],
                                 body=termin, sendUpdates="none").execute()
        erfolg += 1
    except Exception as f:
        print(f"  FEHLER bei {s.titel()}: {type(f).__name__}")
        fehler += 1
    time.sleep(0.15)

print(f"Wiederhergestellt: {erfolg}, Fehler: {fehler}\n")

im_kal = k.hole_verwaltete(heute, ende)
print(f"Jetzt im Kalender: {len(im_kal)} von {len(stunden)} erwarteten")
morgen = heute + dt.timedelta(days=1)
morgige = k.hole_verwaltete(morgen, morgen)
print(f"\nMorgen ({morgen}):")
for e in sorted(morgige.values(), key=lambda x: x['start'].get('dateTime','')):
    print(f"   {e['start'].get('dateTime','')[11:16]}  {e.get('summary')}")
