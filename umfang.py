"""Wie viele Termine werden faelschlich unterdrueckt?"""
import datetime as dt, os, collections
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

k = Kalender(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], os.environ["GCAL_ID"])
im_kal = k.hole_verwaltete(heute, ende)
grab = k.hole_geloeschte(heute, ende)

geplant = {s.event_id(): s for s in stunden}
unterdrueckt = {eid: s for eid, s in geplant.items() if eid in grab and eid not in im_kal}

print(f"Untis liefert:            {len(geplant)} Stunden")
print(f"Im Kalender vorhanden:    {len(im_kal)}")
print(f"Grabsteine insgesamt:     {len(grab)}")
print(f"FAELSCHLICH unterdrueckt: {len(unterdrueckt)}\n")

nach_tag = collections.Counter(s.datum for s in unterdrueckt.values())
print("Betroffene Tage:")
for tag in sorted(nach_tag):
    wt = ['Mo','Di','Mi','Do','Fr','Sa','So'][tag.weekday()]
    print(f"   {tag} ({wt}): {nach_tag[tag]} Stunden fehlen")
